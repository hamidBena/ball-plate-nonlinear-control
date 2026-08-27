#pragma once

#include <cstddef>
#include <stdint.h>
#include <esp_err.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/usb_serial_jtag.h"

class CommHandler {
public:
    struct Config {
        uint32_t txBufferSize = 256;
        uint32_t rxBufferSize = 256;
    };

    CommHandler() = default;
    ~CommHandler();

    esp_err_t init(const Config& cfg);
    void start();
    void stop();

private:
    void taskLoop();
    static void taskEntry(void* arg);
    void interpretData(const char* data, size_t length);

public:
    esp_err_t write(const void* data, size_t length);
    esp_err_t writeLine(const char* text);

private:
    Config config;

private:
    TaskHandle_t taskHandle = nullptr;
    //Queues* queues = nullptr;
    bool running = false;
};