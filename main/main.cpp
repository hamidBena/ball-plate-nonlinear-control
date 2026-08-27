#include "sdkconfig.h"

#include <stdio.h>
#include <string.h>

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

#include "esp_log.h"
#include "AppController.h"

static const char* TAG = "APP_MAIN";

static AppController app_controller;

struct SerialCommand {
    char text[128];
};

static QueueHandle_t g_command_queue;

static void usb_reader_task(void*)
{
    char buffer[128];
    size_t pos = 0;

    while (true) {

        int c = fgetc(stdin);

        if (c == EOF) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        if (c == '\r' || c == '\n') {

            if (pos > 0) {
                buffer[pos] = '\0';

                SerialCommand cmd{};
                strncpy(cmd.text, buffer, sizeof(cmd.text) - 1);

                xQueueSend(g_command_queue, &cmd, 0);

                pos = 0;
            }
        }
        else if (pos < sizeof(buffer) - 1) {
            buffer[pos++] = (char)c;
        }

        taskYIELD();
    }
}

extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "Starting application");

    esp_err_t ret = app_controller.init({});
    if (ret != ESP_OK) {
        ESP_LOGE(TAG,
                 "Failed to initialize AppController: %s",
                 esp_err_to_name(ret));
        return;
    }

    app_controller.start();

    g_command_queue = xQueueCreate(8, sizeof(SerialCommand));

    xTaskCreate(
        usb_reader_task,
        "usb_reader",
        4096,
        nullptr,
        5,
        nullptr);

    SerialCommand cmd;

    while (true) {

        if (xQueueReceive(
                g_command_queue,
                &cmd,
                pdMS_TO_TICKS(20)))
        {
            //ESP_LOGI(TAG, "Received command: '%s'", cmd.text);
            app_controller.handleCommand(cmd.text);
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}