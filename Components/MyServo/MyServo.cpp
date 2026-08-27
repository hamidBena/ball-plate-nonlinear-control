#include "MyServo.h"
#include "esp_log.h"
#include <algorithm>

static const char* TAG = "MySERVO";

MyServo::MyServo() {
}

MyServo::~MyServo() {
}

esp_err_t MyServo::init(const Config& cfg) {
    if (initialized_) return ESP_OK;

    config_ = cfg;

    if (!configureLEDC()) {
        ESP_LOGE(TAG, "Failed to configure LEDC");
        return ESP_FAIL;
    }

    initialized_ = true;
    ESP_LOGI(TAG, "MyServo initialized on pin %d at %d Hz", config_.pin, (int)config_.freq_hz);

    // Drive instantly to baseline 0 (which applies offset internally)
    setAngle(0.0f);

    return ESP_OK;
}

bool MyServo::configureLEDC() {
    static uint8_t next_channel = 0;
    
    // Always use TIMER_0 so X and Y channels share a unified clock configuration block
    timer_num_ = LEDC_TIMER_0;  
    channel_num_ = (ledc_channel_t)(next_channel % 6);  
    next_channel++;
    
    // Configure LEDC timer (Safe to recall for multiple channels sharing this block)
    ledc_timer_config_t timer_conf = {
        .speed_mode = SPEED_MODE,
        .duty_resolution = (ledc_timer_bit_t)RESOLUTION_BITS,
        .timer_num = timer_num_,
        .freq_hz = config_.freq_hz,
        .clk_cfg = LEDC_AUTO_CLK,
    };

    if (ledc_timer_config(&timer_conf) != ESP_OK) {
        return false;
    }

    // Configure LEDC channel
    ledc_channel_config_t channel_conf = {
        .gpio_num = config_.pin,
        .speed_mode = SPEED_MODE,
        .channel = channel_num_,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = timer_num_,
        .duty = 0,
        .hpoint = 0
    };

    if (ledc_channel_config(&channel_conf) != ESP_OK) {
        return false;
    }

    return true;
}

// UNCHANGED: Your original pulse width mapping logic
uint32_t MyServo::angleToPulseUs(float angle) const {
    angle = std::max(config_.minAngle, std::min(config_.maxAngle, angle));
    return config_.min_pulse_us + static_cast<uint32_t>((angle / 180.0f) * (config_.max_pulse_us - config_.min_pulse_us));
}

// Rewritten to accept direct updates instantly on the caller thread
void MyServo::updatePWM(uint32_t pulse_us) {
    uint32_t period_us = 1000000 / config_.freq_hz;
    uint32_t max_duty = (1 << RESOLUTION_BITS) - 1;
    uint32_t duty = (pulse_us * max_duty) / period_us;

    duty = std::min(duty, max_duty);
    ledc_set_duty(SPEED_MODE, channel_num_, duty);
    ledc_update_duty(SPEED_MODE, channel_num_);
}

// UNCHANGED: Your exact offset calculations and clamping boundaries
void MyServo::setAngle(float angle) {
    if (!initialized_) {
        ESP_LOGW(TAG, "MyServo not initialized");
        return;
    } 
    if(invert) {
        angle = -angle;
    }
    angle += config_.angleOffset;

    // Enforce limits (e.g., 90 - 25 to 90 + 25)
    current_angle_ = std::max(config_.minAngle, std::min(config_.maxAngle, angle));
    
    // Process and pass immediately to hardware registers
    uint32_t pulse = angleToPulseUs(current_angle_);
    updatePWM(pulse);
}

float MyServo::getAngle() const {
    return current_angle_;
}

void MyServo::setPosition(float percentage) {
    if (!initialized_) {
        ESP_LOGW(TAG, "MyServo not initialized");
        return;
    }

    percentage = std::max(0.0f, std::min(100.0f, percentage));

    float angle = config_.minAngle + (percentage / 100.0f) * (config_.maxAngle - config_.minAngle);
    setAngle(angle - config_.angleOffset); // Counter-offset compensation to map cleanly into setAngle workflow
}

float MyServo::getPosition() const {
    float range = config_.maxAngle - config_.minAngle;
    if (range <= 0.0f) return 0.0f;
    return ((current_angle_ - config_.minAngle) / range) * 100.0f;
}

void MyServo::setPWMDuty(uint32_t duty) {
    if (!initialized_) {
        ESP_LOGW(TAG, "MyServo not initialized");
        return;
    }

    uint32_t max_duty = (1 << RESOLUTION_BITS) - 1;
    duty = std::min(duty, max_duty);
    ledc_set_duty(SPEED_MODE, channel_num_, duty);
    ledc_update_duty(SPEED_MODE, channel_num_);
}


void MyServo::handleCommand(const char* command) {
    char buf[32];
    int i = 0;

    while (*command && *command != ' ') {
        buf[i++] = *command++;
    }

    buf[i] = '\0';

    if(strcmp(buf, "invert") == 0) {
        invert = !invert;
        ESP_LOGI(TAG, "Invert set to %s", invert ? "true" : "false");
    }else if(strcmp(buf, "angle") == 0) {
        if (*command == ' ') {
            command++;
            float angle = atof(command);
            setAngle(angle);
            ESP_LOGI(TAG, "Angle set to %.2f", angle);
        }
    } else {
        ESP_LOGW(TAG, "Unknown command: %s", buf);
    }
}