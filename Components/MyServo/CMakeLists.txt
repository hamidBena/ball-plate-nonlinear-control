idf_component_register(
    SRCS
       MyServo.cpp
    INCLUDE_DIRS
        "include"
    REQUIRES
        esp_driver_ledc
        freertos
        esp_driver_gpio

)