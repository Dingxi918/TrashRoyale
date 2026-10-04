#include <errno.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "gpiod.h"

struct gpiod_chip { int open; };
struct gpiod_line { int offset; int requested; int value; };
static struct gpiod_chip chip;
static struct gpiod_line lines[32];
static int pulses[32];
static int direction_pulses[32][2];
static int first_direction[32];
static int failed_request = -1;
static int writes_before_failure = -1;
static int unrequested_writes;

void fake_clear_log(void)
{
    memset(pulses, 0, sizeof(pulses));
    memset(direction_pulses, 0, sizeof(direction_pulses));
    for (int index = 0; index < 32; index++)
        first_direction[index] = -1;
}

void fake_reset(void)
{
    memset(lines, 0, sizeof(lines));
    chip.open = 0;
    failed_request = -1;
    writes_before_failure = -1;
    unrequested_writes = 0;
    fake_clear_log();
}

void fake_fail_request(int offset) { failed_request = offset; }
void fake_fail_after_writes(int count) { writes_before_failure = count; }
int fake_pulses(int offset) { return pulses[offset]; }
int fake_first_direction(int offset) { return first_direction[offset]; }
int fake_direction_pulses(int offset, int direction) { return direction_pulses[offset][direction]; }
int fake_bad_writes(void) { return unrequested_writes; }
int fake_requested_count(void)
{
    int count = 0;
    for (int index = 0; index < 32; index++)
        count += lines[index].requested;
    return count;
}

struct gpiod_chip *gpiod_chip_open(const char *path)
{
    (void)path;
    chip.open = 1;
    return &chip;
}

struct gpiod_line *gpiod_chip_get_line(struct gpiod_chip *value, unsigned int offset)
{
    if (!value->open || offset >= 32)
        return NULL;
    lines[offset].offset = offset;
    return &lines[offset];
}

int gpiod_line_request_output(struct gpiod_line *line, const char *consumer, int value)
{
    (void)consumer;
    if (line->offset == failed_request) {
        errno = EBUSY;
        return -1;
    }
    line->requested = 1;
    line->value = value;
    return 0;
}

int gpiod_line_set_value(struct gpiod_line *line, int value)
{
    if (!line->requested) {
        unrequested_writes++;
        errno = EPERM;
        return -1;
    }
    if (writes_before_failure == 0) {
        writes_before_failure = -1;
        errno = EIO;
        return -1;
    }
    if (writes_before_failure > 0)
        writes_before_failure--;
    int dir_offset = line->offset == 17 ? 23 : line->offset == 24 ? 25 : line->offset == 5 ? 6 : -1;
    if (dir_offset >= 0 && value && !line->value) {
        if (!pulses[line->offset])
            first_direction[line->offset] = lines[dir_offset].value;
        pulses[line->offset]++;
        direction_pulses[line->offset][lines[dir_offset].value]++;
    }
    line->value = value;
    return 0;
}

void gpiod_line_release(struct gpiod_line *line) { line->requested = 0; }
void gpiod_chip_close(struct gpiod_chip *value) { value->open = 0; }
int fake_usleep(useconds_t duration) { (void)duration; return 0; }
int fake_nanosleep(const struct timespec *duration, struct timespec *remaining)
{
    (void)duration;
    (void)remaining;
    return 0;
}

unsigned int fake_sleep(unsigned int duration) { (void)duration; return 0; }
