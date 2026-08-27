#include "rgbController.h"
#include "driver/rmt_tx.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstring>
#include <cstdlib>

static const char *TAG = "RGB_CONTROLLER";

// Global encoder for RMT
static rmt_encoder_handle_t copy_encoder = nullptr;

esp_err_t RGBController::init(const Config &config) {
    if (config.led_count == 0) {
        ESP_LOGE(TAG, "LED count must be > 0");
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "Initializing RGB controller on GPIO %d with %d LEDs",
             config.gpio_pin, config.led_count);

    rmt_tx_channel_config_t tx_chan_config = {};
    tx_chan_config.clk_src = RMT_CLK_SRC_DEFAULT;
    tx_chan_config.gpio_num = gpio_num_t(config.gpio_pin);
    tx_chan_config.mem_block_symbols = 64;
    tx_chan_config.resolution_hz = 40 * 1000 * 1000;  // 40MHz clock
    tx_chan_config.trans_queue_depth = 4;

    esp_err_t ret = rmt_new_tx_channel(&tx_chan_config, &tx_channel);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create RMT TX channel: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = rmt_enable(tx_channel);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable RMT channel: %s", esp_err_to_name(ret));
        rmt_del_channel(tx_channel);
        return ret;
    }

    if (copy_encoder == nullptr) {
        rmt_copy_encoder_config_t encoder_config = {};
        ret = rmt_new_copy_encoder(&encoder_config, &copy_encoder);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "Failed to create RMT copy encoder: %s", esp_err_to_name(ret));
            rmt_disable(tx_channel);
            rmt_del_channel(tx_channel);
            return ret;
        }
    }

    led_count = config.led_count;
    brightness = config.max_brightness;

    clear();

    ESP_LOGI(TAG, "RGB controller initialized successfully");
    return ESP_OK;
}

