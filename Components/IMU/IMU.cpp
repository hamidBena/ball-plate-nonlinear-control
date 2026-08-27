#include "IMU.h"

#include "esp_log.h"

static const char* TAG = "IMU";

IMU::~IMU() {
	stop();

	if (devHandle && busHandle) {
		i2c_master_bus_rm_device(devHandle);
		devHandle = nullptr;
	}

	if (busHandle) {
		i2c_del_master_bus(busHandle);
		busHandle = nullptr;
	}
}

esp_err_t IMU::init(const Config& cfg) {
	if (initialized) {
		return ESP_OK;
	}

	config = cfg;

	ESP_LOGI(TAG, "Initializing I2C bus: port=%d, SDA=%d, SCL=%d, freq=%d Hz, addr=0x%02X",
			 static_cast<int>(config.i2c_port),
			 static_cast<int>(config.sda_pin),
			 static_cast<int>(config.scl_pin),
			 config.i2c_freq_hz,
			 config.address);

	i2c_master_bus_config_t busConfig = {
		.i2c_port = config.i2c_port,
		.sda_io_num = config.sda_pin,
		.scl_io_num = config.scl_pin,
		.clk_source = I2C_CLK_SRC_DEFAULT,
		.glitch_ignore_cnt = 7,
		.intr_priority = 0,
		.trans_queue_depth = 0,
		.flags = {
			.enable_internal_pullup = config.use_internal_pullup,
			.allow_pd = 0,
		},
	};

	esp_err_t ret = i2c_new_master_bus(&busConfig, &busHandle);
	if (ret != ESP_OK) {
		ESP_LOGE(TAG, "Failed to create I2C master bus: %s", esp_err_to_name(ret));
		return ret;
	}
	ESP_LOGI(TAG, "I2C bus created successfully");

	i2c_device_config_t devConfig = {
		.dev_addr_length = I2C_ADDR_BIT_LEN_7,
		.device_address = config.address,
		.scl_speed_hz = config.i2c_freq_hz,
		.scl_wait_us = 0,
		.flags = {
			.disable_ack_check = 0,
		},
	};

	ret = i2c_master_bus_add_device(busHandle, &devConfig, &devHandle);
	if (ret != ESP_OK) {
		ESP_LOGE(TAG, "Failed to add BMI160 device: %s", esp_err_to_name(ret));
		return ret;
	}
	ESP_LOGI(TAG, "I2C device added successfully at address 0x%02X", config.address);

	// Scan for I2C devices on the bus to diagnose connectivity
	ESP_LOGI(TAG, "Scanning I2C bus for connected devices...");
	bool deviceFound = false;
	for (uint8_t addr = 0x08; addr < 0x78; addr++) {
		i2c_device_config_t scanConfig = {
			.dev_addr_length = I2C_ADDR_BIT_LEN_7,
			.device_address = addr,
			.scl_speed_hz = 100000,
			.scl_wait_us = 0,
			.flags = {
				.disable_ack_check = 1,  // Ignore ACK for scanning
			},
		};
		i2c_master_dev_handle_t scanHandle = nullptr;
		esp_err_t scanRet = i2c_master_bus_add_device(busHandle, &scanConfig, &scanHandle);
		if (scanRet == ESP_OK) {
			uint8_t reg = 0x00;  // Chip ID register
			uint8_t testByte = 0;
			scanRet = i2c_master_transmit_receive(scanHandle, &reg, 1, &testByte, 1, 100);
			if (scanRet == ESP_OK) {
				ESP_LOGI(TAG, "  Found device at address 0x%02X (chip ID: 0x%02X)", addr, testByte);
				deviceFound = true;
			}
			i2c_master_bus_rm_device(scanHandle);
		}
	}
	if (!deviceFound) {
		ESP_LOGW(TAG, "No I2C devices found on bus. Check wiring and pull-ups.");
	}

	// Power-on delay for BMI160 to stabilize
	vTaskDelay(pdMS_TO_TICKS(50));

	// Attempt soft reset to wake up device
	ESP_LOGI(TAG, "Sending soft reset command to BMI160 at address 0x%02X...", config.address);
	ret = writeRegister(BMI160_REG_CMD, BMI160_CMD_SOFT_RESET);
	if (ret != ESP_OK) {
		ESP_LOGW(TAG, "Soft reset write failed: %s", esp_err_to_name(ret));
	}
	
	// Wait after soft reset
	vTaskDelay(pdMS_TO_TICKS(100));

	uint8_t chipId = 0;
	ESP_LOGI(TAG, "Reading BMI160 chip ID from register 0x%02X at address 0x%02X...", BMI160_REG_CHIP_ID, config.address);
	ret = readRegister(BMI160_REG_CHIP_ID, &chipId, 1);
	if (ret != ESP_OK) {
		ESP_LOGE(TAG, "Failed to read BMI160 chip ID at address 0x%02X (error: %s)", config.address, esp_err_to_name(ret));
		
		// Try alternate address
		ESP_LOGW(TAG, "Trying alternate I2C address 0x68 (SDO pulled low)...");
		i2c_device_config_t altDevConfig = {
			.dev_addr_length = I2C_ADDR_BIT_LEN_7,
			.device_address = 0x68,
			.scl_speed_hz = config.i2c_freq_hz,
			.scl_wait_us = 0,
			.flags = {
				.disable_ack_check = 0,
			},
		};
		i2c_master_dev_handle_t altDevHandle = nullptr;
		ret = i2c_master_bus_add_device(busHandle, &altDevConfig, &altDevHandle);
		if (ret == ESP_OK) {
			ret = i2c_master_transmit_receive(altDevHandle, &BMI160_REG_CHIP_ID, 1, &chipId, 1, -1);
			if (ret == ESP_OK) {
				ESP_LOGI(TAG, "Device found at 0x68! Chip ID: 0x%02X", chipId);
				i2c_master_bus_rm_device(devHandle);  // Remove old address
				devHandle = altDevHandle;
				config.address = 0x68;
			} else {
				i2c_master_bus_rm_device(altDevHandle);
				ESP_LOGE(TAG, "Device not found at 0x68 either. Hardware issue likely.");
				ESP_LOGE(TAG, "Troubleshooting:");
				ESP_LOGE(TAG, "  - Verify BMI160 is powered (3.3V)");
				ESP_LOGE(TAG, "  - Check SDA connected to GPIO5, SCL to GPIO6");
				ESP_LOGE(TAG, "  - Verify 10k pull-up resistors on SDA and SCL");
				ESP_LOGE(TAG, "  - Check for short circuits on the I2C bus");
				return ESP_ERR_NOT_FOUND;
			}
		} else {
			ESP_LOGE(TAG, "Could not add device at 0x69");
			return ret;
		}
	}
	ESP_LOGI(TAG, "Chip ID read: 0x%02X (expected 0x%02X)", chipId, BMI160_CHIP_ID);

	if (chipId != BMI160_CHIP_ID) {
		ESP_LOGE(TAG, "Unexpected BMI160 chip ID: 0x%02X", chipId);
		return ESP_ERR_NOT_FOUND;
	}

	ret = configureSensor();
	if (ret != ESP_OK) {
		ESP_LOGE(TAG, "Failed to configure BMI160: %s", esp_err_to_name(ret));
		return ret;
	}

	initialized = true;
	ESP_LOGI(TAG, "BMI160 initialized on I2C port %d (SDA=%d, SCL=%d)",
			 static_cast<int>(config.i2c_port),
			 static_cast<int>(config.sda_pin),
			 static_cast<int>(config.scl_pin));

	IMU::start();
	return ESP_OK;
}

