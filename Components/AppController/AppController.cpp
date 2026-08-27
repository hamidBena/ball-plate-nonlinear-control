#include "AppController.h"
#include "PinConfig.h"
#include "rgbController.h"
#include "touchPanel.h"
#include "CommHandler.h"
#include "IMU.h"
#include "MyServo.h"
#include "esp_log.h"
#include <cmath>
#define RAD_TO_DEG 57.2957795131f
#define DEG_TO_RAD 0.01745329251f

static const char* TAG = "AppController";

AppController::~AppController() {
    stop();
}

esp_err_t AppController::init(const Config& cfg) {
    ESP_LOGI(TAG, "Initializing AppController");

    // module instances
    rgb1 = new RGBController();
    touchPanel = new TouchPanel();
    commHandler = new CommHandler();
    servo1 = new MyServo();
    servo2 = new MyServo();
    imu = new IMU();

    if (!rgb1 || !touchPanel || !commHandler || !servo1 || !servo2 || !imu) {
        ESP_LOGE(TAG, "Failed to allocate module memory");
        return ESP_ERR_NO_MEM;
    }

    // Initialize RGB Controller
    esp_err_t ret = rgb1->init(RGBController::defaultConfig);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize RGB controller: %s", esp_err_to_name(ret));
        return ret;
    }
    rgb1->start();
    //rgb1->Cycle = true;
    rgb1->setBrightness(255);

    // Initialize TouchPanel (disabled - GPIO5/GPIO6 conflict with IMU I2C)         // TODO: rewire the touch panel to use new pins and re-enable
     ret = touchPanel->init({
         TOUCH_PANEL_X_PLUS, TOUCH_PANEL_X_MINUS, TOUCH_PANEL_X_ADC,  // x axis
         TOUCH_PANEL_Y_PLUS, TOUCH_PANEL_Y_MINUS, TOUCH_PANEL_Y_ADC,  // y axis
         TOUCH_PANEL_THRESHOLD
     });
     if (ret != ESP_OK) {
         ESP_LOGE(TAG, "Failed to initialize touchPanel: %s", esp_err_to_name(ret));
         return ret;
     }
    touchPanel->start();


    // Initialize Servo 1
    ret = servo1->init({
        .pin = SERVO1_PIN,
        .angleOffset = 90.0f - 7.0f
    });
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize servo1: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = servo2->init({
        .pin = SERVO2_PIN,
        .angleOffset = 90.0f + 4.0f
    });
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize servo2: %s", esp_err_to_name(ret));
        return ret;
    }

    // Initialize CommHandler   // TODO: enable when finished - causes crash "usb_serial_jtag_read_bytes"
    /*ret = commHandler->init({});
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize commHandler: %s", esp_err_to_name(ret));
        return ret;
    }*/

    // Initialize IMU (BMI160 over I2C)
    //ret = imu->init({
    //    .sda_pin = IMU_I2C_SDA,
    //    .scl_pin = IMU_I2C_SCL,
    //});
    //if (ret != ESP_OK) {
    //    ESP_LOGE(TAG, "Failed to initialize IMU: %s", esp_err_to_name(ret));
    //    return ret;
    //}

    ESP_LOGI(TAG, "AppController initialized");
    return ESP_OK;
}

void AppController::start() {
    if (running) {
        return;
    }

    running = true;
    
    // Start CommHandler before main loop (disabled - crashes in usb_serial_jtag_read_bytes)
    // if (commHandler) {
    //     commHandler->start();
    // }
    
    xTaskCreate(mainLoopEntry, "AppControllerTask", 4096, this, 4, &mainTaskHandle);
    ESP_LOGI(TAG, "AppController started");
}
 
void AppController::stop() {
    running = false;

    if (mainTaskHandle != nullptr) {
        vTaskDelete(mainTaskHandle);
        mainTaskHandle = nullptr;
    }

    // Stop modules
    // if (commHandler) commHandler->stop();  // Disabled
    if (touchPanel) touchPanel->stop();
    if (rgb1) rgb1->stop();


    // Clean up queues
    if (touchPanelQueue) vQueueDelete(touchPanelQueue);
    if (servo1Queue) vQueueDelete(servo1Queue);
    if (servo2Queue) vQueueDelete(servo2Queue);
    if (ledQueue) vQueueDelete(ledQueue);

    // Clean up module memory
    delete rgb1;
    delete touchPanel;
    delete commHandler;
    delete servo1;
    delete servo2;
    delete imu;
    ESP_LOGI(TAG, "AppController stopped");
}

