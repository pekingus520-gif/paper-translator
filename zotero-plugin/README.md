# Zotero 阅读器输入插件

目标 Zotero 9.0.1，采用 Zotero 7–9 官方 renderTextSelectionPopup 接口。安装、用途、上下文范围和限制见项目 README 的 Zotero 一节。插件不读取 API 密钥、不创建或修改论文标注、不访问远程翻译服务。

官方接口参考：https://www.zotero.org/support/dev/zotero_7_for_developers#custom_reader_event_handlers

bootstrap.js 为独立源文件，不需要 Node 依赖。通过 scripts/build-zotero.py 打包为 XPI。

0.2.2 修复：Zotero 9 安装器要求 update_url 使用 HTTPS。本地 file:// 更新清单不满足该要求，已撤销。默认使用保留的 .invalid 域名作为 HTTPS 占位符，明确不提供已部署的自动更新服务；请手动安装新版本。主动检查此插件更新时可能提示无法连接，这是当前分发方式的限制。部署真正的更新服务后，通过 build-zotero.py --update-url https://你的服务器/updates.json 重新构建。没有修改或放宽 Zotero 的安全检查。

0.2.3 修复：使用 Zotero bootstrap 提供的 Components 环境服务与 PathUtils 读取系统配置目录，撤销未提供的 Ci 和 Services.env 依赖。连接文件缺失或格式异常会分别显示具体提示，不再笼统显示“请先启动桌面翻译器”。安装后请完整退出并重新启动桌面翻译器，再拖选测试。

0.2.4：适配 Snap Zotero。桌面端在已有 ~/snap/zotero/common 下同步私有连接文件，暂停、更改配置及退出同步更新或删除。插件在 Snap 内优先读取 SNAP_USER_COMMON/paper-translator/zotero.json。必须同时更新桌面程序与插件，只有插件更新无法让旧桌面端生成该文件。尚需实际 Snap Zotero 联调。

0.2.5：兼容实际发行包名 `zotero-snap`。桌面端会检测已存在的 `~/snap/zotero/common` 与 `~/snap/zotero-snap/common`，只向检测到的 Zotero Snap 目录同步连接文件。
