#pragma once

#include <cstdint>
#include <cmath>
#include "driver/gpio.h"
#include "driver/ledc.h"

class MyServo {
public:
    /**
     * @brief Servo configuration structure
     */
    struct Config {
        gpio_num_t pin;                    ///< GPIO
        float maxAngle = 90.0f + 25.0f;    ///< Maximum angle
        float minAngle = 90.0f - 25.0f;    ///< Minimum angle
        float angleOffset = 90.0f;         ///< Angle offset
        uint32_t freq_hz = 250;            ///< Any target frequency (50 to 330Hz)
        uint32_t min_pulse_us = 500;
        uint32_t max_pulse_us = 2500;
    };

    MyServo();
    ~MyServo();

    esp_err_t init(const Config& cfg);
    void setAngle(float angle);
    float getAngle() const;
    void setPosition(float percentage);
    float getPosition() const;
    void setPWMDuty(uint32_t duty);
    bool isInitialized() const { return initialized_; }

    void handleCommand(const char* command);

public:
    bool invert = false;

private:
    static const uint8_t RESOLUTION_BITS = 14;      ///< 14-bit resolution is safe and accurate for any servo frequency
    static const ledc_mode_t SPEED_MODE = LEDC_LOW_SPEED_MODE;
    
    bool configureLEDC();
    uint32_t angleToPulseUs(float angle) const;
    void updatePWM(uint32_t pulse_us);

    Config config_;
    float current_angle_ = 0.0f;
    bool initialized_ = false;
    ledc_timer_t timer_num_;    
    ledc_channel_t channel_num_;
};
