#include <errno.h>
#include <gpiod.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

#include "motor.h"

/* BCM GPIO offsets: STEP, DIR for each A4988 driver. */
static const unsigned int pins[3][2] = {{17, 23}, {24, 25}, {5, 6}};
static const char *consumers[3][2] = {
    {"MOTOR1-STEP", "MOTOR1-DIR"},
    {"MOTOR2-STEP", "MOTOR2-DIR"},
    {"MOTOR3-STEP", "MOTOR3-DIR"},
};

static const int travel_steps[3] = {30, 40, 40};

#define STEP_DELAY_US 10000
#define HOLD_SECONDS 1
#define CW 0
#define CCW 1
#define STILL -1

/* Preserve the original electrical direction levels, including M2/M3 polarity. */
static const int directions[4][3] = {
    {CCW, CW, STILL},    /* Input 1: garbage */
    {CCW, CCW, STILL},   /* Input 2: recycling */
    {CW, STILL, CW},     /* Input 3: paper */
    {CW, STILL, CCW},    /* Input 4: compost */
};

static struct gpiod_chip *chip;
static struct gpiod_line *lines[3][2];
static int requested[3][2];
static int ready;
static int faulted;

static void lower_steps(void)
{
    for (int motor = 0; motor < 3; motor++) {
        if (requested[motor][0])
            gpiod_line_set_value(lines[motor][0], 0);
    }
}

static int move_motor(int motor, int direction)
{
    if (gpiod_line_set_value(lines[motor][1], direction) < 0)
        return -1;
    usleep(STEP_DELAY_US);
    for (int step = 0; step < travel_steps[motor]; step++) {
        if (gpiod_line_set_value(lines[motor][0], 1) < 0)
            return -1;
        usleep(STEP_DELAY_US);
        if (gpiod_line_set_value(lines[motor][0], 0) < 0)
            return -1;
        usleep(STEP_DELAY_US);
    }
    return 0;
}

int motor_init(void)
{
    if (ready)
        return faulted ? -1 : 0;

    chip = gpiod_chip_open("/dev/gpiochip0");
    if (!chip) {
        perror("Failed to open GPIO chip");
        return -1;
    }

    for (int motor = 0; motor < 3; motor++) {
        for (int pin = 0; pin < 2; pin++) {
            lines[motor][pin] = gpiod_chip_get_line(chip, pins[motor][pin]);
            if (!lines[motor][pin] || gpiod_line_request_output(
                    lines[motor][pin], consumers[motor][pin], 0) < 0) {
                perror("Failed to request motor GPIO output");
                motor_cleanup();
                return -1;
            }
            requested[motor][pin] = 1;
        }
    }
    ready = 1;
    faulted = 0;
    return 0;
}

int motor_execute(int input)
{
    if (input == MOTOR_NO_MOVEMENT)
        return 0;
    if (input < 1 || input > 4) {
        errno = EINVAL;
        return -1;
    }
    if (!ready || faulted) {
        errno = ready ? EIO : ENODEV;
        return -1;
    }

    const int *route = directions[input - 1];
    for (int motor = 0; motor < 3; motor++) {
        if (route[motor] != STILL && move_motor(motor, route[motor]) < 0)
            goto failed;
    }

    struct timespec remaining = {HOLD_SECONDS, 0};
    while (nanosleep(&remaining, &remaining) < 0) {
        if (errno != EINTR)
            goto failed;
    }

    for (int motor = 0; motor < 3; motor++) {
        if (route[motor] != STILL && move_motor(motor, !route[motor]) < 0)
            goto failed;
    }
    return 0;

failed:
    /* Do not guess a return position after a partial move. Stop further cycles. */
    perror("Motor cycle failed; check gate positions before restarting");
    lower_steps();
    faulted = 1;
    return -1;
}

void motor_cleanup(void)
{
    lower_steps();
    for (int motor = 0; motor < 3; motor++) {
        for (int pin = 0; pin < 2; pin++) {
            if (requested[motor][pin])
                gpiod_line_release(lines[motor][pin]);
            requested[motor][pin] = 0;
            lines[motor][pin] = NULL;
        }
    }
    if (chip)
        gpiod_chip_close(chip);
    chip = NULL;
    ready = 0;
    faulted = 0;
}
