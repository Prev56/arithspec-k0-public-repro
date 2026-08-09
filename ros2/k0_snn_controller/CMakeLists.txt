cmake_minimum_required(VERSION 3.8)
project(k0_snn_controller)

# C++17 required for <cstdint> and structured bindings
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# --- ROS 2 dependencies ---
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

# --- K0 SNN node ---
add_executable(k0_snn_node src/k0_snn_node.cpp)
ament_target_dependencies(k0_snn_node rclcpp std_msgs)

install(TARGETS k0_snn_node
  DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
