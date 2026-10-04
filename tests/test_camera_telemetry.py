import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from server.app import GameApp


class CameraTelemetryTests(unittest.TestCase):
    def setUp(self):
        game = Mock()
        game.snapshot.side_effect = lambda: {}
        self.app = GameApp(game, frame_interval=0)

    def camera(self, read):
        camera = Mock(port="/dev/fake-camera")
        camera.__enter__ = Mock(return_value=camera)
        camera.__exit__ = Mock(return_value=False)
        camera.read_jpeg.side_effect = read
        return camera

    def test_initial_state_distinguishes_no_frame_from_connected_camera(self):
        state = self.app.snapshot()
        self.assertFalse(state["has_frame"])
        self.assertFalse(state["camera_connected"])
        self.assertEqual(state["frame_count"], 0)
        self.assertIsNone(state["frame_age_seconds"])

    def test_frame_count_and_age_track_successfully_decoded_frames(self):
        clock = [0.0]
        frames = iter([(10.0, b"first"), (13.0, b"second")])

        def read():
            try:
                clock[0], jpeg = next(frames)
                return jpeg
            except StopIteration:
                self.app.stop.set()
                return b"ignored-after-stop"

        with patch("server.app.thumbnail", return_value=[20] * 30), \
             patch("server.app.time.monotonic", side_effect=lambda: clock[0]):
            self.app._watch_camera(self.camera(read), Mock(), Mock())
            clock[0] = 17.0
            state = self.app.snapshot()
        self.assertTrue(state["has_frame"])
        self.assertEqual(state["frame_count"], 2)
        self.assertEqual(state["frame_age_seconds"], 4.0)
        self.assertEqual(self.app.latest_jpeg, b"second")
        self.assertEqual(state["status"], "Camera ready; place one item in the sorting area")

    def test_invalid_image_does_not_report_a_successful_capture(self):
        with patch("server.app.thumbnail", side_effect=ValueError("Invalid test JPEG")):
            with self.assertRaisesRegex(ValueError, "Invalid test JPEG"):
                self.app._watch_camera(self.camera(lambda: b"invalid"), Mock(), Mock())
        state = self.app.snapshot()
        self.assertEqual(state["frame_count"], 0)
        self.assertIsNone(state["frame_age_seconds"])
        self.assertFalse(state["has_frame"])

    def test_capture_logs_are_periodic_instead_of_every_frame(self):
        clock = [0.0]
        positions = iter(range(26))

        def read():
            try:
                clock[0] = float(next(positions))
                return b"frame"
            except StopIteration:
                self.app.stop.set()
                return b"ignored"

        with patch("server.app.thumbnail", return_value=[20] * 30), \
             patch("server.app.time.monotonic", side_effect=lambda: clock[0]), \
             self.assertLogs("server.app", level="INFO") as logs:
            self.app._watch_camera(self.camera(read), Mock(), Mock())
        self.assertEqual(self.app.frame_count, 26)
        self.assertEqual(len(logs.output), 3)
        self.assertIn("empty-area reference", logs.output[0])
        self.assertIn("Camera frame 11 received", logs.output[1])
        self.assertIn("Camera frame 21 received", logs.output[2])

    def test_disconnect_reports_closed_connection_and_preserves_cached_frame(self):
        clock = [10.0]
        captures = [0]
        observed = []

        def read():
            self.assertTrue(self.app.snapshot()["camera_connected"])
            captures[0] += 1
            if captures[0] == 1:
                return b"last-good-frame"
            clock[0] = 15.0
            raise OSError("Test camera unplugged")

        def wait(delay):
            if delay == 2:
                observed.append(self.app.snapshot())
                self.app.stop.set()
            return self.app.stop.is_set()

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             patch("google.genai.Client"), \
             patch("server.esp32_cam_rcv.Esp32SerialCamera", return_value=self.camera(read)), \
             patch("server.app.thumbnail", return_value=[20] * 30), \
             patch("server.app.time.monotonic", side_effect=lambda: clock[0]), \
             patch.object(self.app.stop, "wait", side_effect=wait), \
             self.assertLogs("server.app", level="ERROR"):
            self.app.run_camera()
        self.assertEqual(len(observed), 1)
        self.assertFalse(observed[0]["camera_connected"])
        self.assertTrue(observed[0]["has_frame"])
        self.assertEqual(observed[0]["frame_count"], 1)
        self.assertEqual(observed[0]["frame_age_seconds"], 5.0)
        self.assertIn("unplugged", observed[0]["error"])
        self.assertFalse(self.app.camera_connected)

    def test_normal_shutdown_marks_serial_connection_closed(self):
        def read():
            self.assertTrue(self.app.camera_connected)
            self.app.stop.set()
            return b"ignored-after-stop"

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             patch("google.genai.Client"), \
             patch("server.esp32_cam_rcv.Esp32SerialCamera", return_value=self.camera(read)):
            self.app.run_camera()
        self.assertFalse(self.app.camera_connected)

    def jpeg(self, shade):
        output = BytesIO()
        Image.new("RGB", (64, 48), (shade, shade, shade)).save(output, format="JPEG")
        return output.getvalue()

    def watch_frames(self, frames):
        frames = iter(frames)

        def read():
            try:
                return next(frames)
            except StopIteration:
                self.app.stop.set()
                return b"ignored-after-stop"

        classifier = Mock()
        self.app._watch_camera(self.camera(read), Mock(), classifier)
        classifier.assert_not_called()

    def test_saved_frames_replace_only_complete_images_and_latest_bytes_win(self):
        first, second = self.jpeg(20), self.jpeg(21)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.jpg"
            path.write_bytes(b"previous-image")
            self.app.save_latest = path
            previous = [b"previous-image", first]
            upcoming = [first, second]
            replace = os.replace
            publications = []

            def publish(source, destination):
                index = len(publications)
                self.assertEqual(path.read_bytes(), previous[index])
                self.assertEqual(Path(source).read_bytes(), upcoming[index])
                replace(source, destination)
                publications.append(path.read_bytes())

            with patch("server.app.os.replace", side_effect=publish):
                self.watch_frames([first, second])
            self.assertEqual(publications, [first, second])
            self.assertEqual(path.read_bytes(), second)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            self.assertIsNone(self.app.snapshot()["frame_save_error"])

    def test_failed_file_publication_keeps_old_file_and_live_capture_running(self):
        jpeg = self.jpeg(20)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.jpg"
            path.write_bytes(b"previous-image")
            self.app.save_latest = path
            with patch("server.app.os.replace", side_effect=PermissionError("Test disk error")), \
                 self.assertLogs("server.app", level="ERROR"):
                self.watch_frames([jpeg])
            self.assertEqual(path.read_bytes(), b"previous-image")
            self.assertEqual(list(Path(directory).iterdir()), [path])
            self.assertEqual(self.app.latest_jpeg, jpeg)
            state = self.app.snapshot()
            self.assertEqual(state["frame_count"], 1)
            self.assertIn("Test disk error", state["frame_save_error"])
            self.assertIsNone(state["error"])
            self.assertIn("Camera ready", state["status"])

            # A later successful save clears only its own diagnostic error.
            self.app.error = "Existing Gemini error"
            with self.assertLogs("server.app", level="INFO"):
                self.app._save_latest_frame(jpeg)
            self.assertEqual(path.read_bytes(), jpeg)
            self.assertIsNone(self.app.snapshot()["frame_save_error"])
            self.assertEqual(self.app.error, "Existing Gemini error")

    def test_invalid_image_does_not_overwrite_saved_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.jpg"
            original = self.jpeg(20)
            path.write_bytes(original)
            self.app.save_latest = path
            with self.assertRaises(OSError):
                self.watch_frames([b"invalid-image"])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(self.app.frame_count, 0)


if __name__ == "__main__":
    unittest.main()
