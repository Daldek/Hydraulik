# Shim: Ubuntu's libtiff-dev ships no CMake config package; wrap CMake's FindTIFF module (creates TIFF::TIFF).
find_package(TIFF MODULE REQUIRED)
