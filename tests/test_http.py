import json
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server.app import GameApp, GameHTTPServer, Handler
from server.game import GameStore


class HttpGameTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.game = GameStore(Path(self.directory.name) / "game.sqlite3",
                              today=lambda: date(2026, 10, 3))
        handler = type("TestHandler", (Handler,), {"app": GameApp(self.game, demo=True),
                                                   "log_message": lambda *args: None})
        self.server = GameHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:{}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.game.close()
        self.directory.cleanup()

    def post(self, path, data):
        body = json.dumps(data).encode()
        request = Request(self.base + path, body,
                          {"Content-Type": "application/json"})
        with urlopen(request) as response:
            return json.load(response)

    def test_demo_flow_and_duplicate_confirmation_guard(self):
        with urlopen(self.base + "/") as response:
            self.assertIn(b"Trash Royale", response.read())
        self.post("/api/demo_item", {"item": "apple core", "label": "compost"})
        with urlopen(self.base + "/api/state") as response:
            self.assertEqual(json.load(response)["pending"]["item"], "apple core")
        result = self.post("/api/confirm", {"bin": "compost"})
        self.assertTrue(result["event"]["correct"])
        self.assertEqual(result["state"]["total"]["compost"], 1)
        with self.assertRaises(HTTPError) as error:
            self.post("/api/confirm", {"bin": "compost"})
        self.assertEqual(error.exception.code, 400)

    def test_frontend_assets_and_repository_files_are_not_exposed(self):
        for path, mime in (("/game.js", "text/javascript"),
                           ("/map-navigation.js", "text/javascript"),
                           ("/island-effects.js", "text/javascript"),
                           ("/style.css?v=1", "text/css"),
                           ("/assets/cliffs/floating_island_rock.png", "image/png"),
                           ("/assets/background/full_landscape.png", "image/png"),
                           ("/assets/ui/icon_paper.png", "image/png")):
            with self.subTest(path=path), urlopen(self.base + path) as response:
                self.assertEqual(response.headers.get_content_type(), mime)
                self.assertTrue(response.read())
        for path in ("/app.js", "/README.md", "/server/app.py", "/game_state.sqlite3",
                     "/assets/../../server/app.py", "/assets/%2e%2e/README.md",
                     "/assets/%00.png", "/assets/missing.png"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 404)

    def test_demo_buttons_and_project_selection_share_backend_state(self):
        first = self.game.snapshot()["queue"][1]
        selected = self.post("/api/project", {"id": first["id"]})
        self.assertEqual(selected["active_id"], first["id"])
        self.assertEqual(len(selected["queue"]), 8)
        self.assertEqual(selected["mode"], "demo")
        self.assertFalse(selected["motor"]["enabled"])
        for category in ("recycling", "compost", "paper", "garbage"):
            result = self.post("/api/demo_sort", {"category": category})
            self.assertEqual(result["state"]["total"][category], 1)
            self.assertEqual(result["event"]["project"], first["name"])
            self.assertIsNone(result["state"]["pending"])
        with urlopen(self.base + "/api/state") as response:
            state = json.load(response)
        self.assertEqual(state["correct_sorts"], 4)
        self.assertEqual(state["queue"][1]["progress"], dict.fromkeys(state["total"], 1))

    def test_demo_sort_coexists_with_pending_items_and_live_confirmation(self):
        self.post("/api/demo_item", {"item": "can", "label": "recycling"})
        pending = self.server.RequestHandlerClass.app.snapshot()
        simulated = self.post("/api/demo_sort", {"category": "recycling"})
        self.assertEqual(simulated["event"]["source"], "demo")
        self.assertEqual(simulated["state"]["correct_sorts"], 1)
        self.assertEqual(simulated["state"]["pending"], pending["pending"])
        self.assertEqual(simulated["state"]["status"], pending["status"])
        confirmed = self.post("/api/confirm", {"bin": "recycling"})
        self.assertEqual(confirmed["state"]["correct_sorts"], 2)
        self.assertIsNone(confirmed["state"]["pending"])

        app = self.server.RequestHandlerClass.app
        app.demo = False
        app.handle_classification({"item": "newspaper", "label": "paper"})
        camera = app.snapshot()
        simulated = self.post("/api/demo_sort", {"category": "paper"})
        self.assertEqual(simulated["state"]["correct_sorts"], 3)
        for key in ("pending", "status", "error", "classifying", "last_classification", "motor"):
            self.assertEqual(simulated["state"][key], camera[key])
        confirmed = self.post("/api/confirm", {"bin": "paper"})
        self.assertEqual(confirmed["event"]["source"], "camera")
        self.assertEqual(confirmed["state"]["correct_sorts"], 4)
        self.assertEqual(confirmed["state"]["total"]["paper"], 2)
        with self.assertRaises(HTTPError) as error:
            self.post("/api/confirm", {"bin": "paper"})
        self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError) as error:
            self.post("/api/demo_item", {"item": "leaf", "label": "compost"})
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.game.snapshot()["correct_sorts"], 4)

    def test_game_reset_is_shared_persistent_and_clears_pending_item(self):
        self.post("/api/demo_sort", {"category": "paper"})
        self.post("/api/demo_item", {"item": "can", "label": "recycling"})
        old = self.server.RequestHandlerClass.app.snapshot()
        fresh = self.post("/api/reset_game", {})
        self.assertIsNone(fresh["pending"])
        self.assertIsNone(fresh["last_classification"])
        self.assertEqual(fresh["correct_sorts"], 0)
        self.assertFalse(any(fresh["total"].values()))
        self.assertEqual(len(fresh["queue"]), 8)
        self.assertNotEqual(fresh["map_seed"], old["map_seed"])
        with urlopen(self.base + "/api/state") as response:
            self.assertEqual(json.load(response), fresh)
        reopened = GameStore(self.game.path, today=lambda: date(2026, 10, 3))
        try:
            self.assertEqual(reopened.snapshot(), self.game.snapshot())
        finally:
            reopened.close()
        with self.assertRaises(HTTPError) as error:
            self.post("/api/project", {"id": old["queue"][0]["id"]})
        self.assertEqual(error.exception.code, 400)

    def test_game_reset_rejects_busy_camera_or_motors_without_changing_state(self):
        app = self.server.RequestHandlerClass.app
        app.demo = False
        for flag in ("classifying", "routing"):
            with self.subTest(flag=flag):
                setattr(app, flag, True)
                previous = app.snapshot()
                with self.assertRaises(HTTPError) as error:
                    self.post("/api/reset_game", {})
                self.assertEqual(error.exception.code, 400)
                self.assertEqual(app.snapshot(), previous)
                setattr(app, flag, False)


if __name__ == "__main__":
    unittest.main()
