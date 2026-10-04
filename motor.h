#ifndef MOTOR_H
#define MOTOR_H

#include <gpiod.h>

// Initialize the three A4988 drivers
int motor_init(void);

// Execute one of the five combinations
void motor_execute(int input);

// Shut down and release GPIOs
void motor_cleanup(void);

#endif
