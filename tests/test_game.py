import copy
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

from server.app import GameApp
from server.game import CATEGORIES, GameStore, is_complete, make_queue
from server.scene_detector import SceneDetector


class GameTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "state.sqlite3"
        self.day = date(2026, 10, 3)
        self.store = GameStore(self.path, today=lambda: self.day)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_queue_is_stable_and_sort_requires_correct_bin(self):
        state = self.store.snapshot()
        self.assertEqual(len(state["queue"]), 8)
        self.assertEqual(
            [p["required"] for p in state["queue"]],
            [p["required"] for p in make_queue("StormHacks", "2026-10-03")],
        )
        app = GameApp(self.store, demo=True)
        app.demo_item("can", "recycling")
        wrong = app.confirm("garbage")
        self.assertFalse(wrong["correct"])
        self.assertEqual(self.store.snapshot()["correct_sorts"], 0)
        with self.assertRaises(ValueError):
            app.confirm("recycling")
        app.demo_item("can", "recycling")
        right = app.confirm("recycling")
        self.assertTrue(right["correct"])
        self.assertEqual(self.store.snapshot()["total"]["recycling"], 1)

    def test_resource_overflow_completion_and_persistence(self):
        first = self.store.snapshot()["queue"][0]
        for category in CATEGORIES:
            for _ in range(first["required"][category]):
                self.store.record_sort("test item", category, category, "demo")
        state = self.store.snapshot()
        self.assertTrue(is_complete(state["queue"][0]))
        self.assertEqual(state["active_id"], state["queue"][1]["id"])
        self.assertEqual(len(state["completed"]), 1)
        event = self.store.record_sort("extra", "recycling", "recycling", "demo")
        self.assertEqual(event["project"], state["queue"][1]["name"])
        for project in self.store.snapshot()["queue"][1:]:
            for category in CATEGORIES:
                remaining = project["required"][category] - project["progress"][category]
                for _ in range(remaining):
                    self.store.record_sort("test item", category, category, "demo")
        scenery = self.store.record_sort("leaf", "compost", "compost", "demo")
        self.assertEqual(scenery["project"], "City environment")
        self.assertEqual(self.store.snapshot()["decorations"]["compost"], 1)
        saved_count = self.store.snapshot()["correct_sorts"]
        other = GameStore(self.path, today=lambda: self.day)
        try:
            self.assertEqual(other.snapshot()["correct_sorts"], saved_count)
        finally:
            other.close()

    def test_daily_queue_changes_but_completed_city_remains(self):
        self.store.state["completed"].append(self.store.state["queue"][0].copy())
        self.store._save()
        self.day = date(2026, 10, 4)
        state = self.store.snapshot()
        self.assertEqual(state["day"], "2026-10-04")
        self.assertEqual(len(state["completed"]), 1)
        self.assertEqual(len(state["queue"]), 8)
        self.assertEqual(
            [p["id"] for p in state["queue"]],
            [p["id"] for p in make_queue("StormHacks", "2026-10-04")],
        )

    def test_existing_short_save_expands_without_losing_progress(self):
        self.store.record_sort("can", "recycling", "recycling", "demo")
        self.store.state["queue"] = self.store.state["queue"][:3]
        self.store.state["active_id"] = self.store.state["queue"][2]["id"]
        previous = copy.deepcopy(self.store.state)
        self.store._save()
        self.store.close()
        self.store = GameStore(self.path, today=lambda: self.day)

        state = self.store.snapshot()
        self.assertEqual(len(state["queue"]), 8)
        self.assertEqual(self.store.state["queue"][:3], previous["queue"])
        for key in previous.keys() - {"queue"}:
            self.assertEqual(self.store.state[key], previous[key])
        self.assertEqual(len({project["id"] for project in state["queue"]}), 8)
        self.assertEqual(len({project["kind"] for project in state["queue"]}), 8)
        self.assertTrue(all(not any(project["progress"].values())
                            for project in state["queue"][3:]))

        other = GameStore(self.path, today=lambda: self.day)
        try:
            self.assertEqual(other.snapshot(), state)
        finally:
            other.close()

    def test_completed_short_queue_selects_an_added_project(self):
        self.store.state["queue"] = self.store.state["queue"][:3]
        for project in self.store.state["queue"]:
            project["progress"] = dict(project["required"])
        self.store.state["completed"] = copy.deepcopy(self.store.state["queue"])
        self.store.state["active_id"] = None
        self.store._save()

        state = self.store.snapshot()
        self.assertEqual(len(state["queue"]), 8)
        self.assertEqual(len(state["completed"]), 3)
        self.assertEqual(state["active_id"], state["queue"][3]["id"])
        self.assertTrue(all(project["complete"] for project in state["queue"][:3]))

    def test_reset_clears_completed_city_resources_and_history_and_persists(self):
        # Start with a completed city, then earn scenery and record a wrong sort.
        for project in self.store.state["queue"]:
            project["progress"] = dict(project["required"])
        self.store.state["completed"] = copy.deepcopy(self.store.state["queue"])
        self.store.state["total"] = {
            category: sum(project["required"][category] for project in self.store.state["queue"])
            for category in CATEGORIES
        }
        self.store.state["correct_sorts"] = sum(self.store.state["total"].values())
        self.store.state["active_id"] = None
        self.store.record_sort("leaf", "compost", "compost", "demo")
        self.store.record_sort("can", "recycling", "garbage", "demo")
        old = self.store.snapshot()
        self.assertTrue(old["completed"])
        self.assertEqual(old["decorations"]["compost"], 1)
        self.assertTrue(old["history"])

        fresh = self.store.reset()
        self.assertEqual(fresh["completed"], [])
        self.assertEqual(fresh["history"], [])
        self.assertEqual(fresh["correct_sorts"], 0)
        self.assertEqual(fresh["total"], dict.fromkeys(CATEGORIES, 0))
        self.assertEqual(fresh["decorations"], dict.fromkeys(CATEGORIES, 0))
        self.assertEqual(len(fresh["queue"]), 8)
        self.assertEqual(len({project["kind"] for project in fresh["queue"]}), 8)
        self.assertTrue(all(project["percent"] == 0 and not project["complete"]
                            for project in fresh["queue"]))
        self.assertEqual(fresh["active_id"], fresh["queue"][0]["id"])
        self.assertEqual(fresh["location"], old["location"])
        self.assertEqual(fresh["day"], old["day"])
        self.assertGreaterEqual(fresh["map_seed"], 0)
        self.assertLess(fresh["map_seed"], 2**32)
        self.assertNotEqual(fresh["map_seed"], int(float(old["map_seed"])) & 0xFFFFFFFF)
        self.assertFalse({project["id"] for project in old["queue"]}
                         & {project["id"] for project in fresh["queue"]})
        with self.assertRaises(ValueError):
            self.store.choose_project(old["queue"][0]["id"])

        other = GameStore(self.path, today=lambda: self.day)
        try:
            self.assertEqual(other.snapshot(), fresh)
        finally:
            other.close()
        again = self.store.reset()
        self.assertNotEqual(again["map_seed"], fresh["map_seed"])
        self.assertNotEqual(again["generation"], fresh["generation"])

    def test_reset_camera_game_keeps_reference_and_motor_fault_without_moving_hardware(self):
        class UnusedMotor:
            inputs = {"garbage": 1, "recycling": 2, "paper": 3, "compost": 4}

            def execute_category(self, category):
                raise AssertionError("Reset must not move a motor")

        app = GameApp(self.store, motor=UnusedMotor())
        app.latest_jpeg = b"camera frame"
        reference = [20] * 30
        app.detector.observe(reference)
        app.detector.occupied = True
        app.pending = {"item": "blocked item", "label": "paper", "source": "camera"}
        app.last_classification = {"item": "blocked item", "label": "paper"}
        app.motor_fault = True
        app.status = "Motor fault; check gate positions and restart"
        app.error = "Gate did not return"

        state = app.reset_game()
        self.assertIsNone(state["pending"])
        self.assertIsNone(state["last_classification"])
        self.assertTrue(state["motor"]["faulted"])
        self.assertTrue(state["motor"]["enabled"])
        self.assertEqual(state["status"], "Motor fault; check gate positions and restart")
        self.assertEqual(state["error"], "Gate did not return")
        self.assertTrue(state["has_frame"])
        self.assertIs(app.detector.reference, reference)
        self.assertTrue(app.detector.occupied)

    def test_reset_rejects_in_flight_classification_and_motor_routing(self):
        app = GameApp(self.store)
        app.pending = {"item": "can", "label": "recycling", "source": "camera"}
        self.store.record_sort("paper", "paper", "paper", "demo")
        for flag in ("classifying", "routing"):
            with self.subTest(flag=flag):
                setattr(app, flag, True)
                previous = app.snapshot()
                with self.assertRaisesRegex(ValueError, "finish processing"):
                    app.reset_game()
                self.assertEqual(app.snapshot(), previous)
                setattr(app, flag, False)

    def test_reset_queue_generation_survives_daily_rollover(self):
        reset = self.store.reset()
        self.day = date(2026, 10, 4)
        next_day = self.store.snapshot()
        self.assertEqual(next_day["map_seed"], reset["map_seed"])
        self.assertEqual(next_day["generation"], reset["generation"])
        self.assertEqual(next_day["queue"], [
            dict(project, percent=0, complete=False)
            for project in make_queue("StormHacks", "2026-10-04", reset["generation"])
        ])

    def test_simulated_score_preserves_classification_and_pending_camera_item(self):
        app = GameApp(self.store)
        app.detector.observe([20] * 30)
        app.detector.occupied = True
        app.latest_jpeg = b"camera frame"
        app.classifying = True
        app.status = "Classifying item with Gemini"
        app.last_classification = {"item": "previous item", "label": "paper"}
        hardware_keys = ("pending", "status", "error", "classifying", "last_classification", "motor", "has_frame")
        before = app.snapshot()
        detector = copy.deepcopy(app.detector.__dict__)
        event = app.demo_sort("paper")
        self.assertEqual(event["source"], "demo")
        self.assertEqual(app.snapshot()["correct_sorts"], 1)
        for key in hardware_keys:
            self.assertEqual(app.snapshot()[key], before[key])
        self.assertEqual(app.detector.__dict__, detector)

        app.handle_classification({"item": "newspaper", "label": "paper"})
        pending = app.pending
        before = app.snapshot()
        app.demo_sort("paper")
        self.assertIs(app.pending, pending)
        for key in hardware_keys:
            self.assertEqual(app.snapshot()[key], before[key])
        event = app.confirm("paper")
        self.assertEqual(event["source"], "camera")
        state = app.snapshot()
        self.assertEqual(state["correct_sorts"], 3)
        self.assertEqual(state["total"]["paper"], 3)
        self.assertEqual([event["source"] for event in state["history"]], ["camera", "demo", "demo"])
        with self.assertRaises(ValueError):
            app.confirm("paper")
        self.assertEqual(app.snapshot()["correct_sorts"], 3)

    def test_simulated_scores_coexist_with_one_in_flight_motor_route(self):
        class BlockingMotor:
            inputs = {"garbage": 1, "recycling": 2, "paper": 3, "compost": 4}

            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()
                self.calls = []

            def execute_category(self, category):
                self.calls.append(category)
                self.started.set()
                if not self.release.wait(5):
                    raise AssertionError("Test did not release simulated motor")
                return self.inputs[category]

        motor = BlockingMotor()
        app = GameApp(self.store, motor=motor)
        app.detector.observe([20] * 30)
        app.detector.occupied = True
        detector = copy.deepcopy(app.detector.__dict__)
        outcomes, errors = [], []

        def route():
            try:
                outcomes.append(app.handle_classification({"item": "can", "label": "recycling"}))
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=route, daemon=True)
        worker.start()
        try:
            self.assertTrue(motor.started.wait(2))
            before = app.snapshot()
            self.assertTrue(before["motor"]["routing"])
            pending = app.pending
            for category in CATEGORIES:
                simulated = app.demo_sort(category)
                self.assertEqual(simulated["source"], "demo")
                self.assertNotIn("motor_input", simulated)
            during = app.snapshot()
            self.assertEqual(during["correct_sorts"], 4)
            self.assertEqual(during["total"], dict.fromkeys(CATEGORIES, 1))
            for key in ("pending", "status", "error", "classifying", "last_classification", "motor"):
                self.assertEqual(during[key], before[key])
            self.assertIs(app.pending, pending)
            self.assertEqual(app.detector.__dict__, detector)
            self.assertEqual(motor.calls, ["recycling"])
        finally:
            motor.release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["source"], "motor")
        self.assertEqual(outcomes[0]["motor_input"], 2)
        state = app.snapshot()
        self.assertEqual(state["correct_sorts"], 5)
        self.assertEqual(state["total"]["recycling"], 2)
        self.assertEqual([event["source"] for event in state["history"]].count("demo"), 4)
        self.assertEqual([event["source"] for event in state["history"]].count("motor"), 1)
        self.assertEqual(motor.calls, ["recycling"])
        self.assertIsNone(state["pending"])
        with self.assertRaises(ValueError):
            app.confirm("recycling")
        self.assertEqual(app.snapshot()["correct_sorts"], 5)

    def test_simulated_score_does_not_clear_motor_fault(self):
        class UnusedMotor:
            inputs = {"garbage": 1, "recycling": 2, "paper": 3, "compost": 4}

            def execute_category(self, category):
                raise AssertionError("Simulated scores must not move motors")

        app = GameApp(self.store, motor=UnusedMotor())
        app.pending = {"item": "blocked item", "label": "paper", "source": "camera", "routing": "failed"}
        app.motor_fault = True
        app.status = "Motor fault; check gate positions and restart"
        app.error = "Gate did not return"
        before = app.snapshot()
        event = app.demo_sort("compost")
        after = app.snapshot()
        self.assertEqual(event["source"], "demo")
        self.assertEqual(after["correct_sorts"], 1)
        for key in ("pending", "status", "error", "classifying", "last_classification", "motor"):
            self.assertEqual(after[key], before[key])


class SceneTests(unittest.TestCase):
    def test_one_trigger_until_area_clears(self):
        detector = SceneDetector(stable_frames=2, clear_frames=2)
        empty = [20] * 30
        item = [100] * 30
        self.assertIsNone(detector.observe(empty))
        self.assertIsNone(detector.observe(item))
        self.assertIsNone(detector.observe(item))
        self.assertEqual(detector.observe(item), "item")
        self.assertIsNone(detector.observe(item))
        self.assertIsNone(detector.observe(empty))
        self.assertEqual(detector.observe(empty), "clear")
        self.assertIsNone(detector.observe(item))
        self.assertIsNone(detector.observe(item))
        self.assertEqual(detector.observe(item), "item")


if __name__ == "__main__":
    unittest.main()
