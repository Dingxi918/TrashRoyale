#include <Arduino.h>
#include "esp_camera.h"
#include "esp_log.h"

// Common ESP32-S3-CAM N16R8 / ESP32-S3-EYE-style camera pin mapping.
#define CAM_PIN_PWDN  -1
#define CAM_PIN_RESET -1
#define CAM_PIN_XCLK  15
#define CAM_PIN_SIOD  4
#define CAM_PIN_SIOC  5
#define CAM_PIN_D0    11
#define CAM_PIN_D1    9
#define CAM_PIN_D2    8
#define CAM_PIN_D3    10
#define CAM_PIN_D4    12
#define CAM_PIN_D5    18
#define CAM_PIN_D6    17
#define CAM_PIN_D7    16
#define CAM_PIN_VSYNC 6
#define CAM_PIN_HREF  7
#define CAM_PIN_PCLK  13

// Must match the Raspberry Pi receiver's --baud argument.
constexpr uint32_t SERIAL_BAUD = 460800;

// Raspberry Pi sends one 'G' byte to request one JPEG.
constexpr uint8_t FRAME_REQUEST = 'G';
constexpr uint8_t FRAME_MAGIC[4] = {'C', 'A', 'M', '1'};

bool cameraReady = false;

bool writeAll(const uint8_t *data, size_t length) {
    while (length > 0) {
        const size_t written = Serial.write(data, length);
        if (written == 0) {
            delay(1);
            continue;
        }
        data += written;
        length -= written;
    }
    return true;
}

void sendHeader(uint32_t jpegLength) {
    uint8_t header[8] = {
        FRAME_MAGIC[0],
        FRAME_MAGIC[1],
        FRAME_MAGIC[2],
        FRAME_MAGIC[3],
        static_cast<uint8_t>(jpegLength),
        static_cast<uint8_t>(jpegLength >> 8),
        static_cast<uint8_t>(jpegLength >> 16),
        static_cast<uint8_t>(jpegLength >> 24),
    };
    writeAll(header, sizeof(header));
}

bool initializeCamera() {
    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;

    config.pin_d0 = CAM_PIN_D0;
    config.pin_d1 = CAM_PIN_D1;
    config.pin_d2 = CAM_PIN_D2;
    config.pin_d3 = CAM_PIN_D3;
    config.pin_d4 = CAM_PIN_D4;
    config.pin_d5 = CAM_PIN_D5;
    config.pin_d6 = CAM_PIN_D6;
    config.pin_d7 = CAM_PIN_D7;
    config.pin_xclk = CAM_PIN_XCLK;
    config.pin_pclk = CAM_PIN_PCLK;
    config.pin_vsync = CAM_PIN_VSYNC;
    config.pin_href = CAM_PIN_HREF;
    config.pin_sccb_sda = CAM_PIN_SIOD;
    config.pin_sccb_scl = CAM_PIN_SIOC;
    config.pin_pwdn = CAM_PIN_PWDN;
    config.pin_reset = CAM_PIN_RESET;

    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 10;            // Lower value means higher quality.

    if (psramFound()) {
        config.fb_location = CAMERA_FB_IN_PSRAM;
        config.fb_count = 2;
        config.grab_mode = CAMERA_GRAB_LATEST;
    } else {
        config.fb_location = CAMERA_FB_IN_DRAM;
        config.fb_count = 1;
        config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    }

    const esp_err_t result = esp_camera_init(&config);
    if (result != ESP_OK) {
        Serial.printf("CAMERA_INIT_ERROR:0x%x\n", result);
        return false;
    }

    // Correct the common OV3660 default orientation and colour settings.
    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor != nullptr && sensor->id.PID == OV3660_PID) {
        sensor->set_vflip(sensor, 1);
        sensor->set_brightness(sensor, 1);
        sensor->set_saturation(sensor, -2);
    }

    return true;
}

void sendFrame() {
    if (!cameraReady) {
        sendHeader(0);
        Serial.flush();
        return;
    }

    camera_fb_t *frame = esp_camera_fb_get();
    if (frame == nullptr || frame->format != PIXFORMAT_JPEG) {
        if (frame != nullptr) {
            esp_camera_fb_return(frame);
        }
        sendHeader(0);
        Serial.flush();
        return;
    }

    sendHeader(static_cast<uint32_t>(frame->len));
    writeAll(frame->buf, frame->len);
    Serial.flush();
    esp_camera_fb_return(frame);
}

void setup() {
    Serial.begin(SERIAL_BAUD);
    Serial.setDebugOutput(false);
    delay(1000);

    // Disable runtime framework logs so they cannot appear inside JPEG data.
    esp_log_level_set("*", ESP_LOG_NONE);

    cameraReady = initializeCamera();
    if (cameraReady) {
        Serial.println("READY");
    }
}

void loop() {
    while (Serial.available() > 0) {
        const int command = Serial.read();
        if (command == FRAME_REQUEST) {
            sendFrame();
        }
    }
    delay(1);
}