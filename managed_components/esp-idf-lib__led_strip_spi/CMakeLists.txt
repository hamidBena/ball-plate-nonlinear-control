set(REQUIRED_COMPONENTS log color esp_idf_lib_helpers)

# Flag indicating availability of ESP driver components (esp_driver_*)
# Note: Disabled for ESP-IDF v5.x where minor version < 3 due to API changes
set(HAS_ESP_DRIVERS TRUE)
if(${IDF_VERSION_MAJOR} STREQUAL 5 AND ${IDF_VERSION_MINOR} LESS 3)
    set(HAS_ESP_DRIVERS FALSE)
endif()

if(HAS_ESP_DRIVERS)
    list(APPEND REQUIRED_COMPONENTS esp_driver_spi esp_driver_gpio)
else()
    list(APPEND REQUIRED_COMPONENTS driver)
endif()

if(${IDF_TARGET} STREQUAL esp8266)
    set(req esp8266 log color esp_idf_lib_helpers)
endif()

idf_component_register(
    SRCS led_strip_spi.c led_strip_spi_sk9822.c
    INCLUDE_DIRS .
    REQUIRES ${REQUIRED_COMPONENTS}
)
target_compile_options(${COMPONENT_LIB} PRIVATE -Werror=override-init)

# include common cmake file for components
set(ESP_IDF_LIB_CMAKE ${CMAKE_CURRENT_LIST_DIR}/common/cmake/esp-idf-lib.cmake)
if(EXISTS ${ESP_IDF_LIB_CMAKE})
    include(${ESP_IDF_LIB_CMAKE})
else()
    message(WARNING "${ESP_IDF_LIB_CMAKE} not found")
endif()
