#include "touchPanel.h"
#include "esp_log.h"
#include <cmath>
#include <algorithm>

static const char* TAG = "TOUCH_PANEL";

TouchPanel::~TouchPanel() {
    stop();
    if (adcHandle) {
        adc_oneshot_del_unit(adcHandle);
        adcHandle = nullptr;
    }
}

esp_err_t TouchPanel::init(const Config& cfg) {
    config = cfg;

    adc_oneshot_unit_init_cfg_t unit_cfg = {
        .unit_id = ADC_UNIT_1,
        .clk_src = ADC_DIGI_CLK_SRC_DEFAULT,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    esp_err_t ret = adc_oneshot_new_unit(&unit_cfg, &adcHandle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create ADC unit for X axis: %s", esp_err_to_name(ret));
        return ret;
    }

    adc_oneshot_chan_cfg_t chan_cfg = {
        .atten = ADC_ATTEN_DB_12,        // 0-3.3 V
        .bitwidth = ADC_BITWIDTH_DEFAULT // 12-bit
    };
    ret = adc_oneshot_config_channel(adcHandle, config.xADC, &chan_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure X axis ADC channel: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = adc_oneshot_config_channel(adcHandle, config.yADC, &chan_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure Y axis ADC channel: %s", esp_err_to_name(ret));
        return ret;
    }

    return ESP_OK;
}

void TouchPanel::start() {
    if (running) return;
    running = true;

    xTaskCreate(
        taskEntry,
        "TouchPanelTask",
        4096,
        this,
        5,
        &taskHandle
    );
}

void TouchPanel::stop() {
    running = false;
    if (taskHandle) {
        vTaskDelete(taskHandle);
        taskHandle = nullptr;
    }
}

void TouchPanel::taskEntry(void* arg) {
    TouchPanel* tp = static_cast<TouchPanel*>(arg);
    tp->taskLoop();
}

float TouchPanel::getMedian(float arr[], int size) {
    std::nth_element(arr, arr + size / 2, arr + size);
    float upper = arr[size / 2];
    if (size % 2 == 0) {
        std::nth_element(arr, arr + size / 2 - 1, arr + size / 2);
        float lower = arr[size / 2 - 1];
        return (upper + lower) / 2.0f;
    }
    return upper;
}

float TouchPanel::stddeviation(float arr[], int size) {
    float mean = 0.0f;
    for (int i = 0; i < size; i++) {
        mean += arr[i];
    }
    mean /= size;

    float variance = 0.0f;
    for (int i = 0; i < size; i++) {
        variance += (arr[i] - mean) * (arr[i] - mean);
    }
    variance /= size;

    return sqrtf(variance);
}

void TouchPanel::taskLoop() {
    while (true) {
        if(!running){
            touched = false;
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        float dt = 1000.0f / Hz;

        
        // ---- X axis block ----
        gpio_set_direction(config.xP, GPIO_MODE_OUTPUT);
        gpio_set_level(config.xP, 1);   // X+ = 3.3V
        gpio_set_direction(config.xM, GPIO_MODE_OUTPUT);
        gpio_set_level(config.xM, 0);   // X- = GND
        gpio_set_direction(config.yP, GPIO_MODE_INPUT);
        gpio_set_direction(config.yM, GPIO_MODE_INPUT);
        esp_rom_delay_us(500);
        
        for (int i = 0; i < samples; i++) {
            int raw = 0;
            if (adcHandle) adc_oneshot_read(adcHandle, config.yADC, &raw);
            xReadings[i] = raw * 3.3f / 4095.0f;
            esp_rom_delay_us(150);
        }
        
        resetPins();
        
        // ---- Y axis block ----
        gpio_set_direction(config.yP, GPIO_MODE_OUTPUT);
        gpio_set_level(config.yP, 1);   // Y+ = 3.3V
        gpio_set_direction(config.yM, GPIO_MODE_OUTPUT);
        gpio_set_level(config.yM, 0);   // Y- = GND
        gpio_set_direction(config.xP, GPIO_MODE_INPUT);
        gpio_set_direction(config.xM, GPIO_MODE_INPUT);
        esp_rom_delay_us(500);

        for (int i = 0; i < samples; i++) {
            int raw = 0;
            if (adcHandle) adc_oneshot_read(adcHandle, config.xADC, &raw);
            yReadings[i] = raw * 3.3f / 4095.0f;
            esp_rom_delay_us(150);
        }
        
        resetPins();

        float Xstddev = stddeviation(xReadings, samples);
        float Ystddev = stddeviation(yReadings, samples);
        float devThreshold = 0.01f; // tune

        if(Xstddev > devThreshold || Ystddev > devThreshold) {
            consecutiveRejects++;
            if(consecutiveRejects < maxConsecutiveRejects) {
                vTaskDelay(pdMS_TO_TICKS(dt/4));    //  while the consecutive rejects are still low, try to get a new reading quickly, in case this is just a temporary noise spike
            }else{
                vTaskDelay(pdMS_TO_TICKS(dt));
            }
            touched = false;
            
            continue;
        }else{
            //good reading block - reset consecutive rejects, set touched = true
            consecutiveRejects = 0;
            touched = true;
        }
        

        xVoltage = getMedian(xReadings, samples);
        yVoltage = getMedian(yReadings, samples);

        float lastnormx = normX;
        float lastnormy = normY;

        normX = normalizeX(xVoltage);
        normY = normalizeY(yVoltage);

        xFiltered = kfX.update(normX, 1/Hz);
        yFiltered = kfY.update(normY, 1/Hz);
        xVelocity = kfX.getVelocity();
        yVelocity = kfY.getVelocity();
       // float lastXvel = xVelocity;
       // float lastYvel = yVelocity;
//
       // xVelocity = (normX - lastnormx)/(dt/1000.0f) * 0.7f + lastXvel * 0.3f;
       // yVelocity = (normY - lastnormy)/(dt/1000.0f) * 0.7f + lastYvel * 0.3f;

        //printf("Filtered X: %.3f | Filtered Y: %.3f || Velocity X: %.3f | Velocity Y: %.3f\n", xFiltered, yFiltered, xVelocity, yVelocity);
        //printf("normal X: %.3f | normal Y: %.3f || Velocity X: %.3f | Velocity Y: %.3f\n", normX, normY, (normX-lastnormx)/(dt/1000.0f), (normY-lastnormy)/(dt/1000.0f));

        //printf("Normalized X: %.3f | Normalized Y: %.3f\n", normX, normY);
        vTaskDelay(pdMS_TO_TICKS(dt));
    }
}

bool TouchPanel::isTouched() {
    return touched;
}

void TouchPanel::resetPins(){
    gpio_reset_pin(config.xP);
    gpio_reset_pin(config.xM);
    gpio_reset_pin(config.yP);
    gpio_reset_pin(config.yM);
}

float TouchPanel::normalizeX(float voltage) {
    const float inMin = 0.4f, inMax = 2.58f;
    const float outMin = -130.0f, outMax = 130.0f;

    float v = std::max(inMin, std::min(inMax, voltage));
    return outMin + (v - inMin) * (outMax - outMin) / (inMax - inMin);
}

float TouchPanel::normalizeY(float voltage) {
    const float inMin = 0.45f, inMax = 2.5f;
    //const float inMin = 0.109f, inMax = 0.425f;
    const float outMin = -100.0f, outMax = 100.0f;

    float v = std::max(inMin, std::min(inMax, voltage));
    return outMin + (v - inMin) * (outMax - outMin) / (inMax - inMin);
}