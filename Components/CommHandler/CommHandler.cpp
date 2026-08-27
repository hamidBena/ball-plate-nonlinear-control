#include "CommHandler.h"
#include "esp_log.h"
#include <cstring>
#include <string>

static const char* TAG = "comms";

CommHandler::~CommHandler() {
    stop();
}

esp_err_t CommHandler::init(const Config& cfg) {
    config = cfg;

    if (!usb_serial_jtag_is_driver_installed()) {
        usb_serial_jtag_driver_config_t driverConfig = {
            .tx_buffer_size = config.txBufferSize,
            .rx_buffer_size = config.rxBufferSize,
        };

        esp_err_t ret = usb_serial_jtag_driver_install(&driverConfig);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "Failed to install USB Serial/JTAG driver: %s", esp_err_to_name(ret));
            return ret;
        }
    }

    return ESP_OK;
}

void CommHandler::start() {
    if (running) {
        return;
    }

    running = true;
    xTaskCreate(taskEntry, "CommHandlerTask", 4096, this, 5, &taskHandle);
}

void CommHandler::stop() {
    running = false;

    if (taskHandle != nullptr) {
        vTaskDelete(taskHandle);
        taskHandle = nullptr;
    }

    if (usb_serial_jtag_is_driver_installed()) {
        usb_serial_jtag_driver_uninstall();
    }
}

void CommHandler::taskEntry(void* arg) {
    auto* handler = static_cast<CommHandler*>(arg);
    handler->taskLoop();
}

void CommHandler::taskLoop() {
    char buffer[128];

    while (running) {
        int bytesRead = usb_serial_jtag_read_bytes(buffer, sizeof(buffer) - 1, pdMS_TO_TICKS(100));
        if (bytesRead > 0) {
            buffer[bytesRead] = '\0';
            ESP_LOGI(TAG, "USB RX: %s", buffer);
            interpretData(buffer, bytesRead);
        }

        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void CommHandler::interpretData(const char* data, size_t length) {
    std::string strData = std::string(data, length);

    if (strData.contains("Get")){
        
    }else if (strData.contains("Set")){

    }else{
        ESP_LOGW(TAG, "Received unrecognized command: %s", strData.c_str());
    }

}

esp_err_t CommHandler::write(const void* data, size_t length) {
    if (!usb_serial_jtag_is_driver_installed()) {
        return ESP_ERR_INVALID_STATE;
    }

    int written = usb_serial_jtag_write_bytes(data, length, pdMS_TO_TICKS(100));
    return (written == static_cast<int>(length)) ? ESP_OK : ESP_FAIL;
}

esp_err_t CommHandler::writeLine(const char* text) {
    if (text == nullptr) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t length = std::strlen(text);
    esp_err_t ret = write(text, length);
    if (ret != ESP_OK) {
        return ret;
    }

    const char newline[] = "\r\n";
    return write(newline, sizeof(newline) - 1);
}