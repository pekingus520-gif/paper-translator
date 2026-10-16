# Paper Translator

一个极度轻量、开源的日常及论文阅读用翻译器。

## 主要功能

1. **截图翻译**：自定义快捷键，在 GNOME 截图界面拖选文字区域并点击确认 → 本地 OCR → 翻译。可在设置里修改快捷键。
2. **实时划词翻译**：取消传统划词+快捷键划词翻译方式，直接划词即可实时翻译。为了避免在划词复制操作时引起不必要的麻烦，检测到鼠标拖动至少 8 像素，且松开后选区变成不同文字，再等待 1 秒才自动翻译。等待期间复制会取消这次翻译。

**总开关**：默认 `Ctrl+Alt+T`，同时暂停截图触发与自动划词，再按一次恢复。暂停会丢弃在途结果；已发出的网络请求可能完成，但新结果不会弹出。


**日常模式**：调用你配置的百度通用翻译 API,目前只提供百度翻译API。

**论文模式**：百度提供参考初译，AI 结合原句、研究领域及可用上下文，在内部判断术语含义并核对语义，最终只显示复核后的译文。AI 复核失败会报错，不展示未经复核的初译。无法保证模型绝对正确，关键表述仍需结合原文核对。日常模式只发送一次翻译请求，论文模式多一次 AI 精校请求，因此通常较慢。OCR 文本可在结果窗口修改后重新翻译。

## Zotero 9.0.1（兼容 Zotero 7–9 的选区接口）

随附 `PaperTranslator-Zotero-0.2.7.xpi` 是阅读器输入插件，绕开 Linux PRIMARY 选区限制；无需在插件中配置 API。

1. 从 Zotero 的“工具 → 插件”（部分版本叫附加组件）打开插件管理页。
2. 点击齿轮菜单 → “从文件安装插件”，选择随附 `.xpi` 文件；也可把文件拖入插件管理页。
3. 启动更新后的桌面翻译器，并保持运行。
4. Zotero 原有选区弹窗会显示“已发送选区”或连接/暂停提示；结果显示在桌面翻译器悬浮窗。总开关仍由桌面翻译器统一控制。

论文模式会尝试获取选区所在页面的附近文字（最多 4000 字符）用于术语消歧，只翻译选中内容。上下文提取依赖阅读器内部接口；接口不可用时仍能传递选区，模型应提示无法确定的含义。日常模式不提取上下文。上下文会随选区发送给你配置的 AI 服务，不会发送整篇论文。


## Ubuntu 26.04 / GNOME Wayland

先安装运行环境与本地 OCR：

```bash
sudo apt install python3-venv tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim libxcb-cursor0
```

在项目目录运行：

```bash
bash scripts/run-linux.sh
```

首次启动会创建项目专属 `.venv` 并下载依赖，不修改系统 Python。后续启动直接使用已有环境。如果使用随附的 Ubuntu 便携包，解压后运行其中的 `PaperTranslator`，无需 Python；包内已附英语与简体中文 OCR。

建议安装应用菜单入口，让桌面截图服务能识别软件身份：

```bash
bash scripts/install-desktop.sh
```

安装后从应用菜单启动 Paper Translator。安装入口前可能出现“App info not found”桌面注册提示。

**Wayland 全局划词与快捷键需要随附的 GNOME 输入辅助组件**：

```bash
bash scripts/install-gnome-bridge.sh
```

首次安装后 GNOME 若提示没有此扩展，请注销并重新登录，再运行：

```bash
gnome-extensions enable paper-translator-bridge@local
```

打开软件后程序必须保持运行。辅助组件只读取选区、绑定快捷键、定位结果窗；不保存 API 密钥、不调用翻译 API。关闭软件约 8 秒内自动停止取词与释放快捷键。支持 GNOME Shell 45–50，其他 Wayland 桌面当前不提供自动划词适配。

主窗口使用与壁纸融合的自绘顶栏：拖动顶部空白区域可移动窗口，双击可最大化或还原，右上角提供设置、最小化、最大化和关闭按钮；窗口四边可拖动调整大小。关闭按钮仍按托盘设置隐藏软件。

