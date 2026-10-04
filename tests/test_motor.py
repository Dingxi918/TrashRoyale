import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from server.app import GameApp
from server.game import GameStore
from server.motor_controller import DEFAULT_MOTOR_INPUTS, MotorController, MotorError, parse_motor_inputs


ROOT = Path(__file__).resolve().parents[1]


class MotorMappingTests(unittest.TestCase):
    def test_custom_mapping_must_cover_each_bin_once(self):
        self.assertEqual(parse_motor_inputs("garbage=1,recycling=2,paper=3,compost=4"), DEFAULT_MOTOR_INPUTS)
        for bad in ("garbage=1", "garbage=1,recycling=1,paper=3,compost=4",
                    "garbage=1,recycling=2,paper=3,compost=4,garbage=2"):
            with self.subTest(mapping=bad), self.assertRaises(ValueError):
                parse_motor_inputs(bad)


@unittest.skipUnless(shutil.which("gcc"), "Native motor tests require gcc")
class NativeMotorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_directory = tempfile.TemporaryDirectory()
        cls.library_path = Path(cls.build_directory.name) / "libmotor-test.so"
        # Compile the production C source against GPIO and timing fakes.
        subprocess.run([
            "gcc", "-std=c11", "-D_DEFAULT_SOURCE", "-Wall", "-Wextra", "-Werror",
            "-fPIC", "-shared", "-Dusleep=fake_usleep", "-Dnanosleep=fake_nanosleep",
            "-I", str(ROOT / "tests/native"), str(ROOT / "hardware/motor/motor.c"),
            str(ROOT / "tests/native/fake_gpio.c"), "-o", str(cls.library_path),
        ], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build_directory.cleanup()

    def setUp(self):
        self.motor = MotorController(self.library_path)
        self.gpio = self.motor.library
        self.gpio.fake_reset()
        self.directory = tempfile.TemporaryDirectory()
        self.game = GameStore(Path(self.directory.name) / "state.sqlite3")

    def tearDown(self):
        self.motor.close()
        self.game.close()
        self.directory.cleanup()

    def test_routes_preserve_pulses_polarity_and_return_to_start(self):
        self.motor.initialize()
        expected = {1: {17: 1, 24: 0}, 2: {17: 1, 24: 1},
                    3: {17: 0, 5: 0}, 4: {17: 0, 5: 1}}
        travel_steps = {17: 25, 24: 39, 5: 39}
        for category, motor_input in DEFAULT_MOTOR_INPUTS.items():
            with self.subTest(category=category):
                self.gpio.fake_clear_log()
                self.assertEqual(self.motor.execute_category(category), motor_input)
                for pin, steps in travel_steps.items():
                    self.assertEqual(self.gpio.fake_pulses(pin), 2 * steps if pin in expected[motor_input] else 0)
                    if pin in expected[motor_input]:
                        self.assertEqual(self.gpio.fake_first_direction(pin), expected[motor_input][pin])
                        self.assertEqual(self.gpio.fake_direction_pulses(pin, 0), steps)
                        self.assertEqual(self.gpio.fake_direction_pulses(pin, 1), steps)
        self.motor.close()
        self.motor.close()
        self.assertEqual(self.gpio.fake_requested_count(), 0)

    def test_unknown_and_invalid_results_never_move(self):
        self.motor.initialize()
        app = GameApp(self.game, motor=self.motor)
        self.assertIsNone(app.handle_classification({"item": "unclear", "label": "unknown"}))
        self.assertEqual(self.gpio.motor_execute(5), 0)
        with self.assertRaises(ValueError):
            self.motor.execute_category("invalid")
        for pin in (17, 24, 5):
            self.assertEqual(self.gpio.fake_pulses(pin), 0)
        self.assertEqual(self.game.snapshot()["correct_sorts"], 0)

    def test_partial_initialization_releases_acquired_lines(self):
        self.gpio.fake_fail_request(24)
        with self.assertRaises(MotorError):
            self.motor.initialize()
        self.assertEqual(self.gpio.fake_requested_count(), 0)
        self.assertEqual(self.gpio.fake_bad_writes(), 0)

    def test_failed_motor_cycle_does_not_credit_or_retry(self):
        self.motor.initialize()
        app = GameApp(self.game, motor=self.motor)
        self.gpio.fake_fail_after_writes(5)
        with self.assertRaises(MotorError):
            app.handle_classification({"item": "can", "label": "recycling"})
        self.assertTrue(app.snapshot()["motor"]["faulted"])
        self.assertFalse(app.snapshot()["motor"]["routing"])
        self.assertEqual(app.pending["routing"], "failed")
        self.assertEqual(self.game.snapshot()["correct_sorts"], 0)
        pulses = self.gpio.fake_pulses(17)
        with self.assertRaises(MotorError):
            self.motor.execute_category("recycling")
        self.assertEqual(self.gpio.fake_pulses(17), pulses)

    def test_camera_routes_once_then_waits_for_scene_to_clear(self):
        self.motor.initialize()
        app = GameApp(self.game, motor=self.motor, frame_interval=0)
        empty, item = [20] * 30, [100] * 30
        frames = iter([empty] * 2 + [item] * 8 + [empty] * 4)

        def next_frame():
            try:
                return next(frames)
            except StopIteration:
                app.stop.set()
                return empty

        camera = Mock()
        camera.__enter__ = Mock(return_value=camera)
        camera.__exit__ = Mock(return_value=False)
        camera.read_jpeg.side_effect = next_frame
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             patch("google.genai.Client"), \
             patch("server.esp32_cam_rcv.Esp32SerialCamera", return_value=camera), \
             patch("server.app.thumbnail", side_effect=lambda frame: frame), \
             patch("server.gemini_classifier.classify_jpeg", return_value={"item": "can", "label": "recycling"}) as classify:
            app.run_camera()
        classify.assert_called_once()
        state = app.snapshot()
        self.assertEqual(state["correct_sorts"], 1)
        self.assertEqual(state["history"][0]["source"], "motor")
        self.assertEqual(state["history"][0]["motor_input"], 2)
        self.assertEqual(self.gpio.fake_pulses(17), 50)
        self.assertIsNone(state["pending"])
        with self.assertRaises(ValueError):
            app.confirm("recycling")

    def test_unknown_scene_clears_before_accepting_next_item(self):
        self.motor.initialize()
        app = GameApp(self.game, motor=self.motor, frame_interval=0)
        empty, item = [20] * 30, [100] * 30
        frames = iter([empty] * 2 + [item] * 8 + [empty] * 4 + [item] * 8 + [empty] * 4)

        def next_frame():
            try:
                return next(frames)
            except StopIteration:
                app.stop.set()
                return empty

        camera = Mock()
        camera.__enter__ = Mock(return_value=camera)
        camera.__exit__ = Mock(return_value=False)
        camera.read_jpeg.side_effect = next_frame
        results = [{"item": "unclear", "label": "unknown"}, {"item": "paper", "label": "paper"}]
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             patch("google.genai.Client"), \
             patch("server.esp32_cam_rcv.Esp32SerialCamera", return_value=camera), \
             patch("server.app.thumbnail", side_effect=lambda frame: frame), \
             patch("server.gemini_classifier.classify_jpeg", side_effect=results) as classify:
            app.run_camera()
        self.assertEqual(classify.call_count, 2)
        self.assertEqual(self.game.snapshot()["correct_sorts"], 1)
        self.assertEqual(self.game.snapshot()["history"][0]["motor_input"], 3)
        self.assertEqual(self.gpio.fake_pulses(17), 50)
        self.assertEqual(self.gpio.fake_pulses(5), 78)
        self.assertEqual(self.gpio.fake_pulses(24), 0)


if __name__ == "__main__":
    unittest.main()