void AppController::mainLoopEntry(void* arg) {
    auto* controller = static_cast<AppController*>(arg);
    controller->mainLoop();
}

struct PID {
    float Kp, Ki, Kd;
    float setpoint;
    float lastSetPoint;
    float integral = 0;
    float last_error = 0;
    float derivative = 0;
    
    //outputs
    float output = 0;
    float outP = 0;
    float outI = 0;
    float outD = 0;
    
    float maxOutput = 35.0f;
    float maxDerivative = 30.0f;    
    float maxProportional = 25.0f;
    float maxIntegral = 4.0f;
    
    float alphaD = 1.0f;
    float alphaPID = 0.7f;
    
    PID(float p, float i, float d) : Kp(p), Ki(i), Kd(d), setpoint(0) {}
    
    float update(float measurement, float dt) {
        if (dt <= 0.0f) return output; // guard against div-by-zero / nan poisoning
        
        float error = setpoint - measurement;
        
        // Handle setpoint change BEFORE computing P/I/D for this cycle
        if (setpoint != lastSetPoint) {
            integral = 0;
            derivative = 0;
            last_error = error;       // avoid kick on *next* cycle too
            lastSetPoint = setpoint;
            output = 0;               // optional: also reset output on setpoint change
        }
        
        // I
        integral += error * dt;
        integral = std::max(-maxIntegral, std::min(maxIntegral, integral));
        
        // D
        float oldDerivative = derivative;
        derivative = (error - last_error) / dt;
        derivative = alphaD * derivative + (1 - alphaD) * oldDerivative;
        
        // Output
        float oldOutput = output;
        outP = std::max(-maxProportional, std::min(maxProportional, Kp * error));
        outI = std::max(-maxIntegral, std::min(maxIntegral, Ki * integral));
        outD = std::max(-maxDerivative, std::min(maxDerivative, Kd * derivative));
        output = outP + outI + outD;
        
        output = std::max(-maxOutput, std::min(maxOutput, output));
        output = alphaPID * output + (1 - alphaPID) * oldOutput;
        output = std::max(-maxOutput, std::min(maxOutput, output)); // re-clamp after filter
        
        last_error = error;
        return output;
    }
};

class SMC {
public:
    float lambda;
    float K;
    float phi;
    float phiI;
    float integral = 0.0f;
    float maxIntegral = 400.0f; // Limit for integral term to prevent windup
    bool lastErrorSign = 0; // Track the sign of the last error for integral reset

    SMC(float lambda, float K, float phi, float phiI = 0.0f)
        : lambda(lambda), K(K), phi(phi), phiI(phiI) {}

    float compute(float position, float velocity, float target, float targetVelocity = 0) {
        float e     = target - position;
        float e_dot = targetVelocity - velocity;

        if( abs(e) < 50.f ){
            integral += e;
            integral = std::max(-maxIntegral, std::min(maxIntegral, integral));
        }

        if((e > 0) ^ lastErrorSign) { // If the sign of the error has changed
            integral = 0; // Reset integral if error sign changes
        }
        
        float s = e_dot + lambda * e + phiI * integral;
        lastErrorSign = (e > 0);
        return K * tanhf(s / phi);
    }
};


