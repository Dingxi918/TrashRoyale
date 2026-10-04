/* Test-only subset of the libgpiod v1 interface. Never linked into the Pi build. */
#ifndef TEST_GPIOD_H
#define TEST_GPIOD_H
struct gpiod_chip;
struct gpiod_line;
struct gpiod_chip *gpiod_chip_open(const char *path);
struct gpiod_line *gpiod_chip_get_line(struct gpiod_chip *chip, unsigned int offset);
int gpiod_line_request_output(struct gpiod_line *line, const char *consumer, int value);
int gpiod_line_set_value(struct gpiod_line *line, int value);
void gpiod_line_release(struct gpiod_line *line);
void gpiod_chip_close(struct gpiod_chip *chip);
#endif