void IMU::start() {
	if (!initialized || running) {
		return;
	}

	running = true;
	xTaskCreate(taskEntry, "IMUTask", 4096, this, 5, &taskHandle);
}

void IMU::stop() {
	running = false;
	if (taskHandle) {
		vTaskDelete(taskHandle);
		taskHandle = nullptr;
	}
}

esp_err_t IMU::readRegister(uint8_t reg, uint8_t* data, size_t len) {
	if (!devHandle || !data || len == 0) {
		return ESP_ERR_INVALID_ARG;
	}

	return i2c_master_transmit_receive(devHandle, &reg, 1, data, len, -1);
}

esp_err_t IMU::writeRegister(uint8_t reg, uint8_t value) {
	if (!devHandle) {
		return ESP_ERR_INVALID_STATE;
	}

	uint8_t tx[2] = {reg, value};
	return i2c_master_transmit(devHandle, tx, sizeof(tx), -1);
}

esp_err_t IMU::configureSensor() {
	esp_err_t ret = writeRegister(BMI160_REG_CMD, BMI160_CMD_SOFT_RESET);
	if (ret != ESP_OK) {
		return ret;
	}
	vTaskDelay(pdMS_TO_TICKS(100));

	ret = writeRegister(BMI160_REG_CMD, BMI160_CMD_ACC_NORMAL);
	if (ret != ESP_OK) {
		return ret;
	}
	vTaskDelay(pdMS_TO_TICKS(10));

	ret = writeRegister(BMI160_REG_CMD, BMI160_CMD_GYR_NORMAL);
	if (ret != ESP_OK) {
		return ret;
	}
	vTaskDelay(pdMS_TO_TICKS(80));

	// ODR 100 Hz, normal bandwidth, no downsampling
	ret = writeRegister(BMI160_REG_ACC_CONF, 0x28);
	if (ret != ESP_OK) {
		return ret;
	}

	// Accelerometer range: +/-2g
	ret = writeRegister(BMI160_REG_ACC_RANGE, 0x03);
	if (ret != ESP_OK) {
		return ret;
	}

	// ODR 100 Hz, normal mode for gyro
	ret = writeRegister(BMI160_REG_GYR_CONF, 0x28);
	if (ret != ESP_OK) {
		return ret;
	}

	// Gyroscope range: +/-250 dps
	ret = writeRegister(BMI160_REG_GYR_RANGE, 0x03);
	if (ret != ESP_OK) {
		return ret;
	}

	return ESP_OK;
}

