#pragma once

#include <esp_err.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

// Forward declarations
class RGBController;
class TouchPanel;
class CommHandler;
class MyServo;
class IMU;

enum class ControlMode {
    PID,
    SMC
};

enum class Trajectory {
    Points,
    Circle,
    Center,
    Figure8,
};

struct PID;
struct SMC;

class AppController {
public:
    struct Config {};

    AppController() = default;
    ~AppController();

    esp_err_t init(const Config& cfg);
    void start();
    void stop();

    // Queue accessors (modules will use these to post events)
    QueueHandle_t getTouchPanelQueue() const { return touchPanelQueue; }
    QueueHandle_t getServo1Queue() const { return servo1Queue; }
    QueueHandle_t getServo2Queue() const { return servo2Queue; }
    QueueHandle_t getLedQueue() const { return ledQueue; }
    bool running = false;

    void handleCommand(const char* command);

private:
    void mainLoop();
    static void mainLoopEntry(void* arg);
    
    // Module pointers
    RGBController* rgb1 = nullptr;
    TouchPanel* touchPanel = nullptr;
    CommHandler* commHandler = nullptr;
    MyServo* servo1 = nullptr;
    MyServo* servo2 = nullptr;
    IMU* imu = nullptr;

    ControlMode controlMode = ControlMode::SMC;
    Trajectory trajectory = Trajectory::Center;

    // Queues
    QueueHandle_t touchPanelQueue = nullptr;
    QueueHandle_t servo1Queue = nullptr;
    QueueHandle_t servo2Queue = nullptr;
    QueueHandle_t ledQueue = nullptr;

    TaskHandle_t mainTaskHandle = nullptr;

    float printingFrequency = 1/50.f; // 50hz
    int menuID = 0;
    const int menuSize = 2;

    void updateMenu();

    float kpx, kix, kdx, phix, kx, lambdax;
    float kpy, kiy, kdy, phiy, ky, lambday;
    bool dirtyTunes = false;
};