#include <stdio.h>
#include <unistd.h>
#include <gpiod.h>

#include "motor.h"

// --------------------------------------------------
// GPIO assignments
// --------------------------------------------------

#define MOTOR1_STEP 17
#define MOTOR1_DIR  23

#define MOTOR2_STEP 24
#define MOTOR2_DIR  25

#define MOTOR3_STEP 5
#define MOTOR3_DIR  6

// --------------------------------------------------
// Motor configuration
// --------------------------------------------------

#define STEPS_PER_REV 200
#define STEPS_45_DEG 25

#define STEP_DELAY_US 500

#define CW  0
#define CCW 1

#define hold_time 1

// --------------------------------------------------
// GPIO objects
// --------------------------------------------------

static struct gpiod_chip *chip = NULL;

static struct gpiod_line *step1 = NULL;
static struct gpiod_line *dir1  = NULL;

static struct gpiod_line *step2 = NULL;
static struct gpiod_line *dir2  = NULL;

static struct gpiod_line *step3 = NULL;
static struct gpiod_line *dir3  = NULL;


// --------------------------------------------------
// Move one motor
// --------------------------------------------------

static void move_motor(struct gpiod_line *step,
                       struct gpiod_line *dir,
                       int direction,
                       int steps)
{
    gpiod_line_set_value(dir, direction);

    for (int i = 0; i < steps; i++) {

        gpiod_line_set_value(step, 1);
        usleep(STEP_DELAY_US);

        gpiod_line_set_value(step, 0);
        usleep(STEP_DELAY_US);
    }
}


// --------------------------------------------------
// Initialize motors
// --------------------------------------------------

int motor_init(void)
{
    chip = gpiod_chip_open("/dev/gpiochip0");

    if (chip == NULL) {
        perror("Failed to open GPIO chip");
        return -1;
    }


    // Get GPIO lines

    step1 = gpiod_chip_get_line(chip, MOTOR1_STEP);
    dir1  = gpiod_chip_get_line(chip, MOTOR1_DIR);

    step2 = gpiod_chip_get_line(chip, MOTOR2_STEP);
    dir2  = gpiod_chip_get_line(chip, MOTOR2_DIR);

    step3 = gpiod_chip_get_line(chip, MOTOR3_STEP);
    dir3  = gpiod_chip_get_line(chip, MOTOR3_DIR);


    if (!step1 || !dir1 ||
        !step2 || !dir2 ||
        !step3 || !dir3) {

        perror("Failed to get GPIO lines");

        motor_cleanup();

        return -1;
    }


    // Configure STEP outputs

    if (gpiod_line_request_output(
            step1, "MOTOR1-STEP", 0) < 0) {

        perror("Failed to configure Motor 1 STEP");
        motor_cleanup();
        return -1;
    }

    if (gpiod_line_request_output(
            step2, "MOTOR2-STEP", 0) < 0) {

        perror("Failed to configure Motor 2 STEP");
        motor_cleanup();
        return -1;
    }

    if (gpiod_line_request_output(
            step3, "MOTOR3-STEP", 0) < 0) {

        perror("Failed to configure Motor 3 STEP");
        motor_cleanup();
        return -1;
    }


    // Configure DIR outputs

    if (gpiod_line_request_output(
            dir1, "MOTOR1-DIR", 0) < 0) {

        perror("Failed to configure Motor 1 DIR");
        motor_cleanup();
        return -1;
    }

    if (gpiod_line_request_output(
            dir2, "MOTOR2-DIR", 0) < 0) {

        perror("Failed to configure Motor 2 DIR");
        motor_cleanup();
        return -1;
    }

    if (gpiod_line_request_output(
            dir3, "MOTOR3-DIR", 0) < 0) {

        perror("Failed to configure Motor 3 DIR");
        motor_cleanup();
        return -1;
    }


    printf("Motors initialized successfully.\n");

    return 0;
}


// --------------------------------------------------
// Execute motor combination
// --------------------------------------------------

