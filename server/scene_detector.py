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

    def reset(self):
        self.reference = None
        self.previous = None
        self.occupied = False
        self.stable_count = 0
        self.clear_count = 0

    def observe(self, pixels):
        """Return 'item', 'clear', or None. The first frame is the empty reference."""
        if self.reference is None:
            self.reference = pixels
            self.previous = pixels
            return None
        changed = mean_difference(pixels, self.reference) >= self.presence_threshold
        settled = mean_difference(pixels, self.previous) <= self.motion_threshold
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
