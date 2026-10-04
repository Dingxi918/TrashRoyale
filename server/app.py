"""Run the StormHacks game in demo mode or with an ESP32 serial camera."""

import argparse
import json
import mimetypes
import os
import threading
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .game import CATEGORIES, GameStore
from .motor_controller import (
    DEFAULT_LIBRARY, DEFAULT_MOTOR_INPUTS, MotorController, MotorError, parse_motor_inputs,
)
from .scene_detector import SceneDetector, thumbnail


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


class GameHTTPServer(ThreadingHTTPServer):
    # Several screens can each open parallel artwork connections at startup.
    request_queue_size = 64


class GameApp:
    def __init__(self, game, demo=False, serial_port=None, baud=460800,
                 model="gemini-3.8-flash", frame_interval=0.4, motor=None):
        self.game = game
        self.demo = demo
        self.serial_port = serial_port
        self.baud = baud
        self.model = model
        self.frame_interval = frame_interval
        self.motor = motor
        self.lock = threading.RLock()
        self.detector = SceneDetector()
        self.pending = None
        self.classifying = False
        self.routing = False
        self.motor_fault = False
        self.last_classification = None
        self.latest_jpeg = None
        self.status = "Demo ready" if demo else "Connecting to camera"
        self.error = None
        self.stop = threading.Event()

    def snapshot(self):
        with self.lock:
            result = self.game.snapshot()
            result.update({
                "mode": "demo" if self.demo else "camera",
                "pending": dict(self.pending) if self.pending else None,
                "status": self.status,
                "error": self.error,
                "has_frame": self.latest_jpeg is not None,
                "classifying": self.classifying,
                "last_classification": dict(self.last_classification) if self.last_classification else None,
                "motor": {
                    "enabled": self.motor is not None,
                    "routing": self.routing,
                    "faulted": self.motor_fault,
                    "inputs": dict(self.motor.inputs) if self.motor else None,
                },
            })
            return result

    def demo_item(self, item, label):
        if not self.demo:
            raise ValueError("Demo items are available only in demo mode")
        if not isinstance(item, str) or not item.strip() or len(item) > 80:
            raise ValueError("Enter an item name up to 80 characters")
        if label not in (*CATEGORIES, "unknown"):
            raise ValueError("Choose a valid category")
        with self.lock:
            if self.pending:
                raise ValueError("Confirm or dismiss the current item first")
            self.pending = {"item": item.strip(), "label": label, "source": "demo"}
            self.status = "Item ready for disposal confirmation"
            self.error = None

    def confirm(self, actual_bin):
        if actual_bin not in CATEGORIES:
            raise ValueError("Choose the bin used")
        with self.lock:
            if self.motor is not None:
                raise ValueError("Motor mode records successful routes automatically")
            if not self.pending:
                raise ValueError("There is no item awaiting confirmation")
            pending = self.pending
            event = self.game.record_sort(
                pending["item"], pending["label"], actual_bin, pending["source"]
            )
            self.pending = None
            self.status = ("Demo ready" if self.demo else
                           "Ready for the next item" if not self.detector.occupied
                           else "Waiting for the sorting area to clear")
            return event

    def demo_sort(self, category):
        """Credit one simulated sort independently of the live camera workflow."""
        if category not in CATEGORIES:
            raise ValueError("Choose a valid category")
        with self.lock:
            event = self.game.record_sort(f"Demo {category} item", category, category, "demo")
            if (self.demo and self.motor is None and not self.pending
                    and not self.classifying and not self.routing and not self.motor_fault):
                self.status = "Demo ready"
                self.error = None
            return event

    def dismiss(self):
        with self.lock:
            if self.routing:
                raise ValueError("Wait for the motor cycle to finish")
            if not self.pending:
                raise ValueError("There is no item to dismiss")
            self.pending = None
            self.status = ("Motor fault; check gate positions and restart" if self.motor_fault
                           else "Demo ready" if self.demo
                           else "Ready for the next item" if not self.detector.occupied
                           else "Waiting for the sorting area to clear")

    def reset_scene(self):
        if self.demo:
            raise ValueError("Scene reset is only available with a camera")
        with self.lock:
            if self.pending or self.classifying or self.routing:
                raise ValueError("Confirm or dismiss the current item first")
            if self.motor_fault:
                raise ValueError("Check gate positions and restart after a motor fault")
            self.detector.reset()
            self.status = "Clear the sorting area; next frame sets the empty reference"
            self.error = None

    def reset_game(self):
        """Reset shared gameplay while leaving camera and motor safety state intact."""
        with self.lock:
            if self.classifying or self.routing:
                raise ValueError("Wait for the current item to finish processing before resetting the game")
            self.game.reset()
            self.pending = None
            self.last_classification = None
            if not self.motor_fault:
                if self.demo:
                    self.status = "Demo ready"
                    self.error = None
                elif self.error is None and self.latest_jpeg is not None:
                    self.status = ("Waiting for the sorting area to clear" if self.detector.occupied
                                   else "Ready for the next item")
            return self.snapshot()

    def handle_classification(self, result):
        """Consume one Gemini result and, when enabled, route and credit it once."""
        label = result.get("label")
        item = result.get("item")
        if label not in (*CATEGORIES, "unknown") or not isinstance(item, str):
            raise ValueError("Invalid classification result")
        with self.lock:
            self.classifying = False
            if self.stop.is_set():
                return None
            if self.pending or self.routing:
                raise ValueError("An item is already being processed")
            if self.motor_fault:
                raise MotorError("Check gate positions and restart after a motor fault")
            self.pending = {"item": item, "label": label, "source": "camera"}
            self.last_classification = {"item": item, "label": label}
            self.error = None
            if self.motor is None:
                self.status = "Item ready for disposal confirmation"
                return None
            if label == "unknown":
                self.status = "Unknown item; no motor movement or resource earned"
                return None
            self.routing = True
            self.pending["routing"] = "in_progress"
            self.status = f"Routing {item} to {label}"

        # Keep API state readable while the blocking C out/hold/return cycle runs.
        try:
            motor_input = self.motor.execute_category(label)
        except MotorError as error:
            with self.lock:
                self.routing = False
                self.motor_fault = True
                self.pending["routing"] = "failed"
                self.status = "Motor fault; check gate positions and restart"
                self.error = str(error)
            raise

        with self.lock:
            self.routing = False
            self.pending["routing"] = "completed"
            event = self.game.record_sort(item, label, label, "motor", motor_input=motor_input)
            self.last_classification["motor_input"] = motor_input
            self.pending = None
            self.status = "Waiting for the sorting area to clear"
            return event

    def run_camera(self):
        from google import genai
        from .esp32_cam_rcv import Esp32SerialCamera
        from .gemini_classifier import classify_jpeg

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        while not self.stop.is_set():
            try:
                with Esp32SerialCamera(self.serial_port, self.baud) as camera:
                    with self.lock:
                        if not self.motor_fault:
                            self.status = "Clear the sorting area; first frame sets the empty reference"
                            self.error = None
                        self.detector.reset()
                    while not self.stop.is_set():
                        jpeg = camera.read_jpeg()
                        pixels = thumbnail(jpeg)
                        with self.lock:
                            self.latest_jpeg = jpeg
                            change = self.detector.observe(pixels)
                            if change == "clear":
                                if self.motor is not None and self.pending and self.pending["label"] == "unknown":
                                    self.pending = None
                                if not self.pending:
                                    self.status = ("Motor fault; check gate positions and restart" if self.motor_fault
                                                   else "Ready for the next item")
                            should_classify = change == "item" and self.pending is None and not self.motor_fault
                            if should_classify:
                                self.classifying = True
                                self.status = "Classifying item with Gemini"
                        if should_classify:
                            try:
                                result = classify_jpeg(jpeg, CATEGORIES, client, self.model)
                                if self.stop.is_set():
                                    break
                                self.handle_classification(result)
                            except MotorError:
                                # The item remains blocked for inspection; do not repeat a partial cycle.
                                pass
                            except Exception as error:
                                with self.lock:
                                    self.classifying = False
                                    self.status = "Classification failed; clear area to retry"
                                    self.error = str(error)
                        self.stop.wait(self.frame_interval)
            except Exception as error:
                with self.lock:
                    self.status = "Camera disconnected; retrying"
                    self.error = str(error)
                    self.detector.reset()
                self.stop.wait(2)


