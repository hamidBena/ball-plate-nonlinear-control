#pragma once

#include <cstdint>
#include "esp_err.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

class IMU {
public:
	struct Config {
		i2c_port_num_t i2c_port = I2C_NUM_0;
		gpio_num_t sda_pin = GPIO_NUM_5;
		gpio_num_t scl_pin = GPIO_NUM_6;
		uint32_t i2c_freq_hz = 100000;  // 100 kHz
		uint8_t address = 0x69;  // BMI160 address when SDO is high
		uint32_t sample_period_ms = 80;
		bool use_internal_pullup = true;
	};

	struct Data {
		float accel_x_g = 0.0f;
		float accel_y_g = 0.0f;
		float accel_z_g = 0.0f;
		float gyro_x_dps = 0.0f;
		float gyro_y_dps = 0.0f;
		float gyro_z_dps = 0.0f;
		uint32_t tick_ms = 0;
		bool valid = false;
	};

	IMU() = default;
	~IMU();

	esp_err_t init(const Config& cfg);
	void start();
	void stop();

	Data getLatestData() const { return latestData; }
	bool isInitialized() const { return initialized; }
	void displayData() const;

private:
	static constexpr uint8_t BMI160_REG_CHIP_ID = 0x00;
	static constexpr uint8_t BMI160_REG_GYR_DATA = 0x0C;
	static constexpr uint8_t BMI160_REG_ACC_DATA = 0x12;
	static constexpr uint8_t BMI160_REG_ACC_CONF = 0x40;
	static constexpr uint8_t BMI160_REG_ACC_RANGE = 0x41;
	static constexpr uint8_t BMI160_REG_GYR_CONF = 0x42;
	static constexpr uint8_t BMI160_REG_GYR_RANGE = 0x43;
	static constexpr uint8_t BMI160_REG_CMD = 0x7E;

	static constexpr uint8_t BMI160_CHIP_ID = 0xD1;

	static constexpr uint8_t BMI160_CMD_SOFT_RESET = 0xB6;
	static constexpr uint8_t BMI160_CMD_ACC_NORMAL = 0x11;
	static constexpr uint8_t BMI160_CMD_GYR_NORMAL = 0x15;

	esp_err_t readRegister(uint8_t reg, uint8_t* data, size_t len);
	esp_err_t writeRegister(uint8_t reg, uint8_t value);
	esp_err_t configureSensor();
	esp_err_t readSample();

	void taskLoop();
	static void taskEntry(void* arg);

private:
	Config config;
	Data latestData;

	i2c_master_bus_handle_t busHandle = nullptr;
	i2c_master_dev_handle_t devHandle = nullptr;
	TaskHandle_t taskHandle = nullptr;

	bool initialized = false;
	bool running = false;
};
