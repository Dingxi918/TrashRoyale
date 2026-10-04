#!/usr/bin/env python3
"""Receive JPEG frames from an ESP32-S3 camera through a CH340 serial adapter.

Wire protocol expected from the ESP32 firmware:
    Raspberry Pi -> ESP32: b"G"
    ESP32 -> Raspberry Pi: b"CAM1" + uint32_le(jpeg_length) + jpeg_bytes

The Esp32SerialCamera class can be imported by another Python program, while
running this file directly opens an OpenCV preview window.
"""

import argparse
import struct
import time
from pathlib import Path
from typing import Optional

import serial
from serial.tools import list_ports


MAGIC = b"CAM1"
REQUEST_FRAME = b"G"
CH340_VENDOR_ID = 0x1A86
DEFAULT_BAUD = 460800
MAX_JPEG_SIZE = 2_000_000


def find_ch340_port() -> str:
    """Return the only connected CH340 port, or raise a useful error."""
    ports = list(list_ports.comports())
    ch340_ports = [port.device for port in ports if port.vid == CH340_VENDOR_ID]

    if len(ch340_ports) == 1:
        return ch340_ports[0]
    if len(ch340_ports) > 1:
        joined = ", ".join(ch340_ports)
        raise RuntimeError(
            "More than one CH340 adapter was found: {}. Use --port.".format(joined)
        )

    tty_usb_ports = [port.device for port in ports if "ttyUSB" in port.device]
    if len(tty_usb_ports) == 1:
        return tty_usb_ports[0]

    detected = ", ".join(port.device for port in ports) or "none"
    raise RuntimeError(
        "No CH340 serial adapter found. Detected ports: {}. "
        "Connect the board or specify --port /dev/ttyUSB0.".format(detected)
    )


class Esp32SerialCamera:
    def __init__(
        self,
        port: Optional[str] = None,
        baud: int = DEFAULT_BAUD,
        frame_timeout: float = 5.0,
    ) -> None:
        self.port = port or find_ch340_port()
        self.baud = baud
        self.frame_timeout = frame_timeout
        self.serial = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            timeout=0.1,
            write_timeout=2.0,
        )

        # CH340 boards often connect DTR/RTS to the ESP32 reset/boot pins.
        # Deassert both, allow a possible reset to finish, and discard boot logs.
        self.serial.dtr = False
        self.serial.rts = False
        time.sleep(2.0)
        self.serial.reset_input_buffer()

    def close(self) -> None:
        if self.serial.is_open:
            self.serial.close()

    def __enter__(self) -> "Esp32SerialCamera":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _read_exact(self, size: int, deadline: float) -> bytes:
        data = bytearray()
        while len(data) < size:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Timed out after receiving {}/{} bytes".format(len(data), size)
                )

            chunk = self.serial.read(size - len(data))
            if chunk:
                data.extend(chunk)

        return bytes(data)

    def _wait_for_magic(self, deadline: float) -> None:
        window = bytearray()
        while time.monotonic() < deadline:
            byte = self.serial.read(1)
            if not byte:
                continue
            window.extend(byte)
            if len(window) > len(MAGIC):
                del window[0]
            if bytes(window) == MAGIC:
                return

        raise TimeoutError("Timed out waiting for the CAM1 frame header")

    def read_jpeg(self) -> bytes:
        """Request and return one complete JPEG image."""
        self.serial.write(REQUEST_FRAME)
        self.serial.flush()

        deadline = time.monotonic() + self.frame_timeout
        self._wait_for_magic(deadline)

        length_bytes = self._read_exact(4, deadline)
        frame_length = struct.unpack("<I", length_bytes)[0]
        if frame_length == 0 or frame_length > MAX_JPEG_SIZE:
            raise ValueError("Invalid JPEG length received: {}".format(frame_length))

        return self._read_exact(frame_length, deadline)

    def read(self):
        """Request, decode, and return one OpenCV BGR frame."""
        try:
            import cv2
            import numpy as np
        except ImportError as error:
            raise RuntimeError("OpenCV preview needs opencv-python and numpy") from error
        jpeg = self.read_jpeg()
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("OpenCV could not decode the received JPEG")
        return frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview JPEG frames received from an ESP32-S3 over CH340 serial"
    )
    parser.add_argument(
        "--port",
        help="Serial device, for example /dev/ttyUSB0; auto-detected if omitted",
    )
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--save-latest",
        type=Path,
        help="Also overwrite this file with the most recent JPEG frame",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Receive frames without opening an OpenCV window",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cv2 = None
    if not args.headless:
        try:
            import cv2
            import numpy as np
        except ImportError:
            print("Preview needs opencv-python and numpy; use --headless for JPEG capture")
            return 1
    frame_count = 0
    start_time = time.monotonic()

    try:
        with Esp32SerialCamera(args.port, args.baud, args.timeout) as camera:
            print("Connected to {} at {} baud".format(camera.port, camera.baud))
            print("Press q in the preview window, or Ctrl+C, to quit.")

            while True:
                try:
                    jpeg = camera.read_jpeg()
                    if not args.headless:
                        frame = cv2.imdecode(
                            np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR
                        )
                        if frame is None:
                            raise ValueError("OpenCV could not decode the received JPEG")

                    frame_count += 1
                    elapsed = max(time.monotonic() - start_time, 0.001)
                    fps = frame_count / elapsed

                    if args.save_latest:
                        args.save_latest.write_bytes(jpeg)

                    if not args.headless:
                        label = "{}  {:.1f} FPS  {} bytes".format(
                            camera.port, fps, len(jpeg)
                        )
                        cv2.putText(
                            frame,
                            label,
                            (10, 24),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.55,
                            (0, 255, 0),
                            1,
                            cv2.LINE_AA,
                        )
                        cv2.imshow("ESP32-S3 serial camera", frame)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break

                except (TimeoutError, ValueError) as error:
                    print("Frame error: {}. Resynchronizing...".format(error))
                    camera.serial.reset_input_buffer()

    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, serial.SerialException) as error:
        print("Serial camera error: {}".format(error))
        return 1
    finally:
        if cv2 is not None:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