GNOME Wayland 的全局截图快捷键先冻结当前屏幕并打开“区域”模式。拖动框选需要翻译的文字，松开鼠标后自动截图、识别并翻译选定区域；只点击而不拖动不会触发翻译。截图文件无法读取时会尝试接收 GNOME 同时复制到剪贴板的图片。其他 Wayland 截图入口仍使用桌面门户授权界面。结果窗的置顶与定位由辅助组件协助；未安装时窗口位置由桌面决定。

## Windows

安装 64 位 Python 3.10+，双击 `scripts/run-windows.bat`，首次启动下载依赖。截图 OCR 还需安装 Tesseract；程序自动查找 PATH 和 `C:\Program Files\Tesseract-OCR\tesseract.exe`，也可在设置里填写完整路径。

通过 Windows UI Automation 读取选区，不模拟 Ctrl+C、不改写剪贴板。不支持 UI Automation TextPattern 的应用无法实时划词；用截图翻译代替。对不同权限级别的窗口，系统可能拒绝读取选区。

要生成 `.exe`，在 Windows 上运行 `scripts/build-windows.bat`，输出整个 `dist/PaperTranslator` 文件夹。必须在 Windows 上构建和实测，不能把 Linux 构建结果改名为 `.exe`。目前提供 Windows 适配实现与打包脚本，尚未在 Windows 真机验证。

## Linux X11

使用相同 Linux 启动脚本，不需要 GNOME 辅助组件。通过 PRIMARY 选区取词；截图由软件提供区域选择层。目前不跨显示器框选同一个区域。部分应用不提供 PRIMARY 文本，可改用截图。

## 配置 API

在主窗口点击“设置”：

- **百度 App ID / 百度密钥**：到 [百度翻译开放平台](https://fanyi-api.baidu.com/) 开通通用文本翻译后获取。默认接口地址已填写。
- **AI 地址**：支持 Chat Completions 协议的接口，例如服务商给出的 `https://…/v1`；也支持完整 `…/chat/completions` 地址。不要填写网站聊天页面地址。
- **AI 模型名称 / AI 密钥**：按自己的服务商填写。日常模式不需要 AI；论文模式需要百度与 AI 都配置。
- **中英自动互译**：默认开启，中文→英文、英文→中文；中英混合按汉字与英文词数量判断，相同数量优先中文。划词、截图 OCR 与重新翻译使用同一规则。
- **OCR 语言**：默认 `eng`。中文截图可用 `eng+chi_sim`，须安装对应语言包；便携包已附简体中文模型。

密钥优先存入系统密钥库（Linux Secret Service / Windows Credential Manager）。密钥库不可用时会提示，只在本次程序运行保留，不写明文密钥到设置文件。重新启动需再填密钥。Linux 设置目录：`~/.config/paper-translator`；Windows：`%APPDATA%\PaperTranslator`。不保存论文或翻译历史。

实时划词会发送所选文字给配置的翻译服务；论文模式还会发送给配置的 AI 服务。截图图片在本地 OCR，仅识别文字发送给翻译 API。请求去抖并保留最新排队任务，仍可能触及账号限流；使用总开关可随时暂停。

## 开发、验证与打包

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
node tests/test_bridge.mjs
node tests/test_zotero_plugin.mjs
glib-compile-schemas --strict gnome-bridge/schemas
bash scripts/build-linux.sh
```

使用 Qt Essentials 6.10.3，未引入浏览器组件。网络、OCR 在工作线程中运行，只有最新请求能更新窗口。修改视觉样式主要涉及 `src/paper_translator/ui.py`，平台适配与 API 可以保持独立。

源码结构：`providers.py`（百度与 AI）、`controller.py`（任务/暂停/结果）、`ocr.py`（本地识别）、`capture.py`（区域截图与 Wayland portal）、`config.py`（设置/密钥库）、`platforms/`（Windows/X11/Wayland）、`gnome-bridge/`（Ubuntu 输入辅助组件）。

验收情况和限制见 [验证记录](docs/verification.md)。没有你的真实 API 密钥，因此自动测试使用本地 HTTP 服务验证协议与错误处理；不等同于实际服务商联调或学术译文质量评测。
