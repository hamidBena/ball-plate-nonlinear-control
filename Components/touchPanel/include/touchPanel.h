#pragma once

#include <stdint.h>
#include <esp_err.h>
#include "driver/gpio.h"
#include "esp_adc/adc_oneshot.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

class KalmanFilter {
    private:
        float position    = 0;
        float velocity    = 0;
        float p_pos       = 1;
        float p_vel       = 1;
        float Q_pos;
        float Q_vel;
        float R;
        bool  initialized = false;

    public:
        KalmanFilter(float q_position, float q_velocity, float sensor_noise)
            : Q_pos(q_position), Q_vel(q_velocity), R(sensor_noise) {}

        float update(float measurement, float dt) {
            if (!initialized) {
                position    = measurement;
                velocity    = 0;
                p_pos       = 1;
                p_vel       = 1;
                initialized = true;
                return position;
            }

            // predict
            position = position + velocity * dt;
            p_pos    = p_pos + p_vel * dt * dt + Q_pos;
            p_vel    = p_vel + Q_vel;

            // update
            float K     = p_pos / (p_pos + R);
            float K_vel = p_vel * dt / (p_pos + R);
            float inn   = measurement - position;

            position = position + K     * inn;
            velocity = velocity + K_vel * inn;
            p_pos    = (1 - K)           * p_pos;
            p_vel    = (1 - K_vel * dt)  * p_vel;

            return position;
        }

        float getVelocity() { return velocity; }
        float getPosition() { return position; }
};

class TouchPanel {
public:
    struct Config {
        // xADC is the same pin as the xM
        gpio_num_t xP;      // SEND 3.3v
        gpio_num_t xM;      // set to ground 
        adc_channel_t xADC;                     //read analog
        
        // yADC is the same pin as the yM
        gpio_num_t yP;                          // SEND 3.3v
        gpio_num_t yM;                          // set to ground
        adc_channel_t yADC; //read analog 
        int touch_threshold;   // Minimum pressure required (higher = more pressure needed)
    };

    TouchPanel() : kfX(0.f, 2.5f, 0.005f), kfY(0.f, 2.5f, 0.005f) {}
    ~TouchPanel();

    esp_err_t init(const Config& cfg);
    void start();
    void stop();

    bool isTouched();

private:
    void taskLoop();
    static void taskEntry(void* arg);

    void resetPins();

    float getMedian(float arr[], int size);
    float stddeviation(float arr[], int size);

    float normalizeX(float voltage);
    float normalizeY(float voltage);

private:
    Config config;
    adc_oneshot_unit_handle_t adcHandle = nullptr;

public:
    bool touched = false;
    float xVoltage = 0;
    float yVoltage = 0;
    float normX = 0;
    float normY = 0;
    float xFiltered = 0;
    float yFiltered = 0;
    float xVelocity = 0;
    float yVelocity = 0;
    size_t samples = 7;
    float xReadings [7];
    float yReadings [7];

    int consecutiveRejects = 0;
    int maxConsecutiveRejects = 5;
    
    bool running = false;
    
private:
    int lastPressure = 0;
    const float Hz = 250.f;

    KalmanFilter kfX;
    KalmanFilter kfY;

    TaskHandle_t taskHandle = nullptr;
};