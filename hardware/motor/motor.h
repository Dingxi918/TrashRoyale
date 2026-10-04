#ifndef MOTOR_H
#define MOTOR_H

#define MOTOR_NO_MOVEMENT 5

/* Acquire the GPIO outputs. Returns 0 on success, -1 on failure. */
int motor_init(void);

/* Run one complete out/hold/return cycle. Input 5 does not move any motor.
 * Returns 0 on success, -1 on invalid input, uninitialized GPIO, or GPIO failure.
 * After a failed move, inspect the gate positions before cleanup/reinitializing.
 */
int motor_execute(int input);

/* Shut down and release the GPIO outputs. Safe to call repeatedly. */
void motor_cleanup(void);

#endif
