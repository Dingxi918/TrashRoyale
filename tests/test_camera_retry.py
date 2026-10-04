import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from google.genai.errors import APIError

from server.app import GameApp
from server.game import CATEGORIES, GameStore
from server.gemini_classifier import classify_jpeg
from server.motor_controller import DEFAULT_MOTOR_INPUTS, MotorError


def api_error(code):
    return APIError(code, {"error": {"code": code, "message": "Temporary test error"}})


class CameraRetryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = GameStore(Path(self.directory.name) / "state.sqlite3")
        self.app = GameApp(self.store, frame_interval=0)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def watch(self, pixels, outcomes, before_read=None, seconds_per_frame=1):
        """Run only fake captures and fake classifications against a simulated clock."""
        clock = [0.0]
        frames = [f"frame-{index}".encode() for index in range(len(pixels))]
        thumbnails = {jpeg: [value] * 30 for jpeg, value in zip(frames, pixels)}
        position = [0]
        calls = []
        outcomes = iter(outcomes)

        def read():
            index = position[0]
            if before_read:
                before_read(index)
            if index == len(frames):
                self.app.stop.set()
                return frames[-1]
            position[0] += 1
            clock[0] = index * seconds_per_frame
            return frames[index]

        def classify(jpeg, labels, client, model):
            self.assertEqual(labels, CATEGORIES)
            calls.append((jpeg, clock[0]))
            result = next(outcomes)
            if isinstance(result, Exception):
                raise result
            return result

        camera = Mock()
        camera.read_jpeg.side_effect = read
        with patch("server.app.thumbnail", side_effect=thumbnails.__getitem__), \
             patch("server.app.time.monotonic", side_effect=lambda: clock[0]), \
             patch("server.app.random.uniform", return_value=0):
            self.app._watch_camera(camera, Mock(), classify)
        return calls

    def test_transient_failure_retries_with_fresh_frame_then_leaves_one_pending_item(self):
        calls = self.watch([20] * 2 + [100] * 20, [
            api_error(503), {"item": "can", "label": "recycling"},
        ])
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0][0], calls[1][0])
        self.assertGreaterEqual(calls[1][1] - calls[0][1], 2)
        self.assertEqual(self.app.pending["label"], "recycling")
        self.assertEqual(self.store.snapshot()["correct_sorts"], 0)
        self.assertFalse(self.app.classifying)
        self.assertIsNone(self.app.error)

    def test_repeated_failures_are_bounded_and_back_off(self):
        calls = self.watch([20] * 2 + [100] * 80, [api_error(503)] * 3,
                           seconds_per_frame=0.5)
        self.assertEqual(len(calls), 3)
        self.assertGreaterEqual(calls[1][1] - calls[0][1], 2)
        self.assertGreaterEqual(calls[2][1] - calls[1][1], 4)
        self.assertEqual(len({jpeg for jpeg, _ in calls}), 3)
        self.assertIn("clear", self.app.status.lower())
        self.assertFalse(self.app.classifying)
        self.assertIsNone(self.app.pending)

    def test_latest_frame_updates_during_backoff_without_successful_classification(self):
        observed = []

        def inspect(index):
            if index == 7:
                state = self.app.snapshot()
                self.assertTrue(state["classifying"])
                self.assertTrue(state["has_frame"])
                self.assertIsNone(state["last_classification"])
                self.assertEqual(self.app.latest_jpeg, b"frame-6")
                observed.append(True)

        calls = self.watch([20] * 2 + [100] * 5, [api_error(503)], before_read=inspect)
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0][0], self.app.latest_jpeg)
        self.assertEqual(observed, [True])
        self.assertTrue(self.app.snapshot()["has_frame"])

    def test_quota_and_bad_request_errors_do_not_retry(self):
        for code in (429, 400):
            with self.subTest(code=code):
                self.app = GameApp(self.store, frame_interval=0)
                calls = self.watch([20] * 2 + [100] * 30, [api_error(code)])
                self.assertEqual(len(calls), 1)
                self.assertFalse(self.app.classifying)
                self.assertIsNone(self.app.pending)

    def test_supported_transient_statuses_retry(self):
        for code in (408, 500, 502, 503, 504):
            with self.subTest(code=code):
                self.app = GameApp(self.store, frame_interval=0)
                calls = self.watch([20] * 2 + [100] * 20, [
                    api_error(code), {"item": "sheet", "label": "paper"},
                ])
                self.assertEqual(len(calls), 2)

    def test_first_empty_frame_cancels_retry_even_before_clear_event(self):
        canceled = []

        def inspect(index):
            if index == 7:
                canceled.append(not self.app.classifying)
                self.assertTrue(self.app.detector.occupied)

        calls = self.watch([20] * 2 + [100] * 4 + [20] + [100] * 20,
                           [api_error(503)], before_read=inspect)
        self.assertEqual(len(calls), 1)
        self.assertEqual(canceled, [True])
        self.assertIsNone(self.app.pending)

    def test_retry_waits_for_three_fresh_settled_frames_after_motion(self):
        pixels = [20] * 2 + [100] * 4 + [130, 100] * 4 + [130] + [100] * 4
        calls = self.watch(pixels, [
            api_error(503), {"item": "can", "label": "recycling"},
        ])
        self.assertEqual(len(calls), 2)
        self.assertGreaterEqual(calls[1][1], 18)

    def test_resets_are_blocked_while_retry_is_pending(self):
        checked = []
        original_seed = self.store.snapshot()["map_seed"]

        def inspect(index):
            if index == 6:
                self.assertTrue(self.app.classifying)
                with self.assertRaises(ValueError):
                    self.app.reset_scene()
                with self.assertRaises(ValueError):
                    self.app.reset_game()
                checked.append(True)

        self.watch([20] * 2 + [100] * 20, [
            api_error(503), {"item": "can", "label": "recycling"},
        ], before_read=inspect)
        self.assertEqual(checked, [True])
        self.assertEqual(self.store.snapshot()["map_seed"], original_seed)

    def test_shutdown_clears_pending_retry_state(self):
        calls = self.watch([20] * 2 + [100] * 4, [api_error(503)])
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.app.classifying)

    def test_disconnect_clears_pending_retry_state(self):
        def disconnect(index):
            if index == 6:
                raise OSError("Test camera disconnected")

        with self.assertRaisesRegex(OSError, "disconnected"):
            self.watch([20] * 2 + [100] * 20, [api_error(503)], before_read=disconnect)
        self.assertFalse(self.app.classifying)

    def test_retry_budget_restarts_after_clear_and_each_motor_route_is_once(self):
        motor = Mock(inputs=DEFAULT_MOTOR_INPUTS)
        motor.execute_category.side_effect = lambda category: DEFAULT_MOTOR_INPUTS[category]
        self.app = GameApp(self.store, frame_interval=0, motor=motor)
        calls = self.watch([20] * 2 + [100] * 20 + [20] * 4 + [100] * 20, [
            api_error(503), api_error(503), {"item": "can", "label": "recycling"},
            api_error(503), api_error(503), {"item": "sheet", "label": "paper"},
        ])
        self.assertEqual(len(calls), 6)
        self.assertEqual(motor.execute_category.call_count, 2)
        self.assertEqual(self.store.snapshot()["correct_sorts"], 2)
        self.assertIsNone(self.app.pending)

    def test_motor_failure_after_retry_does_not_repeat_classification_or_motion(self):
        motor = Mock(inputs=DEFAULT_MOTOR_INPUTS)
        motor.execute_category.side_effect = MotorError("Test partial motor cycle")
        self.app = GameApp(self.store, frame_interval=0, motor=motor)
        calls = self.watch([20] * 2 + [100] * 30, [
            api_error(503), {"item": "can", "label": "recycling"},
        ])
        self.assertEqual(len(calls), 2)
        motor.execute_category.assert_called_once_with("recycling")
        self.assertTrue(self.app.motor_fault)
        self.assertEqual(self.app.pending["routing"], "failed")
        self.assertEqual(self.store.snapshot()["correct_sorts"], 0)


class ClassifierRetryConfigurationTests(unittest.TestCase):
    def test_sdk_retry_is_disabled_so_camera_budget_counts_actual_requests(self):
        client = Mock()
        client.models.generate_content.return_value.text = '{"item":"can","label":"recycling"}'
        result = classify_jpeg(b"\xff\xd8test\xff\xd9", CATEGORIES, client)
        self.assertEqual(result, {"item": "can", "label": "recycling"})
        client.models.generate_content.assert_called_once()
        config = client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.http_options.retry_options.attempts, 1)
        self.assertEqual(config.http_options.timeout, 30_000)


if __name__ == "__main__":
    unittest.main()
