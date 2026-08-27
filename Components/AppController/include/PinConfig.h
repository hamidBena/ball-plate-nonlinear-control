#pragma once

#include "driver/gpio.h"

// TouchPanel pins
#define TOUCH_PANEL_X_PLUS GPIO_NUM_2  //was GPIO_NUM_6, but conflicts with IMU I2C
#define TOUCH_PANEL_X_MINUS GPIO_NUM_1  //was GPIO_NUM_5, but conflicts with IMU I2C
#define TOUCH_PANEL_X_ADC ADC_CHANNEL_1

#define TOUCH_PANEL_Y_PLUS GPIO_NUM_10
#define TOUCH_PANEL_Y_MINUS GPIO_NUM_0
#define TOUCH_PANEL_Y_ADC ADC_CHANNEL_0

#define TOUCH_PANEL_THRESHOLD 130   // Adjust for touch sensitivity

// Servo pins
#define SERVO1_PIN GPIO_NUM_4
#define SERVO2_PIN GPIO_NUM_5  // TODO: Verify if available

// CommHandler
// Uses built-in USB-C

// IMU (BMI160) I2C pins
#define IMU_I2C_SDA GPIO_NUM_6
#define IMU_I2C_SCL GPIO_NUM_7
