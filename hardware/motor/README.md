# Raspberry Pi motor driver

`motor.c` controls three A4988 STEP/DIR drivers through libgpiod v1. `motor.h` exposes `motor_init()`, `motor_execute(input)`, and `motor_cleanup()` for the Python bridge in `server/motor_controller.py`.

GPIO offsets on `/dev/gpiochip0` are BCM numbers:

| Driver | STEP | DIR |
| --- | --- | --- |
| Motor 1 | 17 | 23 |
| Motor 2 | 24 | 25 |
| Motor 3 | 5 | 6 |

The movement combinations retain the original C code's electrical direction levels. Motor 1 moves 25 steps (45 degrees); motors 2 and 3 move 39 steps (70.2 degrees, the nearest full-step setting to 70 degrees). These angles assume a 200-step motor using full steps. Each active motor moves outward, waits one second, then moves the same number of steps in the reverse direction. STEP pulses are 500 microseconds high and 500 microseconds low.

| Input | Bin | Outward DIR levels |
| --- | --- | --- |
| 1 | Garbage | M1 = 1, M2 = 0 |
| 2 | Recycling | M1 = 1, M2 = 1 |
| 3 | Paper | M1 = 0, M3 = 0 |
| 4 | Compost | M1 = 0, M3 = 1 |
| 5 | Unknown / no movement | None |

Build from the repository root:

```bash
sudo apt-get install -y libgpiod-dev
make -C hardware/motor
```

This produces `hardware/motor/libmotor.so`. Start `server.app` with `--motors` to initialize GPIO and route classified items. The process needs permission to access `/dev/gpiochip0`.

To build and run the separate interactive motor test, stop the backend first so it releases GPIO:

```bash
make -C hardware/motor motor_test
./hardware/motor/motor_test
```

This interactive program moves the physical motors when you enter 1–4. Input 5 makes no movement; input 0 releases GPIO and exits. The gates should start in their neutral position. After a GPIO failure, further movement is blocked until the gate positions are checked and the controller is restarted.
