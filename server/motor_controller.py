"""Python bridge to the Raspberry Pi A4988 motor library."""

import ctypes
import os
import threading
from pathlib import Path

from .game import CATEGORIES


DEFAULT_MOTOR_INPUTS = {"garbage": 1, "recycling": 2, "paper": 3, "compost": 4}
DEFAULT_LIBRARY = Path(__file__).resolve().parents[1] / "hardware/motor/libmotor.so"


class MotorError(RuntimeError):
    """The GPIO controller could not initialize or complete a routing cycle."""


def validate_motor_inputs(inputs):
    if set(inputs) != set(CATEGORIES):
        raise ValueError("Motor mapping must include garbage, recycling, paper, and compost")
    if any(type(value) is not int for value in inputs.values()) or set(inputs.values()) != {1, 2, 3, 4}:
        raise ValueError("Assign each motor input 1–4 to exactly one category")
    return dict(inputs)


def parse_motor_inputs(value):
    """Parse category=number pairs for the --motor-map option."""
    inputs = {}
    for pair in value.split(","):
        key, separator, number = pair.strip().partition("=")
        if not separator or key in inputs:
            raise ValueError("Use category=number pairs, with each category once")
        inputs[key] = int(number)
    return validate_motor_inputs(inputs)


class MotorController:
    def __init__(self, library_path=DEFAULT_LIBRARY, inputs=None):
        self.inputs = validate_motor_inputs(inputs if inputs is not None else DEFAULT_MOTOR_INPUTS)
        self.lock = threading.Lock()
        self.initialized = False
        self.faulted = False
        try:
            self.library = ctypes.CDLL(str(Path(library_path).resolve()), use_errno=True)
        except OSError as error:
            raise MotorError(
                f"Cannot load motor library: {error}. Build it with make -C hardware/motor"
            ) from error
        self.library.motor_init.argtypes = []
        self.library.motor_init.restype = ctypes.c_int
        self.library.motor_execute.argtypes = [ctypes.c_int]
        self.library.motor_execute.restype = ctypes.c_int
        self.library.motor_cleanup.argtypes = []
        self.library.motor_cleanup.restype = None

    @staticmethod
    def _error_details():
        number = ctypes.get_errno()
        return os.strerror(number) if number else "GPIO operation failed"

    def initialize(self):
        with self.lock:
            if self.faulted:
                raise MotorError("Motor controller is faulted; check the gates and restart")
            if self.initialized:
                return
            if self.library.motor_init() != 0:
                raise MotorError(f"Motor initialization failed: {self._error_details()}")
            self.initialized = True

    def execute_category(self, category):
        """Route one known category; unknown does not touch GPIO. Return input or None."""
        if category == "unknown":
            return None
        if category not in self.inputs:
            raise ValueError(f"Invalid motor category: {category}")
        with self.lock:
            if not self.initialized:
                raise MotorError("Initialize the motor controller before routing an item")
            if self.faulted:
                raise MotorError("Motor controller is faulted; check the gates and restart")
            motor_input = self.inputs[category]
            if self.library.motor_execute(motor_input) != 0:
                self.faulted = True
                raise MotorError(
                    f"Motor input {motor_input} failed: {self._error_details()}. "
                    "Check gate positions before restarting"
                )
            return motor_input

    def close(self):
        with self.lock:
            if self.initialized:
                self.library.motor_cleanup()
                self.initialized = False
