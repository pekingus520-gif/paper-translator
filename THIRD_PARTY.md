# 第三方组件

运行包使用动态链接 Qt / PySide6 Essentials 6.10.3（LGPLv3），Python、Pillow、keyring、python-xlib 及其依赖，以及 Tesseract 5.5.0 和英语/OSD OCR 数据。版权与许可证文本位于 third-party-notices/。

Qt 动态库位于运行包 _internal/，保持独立文件，可按相应许可证替换为兼容版本；替换后需自行验证二进制兼容性。Qt 与 PySide 源码：

- https://download.qt.io/archive/qt/6.10/6.10.3/
- https://code.qt.io/cgit/pyside/pyside-setup.git/?h=v6.10.3
- https://github.com/tesseract-ocr/tesseract/tree/5.5.0
- https://github.com/tesseract-ocr/tessdata

Linux 便携包仍使用宿主的桌面服务和系统库，不是跨所有 Linux 发行版的静态程序。Windows 请使用 Windows 打包脚本生成对应包。
