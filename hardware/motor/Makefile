CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra
CPPFLAGS += -D_DEFAULT_SOURCE
LDLIBS += -lgpiod

.PHONY: all
all: libmotor.so

libmotor.so: motor.c motor.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -std=c11 -fPIC -shared -o $@ motor.c $(LDFLAGS) $(LDLIBS)

motor_test: test.c motor.c motor.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -std=c11 -o $@ test.c motor.c $(LDFLAGS) $(LDLIBS)
