#include <stdio.h>

#include "motor.h"

int main(void)
{
    int input;
    int exit_status = 0;


    // Initialize motors

    if (motor_init() != 0) {

        printf("Motor initialization failed.\n");

        return 1;
    }


    printf("\n");
    printf("===============================\n");
    printf("      MOTOR TEST PROGRAM\n");
    printf("===============================\n");

    printf("1 - Garbage:   M1 DIR=1, M2 DIR=0\n");
    printf("2 - Recycling: M1 DIR=1, M2 DIR=1\n");
    printf("3 - Paper:     M1 DIR=0, M3 DIR=0\n");
    printf("4 - Compost:   M1 DIR=0, M3 DIR=1\n");
    printf("5 - ERROR CASE / NO MOVEMENT\n");
    printf("0 - EXIT\n");

    printf("===============================\n");


    while (1) {

        printf("\nEnter test value: ");

        int result = scanf("%d", &input);
        if (result == EOF)
            break;
        if (result != 1) {

            printf("Invalid input.\n");

            // Clear invalid input

            int character;
            while ((character = getchar()) != '\n' && character != EOF);

            continue;
        }


        // Exit

        if (input == 0) {

            printf("Exiting motor test.\n");

            break;
        }


        // Run selected test

        if (motor_execute(input) != 0) {
            fprintf(stderr, "Motor execution failed; stopping test.\n");
            exit_status = 1;
            break;
        }
    }


    // Clean up GPIOs

    motor_cleanup();


    printf("Motor test finished.\n");

    return exit_status;
}
