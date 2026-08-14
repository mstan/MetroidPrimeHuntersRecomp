cmake_minimum_required(VERSION 3.24)
project(mph_recomp_ui_launcher C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(SDL2 CONFIG REQUIRED)

add_executable(mph-recomp-ui launcher_main.cpp)
target_link_libraries(mph-recomp-ui PRIVATE SDL2::SDL2)

set(RECOMP_UI_ROOT "F:/Projects/recomp-ui" CACHE PATH
    "Path to the shared recomp-ui checkout")

enable_testing()
add_executable(mph-mod-provider-test tests/launcher_mod_provider_test.cpp)
target_include_directories(mph-mod-provider-test PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}"
    "${RECOMP_UI_ROOT}/src"
    "${RECOMP_UI_ROOT}/src/common")
target_compile_definitions(mph-mod-provider-test PRIVATE
    MPH_RECOMP_UI_NO_MAIN)

set(RECOMP_UI_SDL3 OFF)
set(RECOMP_UI_ENABLE_MODS ON CACHE BOOL "" FORCE)
include("${RECOMP_UI_ROOT}/recomp_ui.cmake")
recomp_target_launcher_ui(mph-recomp-ui CONSOLE nds)

add_test(NAME mph_mod_provider_test COMMAND mph-mod-provider-test)
