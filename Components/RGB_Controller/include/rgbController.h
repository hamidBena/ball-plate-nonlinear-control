#pragma once

#include <stdint.h>
#include <esp_err.h>
#include "driver/rmt_tx.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

class RGBController {
public:
    struct Config {
        uint8_t gpio_pin;
        uint8_t led_count;
        uint8_t max_brightness;
    };

    // Default configuration for built-in LED
    static constexpr Config defaultConfig{
        .gpio_pin = 8,
        .led_count = 1,
        .max_brightness = 255
    };

    RGBController() = default;
    ~RGBController() { deinit(); }

    // Public API
    esp_err_t init(const Config &config);
    esp_err_t deinit();

    void start();          // Create the task
    void stop();           // Signal task to shutdown
    void setLedCount(uint8_t count) { led_count = count; }
    void setColor(uint8_t red, uint8_t green, uint8_t blue) {
        requestColor[0] = red;
        requestColor[1] = green;
        requestColor[2] = blue;
        Cycle = false;
    }
    esp_err_t setBrightness(uint8_t brightness);

    bool isRunning() const { return taskHandle != nullptr && !Shutdown; }

    void handleCommand(const char* command);

public:
    bool Cycle = false;    // If true, cycles colors automatically
    bool Shutdown = false;
    uint8_t brightness = 5;

private:
    // Task-related
    void run();
    static void taskEntry(void* arg);

    // Internal helpers
    esp_err_t set_color(uint8_t red, uint8_t green, uint8_t blue);
    esp_err_t clear();
    void CycleColors();
    void update();
    void shutdownAnimation();

    // state
    rmt_channel_handle_t tx_channel;
    uint8_t led_count;
    uint8_t currentColor[3] = {50, 50, 50};
    uint8_t requestColor[3] = {50, 50, 50};

    TaskHandle_t taskHandle = nullptr;
};