esp_err_t IMU::readSample() {
	uint8_t accBuf[6] = {};
	uint8_t gyrBuf[6] = {};

	esp_err_t ret = readRegister(BMI160_REG_ACC_DATA, accBuf, sizeof(accBuf));
	if (ret != ESP_OK) {
		return ret;
	}

	ret = readRegister(BMI160_REG_GYR_DATA, gyrBuf, sizeof(gyrBuf));
	if (ret != ESP_OK) {
		return ret;
	}

	const int16_t ax = static_cast<int16_t>((accBuf[1] << 8) | accBuf[0]);
	const int16_t ay = static_cast<int16_t>((accBuf[3] << 8) | accBuf[2]);
	const int16_t az = static_cast<int16_t>((accBuf[5] << 8) | accBuf[4]);

	const int16_t gx = static_cast<int16_t>((gyrBuf[1] << 8) | gyrBuf[0]);
	const int16_t gy = static_cast<int16_t>((gyrBuf[3] << 8) | gyrBuf[2]);
	const int16_t gz = static_cast<int16_t>((gyrBuf[5] << 8) | gyrBuf[4]);

	// For +/-2g: 16384 LSB/g. For +/-250 dps: 32768 / 250 LSB/dps.
	latestData.accel_x_g = static_cast<float>(ax) / 16384.0f;
	latestData.accel_y_g = static_cast<float>(ay) / 16384.0f;
	latestData.accel_z_g = static_cast<float>(az) / 16384.0f;

	latestData.gyro_x_dps = static_cast<float>(gx) * 250.0f / 32768.0f;
	latestData.gyro_y_dps = static_cast<float>(gy) * 250.0f / 32768.0f;
	latestData.gyro_z_dps = static_cast<float>(gz) * 250.0f / 32768.0f;

	latestData.tick_ms = static_cast<uint32_t>(xTaskGetTickCount() * portTICK_PERIOD_MS);
	latestData.valid = true;
	return ESP_OK;
}

void IMU::taskEntry(void* arg) {
	IMU* imu = static_cast<IMU*>(arg);
	imu->taskLoop();
}

void IMU::taskLoop() {
	while (running) {
		esp_err_t ret = readSample();
		if (ret != ESP_OK) {
			ESP_LOGW(TAG, "BMI160 read failed: %s", esp_err_to_name(ret));
		}

		vTaskDelay(pdMS_TO_TICKS(config.sample_period_ms));
	}

	taskHandle = nullptr;
	vTaskDelete(nullptr);
}

void IMU::displayData() const {
    if (!latestData.valid) {
        return;
    }

    ESP_LOGI(TAG, "Accel (g): X=%.2f Y=%.2f Z=%.2f | Gyro (dps): X=%.2f Y=%.2f Z=%.2f | Tick: %u ms",
             latestData.accel_x_g, latestData.accel_y_g, latestData.accel_z_g,
             latestData.gyro_x_dps, latestData.gyro_y_dps, latestData.gyro_z_dps,
             latestData.tick_ms);
}