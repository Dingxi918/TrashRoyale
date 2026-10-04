import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import Mock, patch

from server.app import GameApp, main


class SceneDetectionTests(unittest.TestCase):
    def setUp(self):
        self.game = Mock()
        self.game.snapshot.side_effect = lambda: {}
        self.app = GameApp(self.game, frame_interval=0)
        self.app.camera_connected = True
        self.empty = [20] * (64 * 48)
        self.item = [100] * len(self.empty)

    def watch(self, pixels):
        """Run synthetic captures with a fake classifier; no device or API access."""
        frames = [f"frame-{index}".encode() for index in range(len(pixels))]
        thumbnails = dict(zip(frames, pixels))
        position = [0]
        self.app.stop.clear()

        def read():
            if position[0] == len(frames):
                self.app.stop.set()
                return b"ignored-after-stop"
            jpeg = frames[position[0]]
            position[0] += 1
            return jpeg

        camera = Mock()
        camera.read_jpeg.side_effect = read
        classifier = Mock(return_value={"item": "can", "label": "recycling"})
        with patch("server.app.thumbnail", side_effect=thumbnails.__getitem__):
            self.app._watch_camera(camera, Mock(), classifier)
        return classifier

    def test_static_empty_background_never_calls_classifier(self):
        self.watch([self.empty] * 12).assert_not_called()
        state = self.app.snapshot()
        self.assertEqual(state["classification_gate"], "no_scene_change")
        self.assertEqual(state["scene"]["reference_difference"], 0)
        self.assertEqual(state["scene"]["stable_count"], 0)
        self.assertFalse(state["scene"]["occupied"])

    def test_scene_in_motion_never_calls_classifier(self):
        moving = [130] * len(self.empty)
        self.watch([self.empty] + [self.item, moving] * 6).assert_not_called()
        state = self.app.snapshot()
        self.assertEqual(state["classification_gate"], "scene_moving")
        self.assertEqual(state["scene"]["motion_difference"], 30)
        self.assertTrue(state["scene"]["item_present"])
        self.assertFalse(state["scene"]["settled"])

    def test_contaminated_reference_requires_empty_reference_reset(self):
        self.watch([self.item] * 12).assert_not_called()
        self.assertEqual(self.app.snapshot()["classification_gate"], "no_scene_change")
        self.app.reset_scene()
        self.watch([self.empty] + [self.item] * 5).assert_called_once()
        self.assertEqual(self.app.snapshot()["classification_gate"], "pending_item")

    def test_one_classification_per_item_until_three_empty_frames(self):
        self.watch([self.empty] + [self.item] * 12).assert_called_once()
        self.assertEqual(self.app.pending["label"], "recycling")
        self.game.record_sort.assert_not_called()
        self.app.dismiss()
        self.watch([self.item] * 6).assert_not_called()
        state = self.app.snapshot()
        self.assertEqual(state["classification_gate"], "waiting_for_area_to_clear")
        self.assertEqual(state["scene"]["phase"], "waiting_for_area_to_clear")
        self.assertEqual(state["scene"]["progress_count"], 0)
        self.watch([self.empty] * 2).assert_not_called()
        state = self.app.snapshot()
        self.assertEqual(state["scene"]["progress_count"], 2)
        self.assertEqual(state["scene"]["progress_frames_required"], 3)
        self.assertIn("(2/3)", state["status"])
        self.watch([self.item] * 5).assert_not_called()
        self.watch([self.empty] * 3 + [self.item] * 5).assert_called_once()

    def test_snapshot_measurements_and_detection_gate_match_latest_frame(self):
        self.assertEqual(self.app.snapshot()["classification_gate"], "no_empty_reference")
        self.app.detector.observe(self.empty)
        self.app.detector.observe(self.item)
        state = self.app.snapshot()
        self.assertEqual(state["classification_gate"], "scene_moving")
        self.assertEqual(state["scene"]["reference_difference"], 80)
        self.assertEqual(state["scene"]["motion_difference"], 80)
        self.assertEqual(state["scene"]["presence_threshold"], 11)
        self.assertEqual(state["scene"]["motion_threshold"], 4)
        self.assertEqual(state["scene"]["stable_frames_required"], 3)

        self.app.detector.observe(self.item)
        state = self.app.snapshot()
        self.assertEqual(state["classification_gate"], "waiting_for_stable_frames")
        self.assertEqual(state["scene"]["motion_difference"], 0)
        self.assertEqual(state["scene"]["stable_count"], 1)
        self.assertTrue(state["scene"]["settled"])
        self.app.reset_scene()
        state = self.app.snapshot()
        self.assertEqual(state["classification_gate"], "no_empty_reference")
        self.assertFalse(state["scene"]["has_reference"])
        self.assertIsNone(state["scene"]["reference_difference"])
        self.assertIsNone(state["scene"]["motion_difference"])

    def small_item(self):
        pixels = self.empty.copy()
        for y in range(12, 20):
            for x in range(20, 28):
                pixels[y * 64 + x] = 120
        return pixels

    def test_localized_item_below_global_threshold_does_not_trigger(self):
        self.watch([self.empty] + [self.small_item()] * 12).assert_not_called()
        state = self.app.snapshot()
        self.assertEqual(state["scene"]["reference_difference"], 2.08)
        self.assertFalse(state["scene"]["item_present"])
        self.assertEqual(state["classification_gate"], "no_scene_change")

    def test_explicit_calibrated_thresholds_detect_small_still_item_once(self):
        self.app = GameApp(self.game, frame_interval=0, presence_threshold=2,
                           motion_threshold=1)
        self.app.camera_connected = True
        self.watch([self.empty] + [self.small_item()] * 12).assert_called_once()
        state = self.app.snapshot()
        self.assertEqual(state["scene"]["presence_threshold"], 2)
        self.assertEqual(state["scene"]["motion_threshold"], 1)

    def test_gate_prioritizes_processing_states_over_detector_state(self):
        self.app.detector.observe(self.empty)
        for attribute, value, expected in (
            ("demo", True, "demo_mode"),
            ("camera_connected", False, "camera_disconnected"),
            ("motor_fault", True, "motor_fault"),
            ("routing", True, "motor_routing"),
            ("pending", {"item": "can", "label": "recycling"}, "pending_item"),
            ("classifying", True, "classification_in_progress"),
        ):
            with self.subTest(attribute=attribute):
                original = getattr(self.app, attribute)
                setattr(self.app, attribute, value)
                self.assertEqual(self.app.snapshot()["classification_gate"], expected)
                setattr(self.app, attribute, original)

    def test_invalid_calibration_arguments_fail_before_opening_store_or_server(self):
        for option, value in (
            ("--presence-threshold", "0"),
            ("--presence-threshold", "256"),
            ("--presence-threshold", "nan"),
            ("--presence-threshold", "inf"),
            ("--motion-threshold", "-1"),
            ("--motion-threshold", "256"),
            ("--motion-threshold", "nan"),
            ("--motion-threshold", "inf"),
        ):
            with self.subTest(option=option, value=value), \
                 patch.object(sys, "argv", ["server.app", "--demo", option, value]), \
                 patch("server.app.logging.basicConfig"), \
                 patch("server.app.GameStore") as store, \
                 redirect_stderr(StringIO()) as error:
                with self.assertRaises(SystemExit) as exit:
                    main()
                self.assertEqual(exit.exception.code, 2)
                self.assertIn(option, error.getvalue())
                store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