esp_err_t RGBController::deinit() {
    stop();

    if (tx_channel == nullptr) {
        ESP_LOGW(TAG, "RGB controller not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t ret = rmt_disable(tx_channel);
    if (ret == ESP_OK) {
        ret = rmt_del_channel(tx_channel);
        tx_channel = nullptr;

        if (copy_encoder != nullptr) {
            rmt_del_encoder(copy_encoder);
            copy_encoder = nullptr;
        }

        ESP_LOGI(TAG, "RGB controller deinitialized");
    }
    return ret;
}

esp_err_t RGBController::set_color(uint8_t red, uint8_t green, uint8_t blue) {
    if (tx_channel == nullptr) {
        ESP_LOGE(TAG, "RGB controller not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    uint32_t r = (red * brightness) / 255;
    uint32_t g = (green * brightness) / 255;
    uint32_t b = (blue * brightness) / 255;

    currentColor[0] = r;
    currentColor[1] = g;
    currentColor[2] = b;

    int total_symbols = (led_count * 24) + 1;
    rmt_symbol_word_t *symbols = (rmt_symbol_word_t *)malloc(total_symbols * sizeof(rmt_symbol_word_t));
    if (!symbols) {
        ESP_LOGE(TAG, "Failed to allocate memory for RMT symbols");
        return ESP_ERR_NO_MEM;
    }

    int symbol_idx = 0;
    uint32_t pixel = ((uint32_t)g << 16) | ((uint32_t)r << 8) | b;

    for (int led = 0; led < led_count; led++) {
        for (int i = 23; i >= 0; i--) {
            uint32_t bit = (pixel >> i) & 1;
            if (bit) {
                symbols[symbol_idx].val = 0;
                symbols[symbol_idx].duration0 = 28; symbols[symbol_idx].level0 = 1;
                symbols[symbol_idx].duration1 = 24; symbols[symbol_idx].level1 = 0;
            } else {
                symbols[symbol_idx].val = 0;
                symbols[symbol_idx].duration0 = 14; symbols[symbol_idx].level0 = 1;
                symbols[symbol_idx].duration1 = 34; symbols[symbol_idx].level1 = 0;
            }
            symbol_idx++;
        }
    }

    // Reset pulse
    symbols[symbol_idx].val = 0;
    symbols[symbol_idx].duration0 = 0;
    symbols[symbol_idx].level0 = 0;
    symbols[symbol_idx].duration1 = 2000;
    symbols[symbol_idx].level1 = 0;
    symbol_idx++;

    rmt_transmit_config_t tx_config = {};
    tx_config.loop_count = 0;

    esp_err_t ret = rmt_transmit(tx_channel, copy_encoder, symbols,
                                 symbol_idx * sizeof(rmt_symbol_word_t), &tx_config);
    free(symbols);
    return ret;
}

esp_err_t RGBController::setBrightness(uint8_t new_brightness) {
    if (tx_channel == nullptr) {
        ESP_LOGE(TAG, "RGB controller not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    brightness = new_brightness;
    return set_color(currentColor[0], currentColor[1], currentColor[2]);
}

esp_err_t RGBController::clear() {
    if (tx_channel == nullptr) {
        ESP_LOGW(TAG, "RGB controller not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    return set_color(0, 0, 0);
}

void RGBController::run() {
    while (!Shutdown) {
        if (Cycle) CycleColors();
        set_color(requestColor[0], requestColor[1], requestColor[2]);
        vTaskDelay(pdMS_TO_TICKS(100)); // Update every 100 ms
    }

    ESP_LOGI(TAG, "RGBController task exiting");
    shutdownAnimation();
    taskHandle = nullptr;
    vTaskDelete(nullptr);
}

void RGBController::shutdownAnimation(){
    // flash red 3 times
    for (int i = 0; i < 3; i++) {
        set_color(255, 0, 0);
        vTaskDelay(pdMS_TO_TICKS(200));
        clear();
        vTaskDelay(pdMS_TO_TICKS(200));
    }
    // fade out
    set_color(255,255,255);
    for (int step = brightness; step >= 0; step -= 5) {
        setBrightness(step);
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void RGBController::taskEntry(void *arg) {
    RGBController *controller = static_cast<RGBController*>(arg);
    controller->run();
}

void RGBController::start() {
    if (taskHandle != nullptr) {
        ESP_LOGW(TAG, "Task already running");
        return;
    }
    Shutdown = false;
    xTaskCreate(
        taskEntry,
        "RGBControllerTask",
        2048,
        this,
        5,
        &taskHandle
    );
}

void RGBController::stop() {
    if (taskHandle == nullptr) return;
    Shutdown = true;
}
  
void RGBController::CycleColors() {
    static uint8_t hue = 0;
    hue = (hue + 1) % 256;

    uint8_t r, g, b;
    if (hue < 85) {
        r = hue * 3;
        g = 255 - hue * 3;
        b = 0;
    } else if (hue < 170) {
        hue -= 85;
        r = 255 - hue * 3;
        g = 0;
        b = hue * 3;
    } else {
        hue -= 170;
        r = 0;
        g = hue * 3;
        b = 255 - hue * 3;
    }
    requestColor[0] = r;
    requestColor[1] = g;
    requestColor[2] = b;
}

void RGBController::handleCommand(const char* command) {
    char buf[32];
    int i = 0;

    while (*command && *command != ' ' && i < (int)sizeof(buf) - 1) {
        buf[i++] = *command++;
    }

    buf[i] = '\0';

    if(strcmp(buf, "cycle") == 0) {
        Cycle = !Cycle;
        ESP_LOGI(TAG, "Cycle mode %s", Cycle ? "enabled" : "disabled");
    } else if (strcmp(buf, "color") == 0) {
        if (*command == ' ') {
            command++;
            int r, g, b;
            if (sscanf(command, "%d %d %d", &r, &g, &b) == 3) {
                setColor(r, g, b);
                ESP_LOGI(TAG, "Color set to (%d, %d, %d)", r, g, b);
            } else {
                ESP_LOGW(TAG, "Invalid color command format");
            }
        }
    } else if (strcmp(buf, "brightness") == 0) {
        if (*command == ' ') {
            command++;
            int b;
            if (sscanf(command, "%d", &b) == 1) {
                setBrightness(b);
                ESP_LOGI(TAG, "Brightness set to %d", b);
            } else {
                ESP_LOGW(TAG, "Invalid brightness command format");
            }
        }
    } else {
        ESP_LOGW(TAG, "Unknown command: %s", buf);
    }
}
