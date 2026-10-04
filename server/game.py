"""Persistent, single-location city game rules."""

import copy
import hashlib
import json
import random
import secrets
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path


CATEGORIES = ("recycling", "compost", "paper", "garbage")
DAILY_PROJECT_COUNT = 8
RESOURCE_NAMES = {
    "recycling": "Building materials",
    "compost": "Fertilizer",
    "paper": "Exterior details",
    "garbage": "Energy",
}
PROJECT_POOL = (
    ("Community Garden", "garden", (3, 8, 2, 2)),
    ("Neighborhood Library", "library", (7, 2, 8, 3)),
    ("Solar Plaza", "plaza", (6, 3, 3, 7)),
    ("Riverside Park", "park", (4, 9, 3, 2)),
    ("Learning Hub", "school", (8, 3, 7, 4)),
    ("Bike Station", "bike", (7, 2, 3, 5)),
    ("Community Market", "market", (6, 4, 6, 4)),
    ("Arts Pavilion", "arts", (5, 4, 8, 3)),
)


def _seed(location, day):
    digest = hashlib.sha256(f"{location}:{day}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def make_queue(location, day, generation=None):
    rng = random.Random(_seed(location, f"{day}:{generation}" if generation else day))
    selected = rng.sample(PROJECT_POOL, DAILY_PROJECT_COUNT)
    queue = []
    for index, (name, kind, base) in enumerate(selected):
        needs = {category: max(1, round(base[i] * rng.uniform(0.85, 1.15)))
                 for i, category in enumerate(CATEGORIES)}
        queue.append({
            "id": f"{day}-{generation}-{index}" if generation else f"{day}-{index}",
            "name": name, "kind": kind,
            "required": needs, "progress": dict.fromkeys(CATEGORIES, 0),
        })
    return queue


def project_percent(project):
    earned = sum(project["progress"].values())
    needed = sum(project["required"].values())
    return round(100 * earned / needed) if needed else 100


def is_complete(project):
    return all(project["progress"][key] >= project["required"][key]
               for key in CATEGORIES)


class GameStore:
    def __init__(self, path, location="StormHacks", today=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.location = location
        self.today = today or date.today
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        # WAL avoids rewriting the main database and journal on every sort.
        # Keep FULL synchronization so a credited item is committed before reply.
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA synchronous = FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS game (id INTEGER PRIMARY KEY, state TEXT NOT NULL)")
        row = self.db.execute("SELECT state FROM game WHERE id = 1").fetchone()
        if row:
            self.state = json.loads(row[0])
            if self.state["location"] != location:
                raise ValueError("This save belongs to a different location")
        else:
            self.state = self._fresh_state(_seed(location, "map"))
            self._save()

    def _fresh_state(self, map_seed, generation=None):
        day = self.today().isoformat()
        queue = make_queue(self.location, day, generation)
        state = {
            "location": self.location, "day": day, "queue": queue,
            "active_id": queue[0]["id"], "completed": [],
            "total": dict.fromkeys(CATEGORIES, 0),
            "decorations": dict.fromkeys(CATEGORIES, 0),
            "correct_sorts": 0, "history": [], "map_seed": map_seed,
        }
        if generation:
            state["generation"] = generation
        return state

    def close(self):
        with self.lock:
            self.db.close()

    def _save(self):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO game (id, state) VALUES (1, ?)",
                (json.dumps(self.state, separators=(",", ":")),),
            )

    def _roll_day(self):
        day = self.today().isoformat()
        generation = self.state.get("generation")
        if self.state["day"] != day:
            self.state["day"] = day
            self.state["queue"] = make_queue(self.location, day, generation)
            self.state["active_id"] = self.state["queue"][0]["id"]
            self._save()
            return

        # Expand saves made with the old daily count without replacing projects
        # that already received resources or changing their identifiers.
        queue = self.state["queue"]
        if len(queue) >= DAILY_PROJECT_COUNT:
            return
        existing_kinds = {project["kind"] for project in queue}
        for project in make_queue(self.location, day, generation):
            if project["kind"] in existing_kinds:
                continue
            project["id"] = (f"{day}-{generation}-{len(queue)}" if generation
                             else f"{day}-{len(queue)}")
            queue.append(project)
            if len(queue) == DAILY_PROJECT_COUNT:
                break
        if not any(project["id"] == self.state["active_id"] and not is_complete(project)
                   for project in queue):
            next_project = next((project for project in queue if not is_complete(project)), None)
            self.state["active_id"] = next_project["id"] if next_project else None
        self._save()

    def snapshot(self):
        with self.lock:
            self._roll_day()
            state = copy.deepcopy(self.state)
            for project in state["queue"]:
                project["percent"] = project_percent(project)
                project["complete"] = is_complete(project)
            return state

    def reset(self):
        """Start a fresh saved game without carrying resources or city history."""
        with self.lock:
            previous = self.state
            previous_seed = previous["map_seed"]
            # Older saves use 64-bit seeds, which JavaScript rounds before taking
            # the low 32 bits. Exclude that rendered seed as well as the raw one.
            old_seeds = {previous_seed & 0xFFFFFFFF, int(float(previous_seed)) & 0xFFFFFFFF}
            map_seed = secrets.randbits(32)
            while map_seed in old_seeds:
                map_seed = secrets.randbits(32)
            self.state = self._fresh_state(map_seed, secrets.token_hex(8))
            try:
                self._save()
            except Exception:
                self.state = previous
                raise
            return self.snapshot()

    def choose_project(self, project_id):
        with self.lock:
            self._roll_day()
            if not any(p["id"] == project_id and not is_complete(p)
                       for p in self.state["queue"]):
                raise ValueError("Choose an unfinished project from today's queue")
            self.state["active_id"] = project_id
            self._save()
            return self.snapshot()

    def record_sort(self, item, label, actual_bin, source, motor_input=None):
        if label not in (*CATEGORIES, "unknown") or actual_bin not in CATEGORIES:
            raise ValueError("Invalid sorting category")
        with self.lock:
            self._roll_day()
            correct = label == actual_bin
            event = {
                "time": datetime.now().isoformat(timespec="milliseconds"),
                "item": item[:80], "predicted": label,
                "actual": actual_bin, "correct": correct, "source": source,
                "resource": RESOURCE_NAMES.get(label) if correct else None,
                "project": None,
            }
            if motor_input is not None:
                event["motor_input"] = motor_input
            if correct:
                self.state["total"][label] += 1
                self.state["correct_sorts"] += 1
                queue = self.state["queue"]
                active = next((i for i, p in enumerate(queue)
                               if p["id"] == self.state["active_id"]), 0)
                order = list(range(active, len(queue))) + list(range(active))
                for index in order:
                    project = queue[index]
                    if project["progress"][label] >= project["required"][label]:
                        continue
                    was_complete = is_complete(project)
                    project["progress"][label] += 1
                    event["project"] = project["name"]
                    if not was_complete and is_complete(project):
                        self.state["completed"].append(copy.deepcopy(project))
                    break
                else:
                    self.state["decorations"][label] += 1
                    event["project"] = "City environment"

                active_project = next((p for p in queue if p["id"] == self.state["active_id"]), None)
                if active_project is None or is_complete(active_project):
                    next_project = next((p for p in queue if not is_complete(p)), None)
                    self.state["active_id"] = next_project["id"] if next_project else None

            self.state["history"].insert(0, event)
            self.state["history"] = self.state["history"][:30]
            self._save()
            return event