class Handler(BaseHTTPRequestHandler):
    app = None

    def _send(self, status, content, mime):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        try:
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            # A tab may close or cancel a poll after the game event was saved.
            pass

    def _json(self, status, value):
        self._send(status, json.dumps(value).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/api/state":
            self._json(200, self.app.snapshot())
        elif route == "/api/frame":
            with self.app.lock:
                jpeg = self.app.latest_jpeg
            if jpeg is None:
                self._json(404, {"error": "No camera frame yet"})
            else:
                self._send(200, jpeg, "image/jpeg")
        else:
            # Only publish the UI entry points and artwork, never repository files.
            name = unquote(route).lstrip("/") if route != "/" else "index.html"
            if "\x00" in name or any(part in {".", ".."} for part in name.split("/")):
                self._json(404, {"error": "Not found"})
                return
            root = FRONTEND.resolve()
            path = (root / name).resolve()
            allowed = (name in {"index.html", "game.js", "map-navigation.js", "island-effects.js", "style.css"}
                       or name.startswith("assets/") and path.is_relative_to(root / "assets"))
            if not allowed or not path.is_relative_to(root) or not path.is_file():
                self._json(404, {"error": "Not found"})
                return
            mime = ("text/javascript" if path.suffix == ".js" else
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            if mime.startswith("text/"):
                mime += "; charset=utf-8"
            self._send(200, path.read_bytes(), mime)

    def do_POST(self):
        route = urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 8192:
                raise ValueError("Request body must be at most 8 KB")
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object")
            if route == "/api/demo_item":
                self.app.demo_item(body.get("item"), body.get("label"))
                result = self.app.snapshot()
            elif route == "/api/demo_sort":
                event = self.app.demo_sort(body.get("category"))
                result = {"event": event, "state": self.app.snapshot()}
            elif route == "/api/confirm":
                event = self.app.confirm(body.get("bin"))
                result = {"event": event, "state": self.app.snapshot()}
            elif route == "/api/dismiss":
                self.app.dismiss()
                result = self.app.snapshot()
            elif route == "/api/project":
                self.app.game.choose_project(body.get("id"))
                result = self.app.snapshot()
            elif route == "/api/reset_scene":
                self.app.reset_scene()
                result = self.app.snapshot()
            elif route == "/api/reset_game":
                result = self.app.reset_game()
            else:
                self._json(404, {"error": "Not found"})
                return
            self._json(200, result)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Use manual items without camera or API key")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--database", type=Path, default=Path("game_state.sqlite3"))
    parser.add_argument("--location", default="StormHacks")
    parser.add_argument("--serial-port", help="CH340 device; auto-detected if omitted")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--frame-interval", type=float, default=0.4)
    parser.add_argument("--motors", action="store_true", help="Automatically route recognized items using A4988 motors")
    parser.add_argument("--motor-library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--motor-map", type=parse_motor_inputs, default=DEFAULT_MOTOR_INPUTS,
                        help="Category=input pairs; default: garbage=1,recycling=2,paper=3,compost=4")
    args = parser.parse_args()
    if not args.demo and not os.environ.get("GEMINI_API_KEY"):
        parser.error("Set GEMINI_API_KEY, or run with --demo")
    if args.frame_interval < 0:
        parser.error("--frame-interval cannot be negative")
    if args.demo and args.motors:
        parser.error("--motors requires live camera mode; demo mode never moves hardware")

    with ExitStack() as cleanup:
        game = GameStore(args.database, args.location)
        cleanup.callback(game.close)
        motor = None
        if args.motors:
            try:
                motor = MotorController(args.motor_library, args.motor_map)
                cleanup.callback(motor.close)
            except MotorError as error:
                parser.error(str(error))
        app = GameApp(game, args.demo, args.serial_port, args.baud,
                      args.model, args.frame_interval, motor)
        handler = type("StormHacksHandler", (Handler,), {"app": app})
        server = GameHTTPServer((args.host, args.port), handler)
        cleanup.callback(server.server_close)
        if motor:
            try:
                motor.initialize()
            except MotorError as error:
                parser.error(str(error))
        thread = None
        if not args.demo:
            thread = threading.Thread(target=app.run_camera, daemon=True)
            thread.start()
        print(f"StormHacks game at http://{args.host}:{args.port} ({'demo' if args.demo else 'camera'})")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            app.stop.set()
            if thread:
                thread.join(timeout=3)


if __name__ == "__main__":
    main()