void AppController::mainLoop() {
    ESP_LOGI(TAG, "Main loop started");
    float x = 0.0f, y = 0.0f;

    PID pidX(0.2, 0.0, 0.075);
    PID pidY(0.2, 0.0, 0.075);
    SMC smcX(3.5f, 30.0f, 200.f, 0.0f);
    SMC smcY(3.5f, 30.0f, 240.f, 0.0f);

    pidX.setpoint = 0;
    pidY.setpoint = 0;

    float frequency = 1000 / 250.f;  // 50 hz
    float dt = frequency / 1000.f;
    float time = 0.f;

    int targetCount = 3;
    float Xpoints[3] = {0.f, 80.f, -80.f};
    float Ypoints[3] = {70.f, -50.f, -50.f};

    float XVels[targetCount] = {0.f, 0.f, 0.f};
    float YVels[targetCount] = {0.f, 0.f, 0.f};
    int Xindex = 0;
    int Yindex = 0;

    float angle = 0.f;
    float radius = 70.f;
    float speed = 0.f; // degrees per second

    float tx = 0.f;
    float ty = 0.f;
    float tvx = 0.f;
    float tvy = 0.f;
    bool wasOnTarget = false;
    bool isOnTarget = false;
    float timeEnteredTarget = 0.f;

    float controlS1 = 0.f;
    float controlS2 = 0.f;

    servo1->invert = false;

    while (true) {
        if(!running){
            touchPanel->running = false;
            vTaskDelay(pdMS_TO_TICKS(200));
            continue;
        }else{
            touchPanel->running = true;
        }
        x = touchPanel->xFiltered;
        y = touchPanel->yFiltered;

        wasOnTarget = isOnTarget;
        isOnTarget = std::hypot(tx - x, ty - y) < 20.f;
        if (isOnTarget && !wasOnTarget) { // ball just arrived at target
            timeEnteredTarget = time;
        }
        if(isOnTarget) rgb1->setColor(0, 255, 0); // Green when on target
        else rgb1->setColor(0, 0, 0); // Red when not on target

        float radAngle   = angle * DEG_TO_RAD;
        float angularVel = speed * DEG_TO_RAD;
        float velocityDamping = 0.7f;
        switch(trajectory) {
            case Trajectory::Circle:
                smcX.phi = 250.f;
                smcY.phi = 250.f;
                speed = 200.f;
                tx = radius * std::cos(radAngle);
                ty = radius * std::sin(radAngle);
                tvx = -radius * angularVel * std::sin(radAngle) * velocityDamping;
                tvy =  radius * angularVel * std::cos(radAngle) * velocityDamping;
                break;
            case Trajectory::Points:
                smcX.phi = 340.f;
                smcY.phi = 340.f;
                wasOnTarget = isOnTarget;
                
                if (isOnTarget && (time - timeEnteredTarget) > 0.2f) { // ball has been at target for 0.5 seconds
                    Xindex = (Xindex + 1) % targetCount;
                    Yindex = (Yindex + 1) % targetCount;
                    tx = Xpoints[Xindex];
                    ty = Ypoints[Yindex];
                    tvx = XVels[Xindex];
                    tvy = YVels[Yindex];
                }
                break;
            case Trajectory::Figure8:
                smcX.phi = 250.f;
                smcY.phi = 250.f;
                speed = 165.f;

                tx = 85 * std::sin(radAngle);
                ty = 40 * std::sin(2.f * radAngle);

                tvx = 85 * angularVel * std::cos(radAngle) * velocityDamping;
                tvy = 2 * 40 * angularVel * std::cos(2.f * radAngle) * velocityDamping;
                
                break;
            case Trajectory::Center:
                smcX.phi = 340.f;
                smcY.phi = 340.f;
                tx = 0;
                ty = 0;
                tvx = 0;
                tvy = 0;
                break;
        }

        switch(controlMode) {
            case ControlMode::PID:
                pidX.setpoint = tx;
                pidY.setpoint = ty;
                pidX.update(x, dt);
                pidY.update(y, dt);
                controlS1 = pidY.output;
                controlS2 = pidX.output;
                break;
            case ControlMode::SMC:
                controlS1 = smcY.compute(y, touchPanel->yVelocity, ty, tvy);
                controlS2 = smcX.compute(x, touchPanel->xVelocity, tx, tvx);
                break;
        }

        if(touchPanel->isTouched()){
            servo2->setAngle(controlS2);
            servo1->setAngle(controlS1);
        }

        //printf("Setpoints: (%.2f, %.2f) | Measurements: (%.2f, %.2f) | ControlX: %.2f | ControlY: %.2f\n", tx, ty, x, y, controlS2, controlS1);
        if(fmod(time, printingFrequency) <= dt){
            char buf[512];  // adjust size if needed
            int pos = 0;
            
            pos += sprintf(buf + pos, "{\"target\":[%.2f,%.2f],\"ball\":[%.2f,%.2f],\"ballVel\":[%.2f,%.2f],\"controls\":[%.2f,%.2f],\"xReadings\":[",
                tx, ty, x, y, touchPanel->xVelocity, touchPanel->yVelocity, controlS2, controlS1);

            for (int i = 0; i < touchPanel->samples; i++) {
                pos += sprintf(buf + pos, i < touchPanel->samples - 1 ? "%.3f," : "%.3f", touchPanel->xReadings[i]);
            }

            pos += sprintf(buf + pos, "],\"yReadings\":[");

            for (int i = 0; i < touchPanel->samples; i++) {
                pos += sprintf(buf + pos, i < touchPanel->samples - 1 ? "%.3f," : "%.3f", touchPanel->yReadings[i]);
            }

            pos += sprintf(buf + pos, "]}\n");
            
            printf("%s", buf);  // single print = single line = clean JSON
        }

        if(dirtyTunes) {
            pidX.Kp = kpx; pidY.Kp = kpy;
            pidX.Ki = kix; pidY.Ki = kiy;
            pidX.Kd = kdx; pidY.Kd = kdy;

            smcX.phi = phix;         smcY.phi = phiy;
            smcX.K = kx;             smcY.K = ky;
            smcX.lambda = lambdax;   smcY.lambda = lambday;

            dirtyTunes = false;
        }
        
        angle = std::fmod(time * speed, 360.f);
        
        time += frequency/1000.f;
        vTaskDelay(pdMS_TO_TICKS(frequency)); // 50 Hz update rate
    }

    ESP_LOGI(TAG, "Main loop stopped");
}

