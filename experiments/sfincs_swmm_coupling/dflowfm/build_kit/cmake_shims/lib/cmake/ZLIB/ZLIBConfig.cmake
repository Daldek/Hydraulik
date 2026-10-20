# Shim: Ubuntu's zlib1g-dev has no CMake config package; wrap CMake's FindZLIB module (creates ZLIB::ZLIB).
find_package(ZLIB MODULE REQUIRED)