void motor_execute(int input)
{
    switch (input) {

        // ------------------------------------------
        // INPUT 1
        // M1: 45 CCW
        // M2: 45 CCW
        // M3: no movement
        // ------------------------------------------

        case 1:

            printf("\nInput 1\n");
            printf("M1: 45 CCW\n");
            printf("M2: 45 CCW\n");
            printf("M3: No movement\n");

            move_motor(step1, dir1, CCW, STEPS_45_DEG);
            move_motor(step2, dir2, CW, STEPS_45_DEG);

            printf("Waiting %d seconds...\n", hold_time);

            sleep(hold_time);

            printf("Returning...\n");

            move_motor(step1, dir1, CW, STEPS_45_DEG);
            move_motor(step2, dir2, CCW, STEPS_45_DEG);

            break;


        // ------------------------------------------
        // INPUT 2
        // M1: 45 CCW
        // M2: 45 CW
        // M3: no movement
        // ------------------------------------------

        case 2:

            printf("\nInput 2\n");
            printf("M1: 45 CCW\n");
            printf("M2: 45 CW\n");
            printf("M3: No movement\n");

            move_motor(step1, dir1, CCW, STEPS_45_DEG);
            move_motor(step2, dir2, CCW, STEPS_45_DEG);

            printf("Waiting %d seconds...\n", hold_time);

            sleep(hold_time);

            printf("Returning...\n");

            move_motor(step1, dir1, CW, STEPS_45_DEG);
            move_motor(step2, dir2, CW, STEPS_45_DEG);

            break;


        // ------------------------------------------
        // INPUT 3
        // M1: 45 CW
        // M2: no movement
        // M3: 45 CCW
        // ------------------------------------------

        case 3:

            printf("\nInput 3\n");
            printf("M1: 45 CW\n");
            printf("M2: No movement\n");
            printf("M3: 45 CCW\n");

            move_motor(step1, dir1, CW, STEPS_45_DEG);
            move_motor(step3, dir3, CW, STEPS_45_DEG);

            printf("Waiting %d seconds...\n", hold_time);

            sleep(hold_time);

            printf("Returning...\n");

            move_motor(step1, dir1, CCW, STEPS_45_DEG);
            move_motor(step3, dir3, CCW, STEPS_45_DEG);

            break;


        // ------------------------------------------
        // INPUT 4
        // M1: 45 CW
        // M2: no movement
        // M3: 45 CW
        // ------------------------------------------

        case 4:

            printf("\nInput 4\n");
            printf("M1: 45 CW\n");
            printf("M2: No movement\n");
            printf("M3: 45 CW\n");

            move_motor(step1, dir1, CW, STEPS_45_DEG);
            move_motor(step3, dir3, CCW, STEPS_45_DEG);

            printf("Waiting %d seconds...\n", hold_time);

            sleep(hold_time);

            printf("Returning...\n");

            move_motor(step1, dir1, CCW, STEPS_45_DEG);
            move_motor(step3, dir3, CW, STEPS_45_DEG);

            break;


        // ------------------------------------------
        // INPUT 5
        // ERROR CASE
        // ------------------------------------------

        case 5:

            printf("\nInput 5: ERROR CASE\n");
            printf("No motors will move.\n");

            break;


        default:

            printf("\nInvalid motor input: %d\n", input);
            printf("No motors will move.\n");

            break;
    }
}


// --------------------------------------------------
// Cleanup
// --------------------------------------------------

void motor_cleanup(void)
{
    if (step1)
        gpiod_line_set_value(step1, 0);

    if (step2)
        gpiod_line_set_value(step2, 0);

    if (step3)
        gpiod_line_set_value(step3, 0);


    if (step1)
        gpiod_line_release(step1);

    if (dir1)
        gpiod_line_release(dir1);


    if (step2)
        gpiod_line_release(step2);

    if (dir2)
        gpiod_line_release(dir2);


    if (step3)
        gpiod_line_release(step3);

    if (dir3)
        gpiod_line_release(dir3);


    if (chip)
        gpiod_chip_close(chip);


    chip = NULL;

    step1 = NULL;
    dir1  = NULL;

    step2 = NULL;
    dir2  = NULL;

    step3 = NULL;
    dir3  = NULL;
}