void AppController::handleCommand(const char* command) {
    char buf[32];
    int i = 0;

    while (*command && *command != ' ' && i < (int)sizeof(buf) - 1) {
        buf[i++] = *command++;
    }

    buf[i] = '\0';

    // skip ALL spaces (IMPORTANT)
    while (*command == ' ') command++;

    if (strcmp(buf, "mode") == 0) {

        if (strcmp(command, "pid") == 0) {
            controlMode = ControlMode::PID;
            rgb1->setColor(0, 255, 0);
        }
        else if (strcmp(command, "smc") == 0) {
            controlMode = ControlMode::SMC;
            rgb1->setColor(0, 255, 0);
        }
        else if (strncmp(command, "tune", 4) == 0) {
            command += 4;
            while (*command == ' ') command++;

            char key[16] = {0};
            char val[16] = {0};

            int i = 0;

            // read key
            while (*command && *command != ' ' && i < 15) {
                key[i++] = *command++;
            }
            key[i] = '\0';

            while (*command == ' ') command++;

            i = 0;

            // read value
            while (*command && *command != ' ' && i < 15) {
                val[i++] = *command++;
            }
            val[i] = '\0';

            float v = atof(val);

            while (*command == ' ') command++;

            if (strcmp(key, "kpx") == 0) kpx = v;
            else if (strcmp(key, "kix") == 0) kix = v;
            else if (strcmp(key, "kdx") == 0) kdx = v;
            else if (strcmp(key, "phix") == 0) phix = v;
            else if (strcmp(key, "kx") == 0) kx = v;
            else if (strcmp(key, "lambdax") == 0) lambdax = v;
            else if (strcmp(key, "kpy") == 0) kpy = v;
            else if (strcmp(key, "kiy") == 0) kiy = v;
            else if (strcmp(key, "kdy") == 0) kdy = v;
            else if (strcmp(key, "phiy") == 0) phiy = v;
            else if (strcmp(key, "ky") == 0) ky = v;
            else if (strcmp(key, "lambday") == 0) lambday = v;
            else {
                ESP_LOGW(TAG, "Unknown PID param: %s", key);
            }
            dirtyTunes = true;

            printf(TAG, "Tuned %s = %.3f", key, v);
        }
    } else if (strcmp(buf, "trajectory") == 0) {
        if (strcmp(command, "points") == 0) {
            trajectory = Trajectory::Points;
        }
        else if (strcmp(command, "circle") == 0) {
            trajectory = Trajectory::Circle;
        }
        else if (strcmp(command, "figure8") == 0) {
            trajectory = Trajectory::Figure8;
        }
        else if (strcmp(command, "center") == 0) {
            trajectory = Trajectory::Center;
        }
        else {
            ESP_LOGW(TAG, "Unknown trajectory: %s", command);
        }
    } else if(strcmp(buf, "servo1") == 0) {
        servo1->handleCommand(command);
    } else if(strcmp(buf, "servo2") == 0) {
        servo2->handleCommand(command);
    } else if(strcmp(buf, "rgb") == 0) {
        rgb1->handleCommand(command);
    } else {
        ESP_LOGW(TAG, "Unknown command: %s", buf);
    }
}