"""Detect one stable item, then wait for the camera area to clear."""

from io import BytesIO


def thumbnail(jpeg):
    from PIL import Image

    with Image.open(BytesIO(jpeg)) as image:
        return list(image.convert("L").resize((64, 48)).getdata())


def mean_difference(first, second):
    return sum(abs(a - b) for a, b in zip(first, second)) / len(first)


class SceneDetector:
    def __init__(self, presence_threshold=11, motion_threshold=4,
                 stable_frames=3, clear_frames=3):
        self.presence_threshold = presence_threshold
        self.motion_threshold = motion_threshold
        self.stable_frames = stable_frames
        self.clear_frames = clear_frames
        self.reference = None
        self.previous = None
        self.occupied = False
        self.stable_count = 0
        self.clear_count = 0
        self.reference_difference = None
        self.motion_difference = None
        self.present = False
        self.settled = False

    def reset(self):
        self.reference = None
        self.previous = None
        self.occupied = False
        self.stable_count = 0
        self.clear_count = 0
        self.reference_difference = None
        self.motion_difference = None
        self.present = False
        self.settled = False

    def snapshot(self):
        """Explain the latest frame's detection decision without changing it."""
        return {
            "phase": ("waiting_for_empty_reference" if self.reference is None else
                      "waiting_for_area_to_clear" if self.occupied else "waiting_for_item"),
            "progress_count": self.clear_count if self.occupied else self.stable_count,
            "progress_frames_required": self.clear_frames if self.occupied else self.stable_frames,
            "has_reference": self.reference is not None,
            "reference_difference": (round(self.reference_difference, 2)
                                     if self.reference_difference is not None else None),
            "presence_threshold": self.presence_threshold,
            "motion_difference": (round(self.motion_difference, 2)
                                  if self.motion_difference is not None else None),
            "motion_threshold": self.motion_threshold,
            "item_present": self.present,
            "settled": self.settled,
            "stable_count": self.stable_count,
            "stable_frames_required": self.stable_frames,
            "occupied": self.occupied,
            "clear_count": self.clear_count,
            "clear_frames_required": self.clear_frames,
        }

    def observe(self, pixels):
        """Return 'item', 'clear', or None. The first frame is the empty reference."""
        if self.reference is None:
            self.reference = pixels
            self.previous = pixels
            self.reference_difference = 0.0
            self.motion_difference = 0.0
            self.present = False
            self.settled = True
            return None
        self.reference_difference = mean_difference(pixels, self.reference)
        self.motion_difference = mean_difference(pixels, self.previous)
        changed = self.present = self.reference_difference >= self.presence_threshold
        settled = self.settled = self.motion_difference <= self.motion_threshold
        self.previous = pixels
        if not self.occupied:
            self.stable_count = self.stable_count + 1 if changed and settled else 0
            if self.stable_count >= self.stable_frames:
                self.occupied = True
                self.stable_count = 0
                return "item"
        else:
            self.clear_count = self.clear_count + 1 if not changed else 0
            if self.clear_count >= self.clear_frames:
                self.occupied = False
                self.clear_count = 0
                return "clear"
        return None
