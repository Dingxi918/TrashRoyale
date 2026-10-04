#!/usr/bin/env python3
"""Classify one ESP32 camera JPEG with the Gemini API.

Examples:
    python gemini_camera_classifier.py --image latest.jpg --labels 'recycling,compost,garbage,paper'
    python gemini_camera_classifier.py --port /dev/ttyUSB0 --baud 460800 \
        --labels 'recycling,compost,garbage,paper'

Import classify_jpeg() from a scene-change detector to classify only when a
new object is present and the scene has settled. Set GEMINI_API_KEY first.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Sequence


DEFAULT_MODEL = "gemini-3.8-flash"
REQUEST_TIMEOUT_MS = 30_000


def classify_jpeg(
    jpeg_bytes: bytes,
    labels: Sequence[str],
    client: Any,
    model: str = DEFAULT_MODEL,
) -> Dict[str, str]:
    """Send one JPEG and return {'item': ..., 'label': ...}."""
    labels = [label.strip() for label in labels if label.strip()]
    if not labels or len(set(labels)) != len(labels) or "unknown" in labels:
        raise ValueError("Provide distinct labels; 'unknown' is added automatically")
    if not jpeg_bytes.startswith(b"\xff\xd8") or not jpeg_bytes.endswith(b"\xff\xd9"):
        raise ValueError("Input is not a complete JPEG image")

    allowed = labels + ["unknown"]
    prompt = (
        "A camera points at a fixed waste-sorting area. Identify the newly "
        "placed main object, ignoring the background, hands, and other people. "
        "Return its short common name in 'item' and choose exactly one label "
        "from: {}. If no single item is visible, or its category cannot be "
        "determined reliably from the image, use 'unknown'. Do not guess "
        "hidden materials or local disposal rules."
    ).format(", ".join(allowed))

    from google.genai import types

    response = client.models.generate_content(
        model=model,
        contents=[
            prompt,
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
        ],
        config=types.GenerateContentConfig(
            # The camera loop owns bounded retries and checks fresh frames
            # between attempts. Avoid multiplying its calls with SDK retries.
            http_options=types.HttpOptions(
                timeout=REQUEST_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "label": {"type": "string", "enum": allowed},
                },
                "required": ["item", "label"],
            },
        ),
    )
    result = json.loads(response.text or "")
    if not isinstance(result, dict) or result.get("label") not in allowed:
        raise ValueError("Unexpected Gemini classification: {!r}".format(result))
    if not isinstance(result.get("item"), str):
        raise ValueError("Gemini did not return an item name")
    return {"item": result["item"], "label": result["label"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="Classify an existing JPEG")
    parser.add_argument("--port", help="CH340 port; auto-detect if omitted")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--labels", required=True, help="Comma-separated sorting categories")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    labels = [part.strip() for part in args.labels.split(",") if part.strip()]
    if not os.environ.get("GEMINI_API_KEY"):
        parser.error("Set GEMINI_API_KEY in the Pi shell before running this script")

    try:
        if args.image is not None:
            jpeg = args.image.read_bytes()
        else:
            try:
                from .esp32_cam_rcv import Esp32SerialCamera
            except ImportError:
                from esp32_cam_rcv import Esp32SerialCamera

            with Esp32SerialCamera(args.port, baud=args.baud) as camera:
                jpeg = camera.read_jpeg()

        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        result = classify_jpeg(jpeg, labels, client, args.model)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, TimeoutError, ValueError, RuntimeError) as error:
        print("Classification failed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
