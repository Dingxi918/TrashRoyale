#include <stdio.h>

#include "motor.h"

int main(void)
{
    int input;


    // Initialize motors

    if (motor_init() != 0) {

        printf("Motor initialization failed.\n");

        return 1;
    }


    printf("\n");
    printf("===============================\n");
    printf("      MOTOR TEST PROGRAM\n");
    printf("===============================\n");

    printf("1 - M1 CCW 45, M2 CCW 45\n");
    printf("2 - M1 CCW 45, M2 CW 45\n");
    printf("3 - M1 CW 45,  M3 CCW 45\n");
    printf("4 - M1 CW 45,  M3 CW 45\n");
    printf("5 - ERROR CASE / NO MOVEMENT\n");
    printf("0 - EXIT\n");

    printf("===============================\n");


    while (1) {

        printf("\nEnter test value: ");

        if (scanf("%d", &input) != 1) {

            printf("Invalid input.\n");

            // Clear invalid input

            while (getchar() != '\n');

            continue;
        }


        // Exit

        if (input == 0) {

            printf("Exiting motor test.\n");

            break;
        }


        // Run selected test

        motor_execute(input);
    }


    // Clean up GPIOs

    motor_cleanup();


    printf("Motor test finished.\n");

    return 0;
}
