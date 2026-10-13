/* Zotero 7–9 bootstrapped plugin. No translation credentials or remote API calls. */
let pluginID, active = false, sequence = 0, timer = null, lastSent = '', lastSentAt = 0, handler;
let copyDocument = null, copyHandler = null;

function stopCopyWatch() {
    if (copyDocument && copyHandler)
        copyDocument.removeEventListener?.('copy', copyHandler, true);
    copyDocument = copyHandler = null;
}

function configPath() {
    const {classes, interfaces} = Components;
    const environment = classes['@mozilla.org/process/environment;1'].getService(interfaces.nsIEnvironment);
    const snapCommon = environment.get('SNAP_USER_COMMON');
    if (!Zotero.isWin && snapCommon)
        return PathUtils.join(snapCommon, 'paper-translator', 'zotero.json');
    const base = Zotero.isWin
        ? (environment.get('APPDATA') || Services.dirsvc.get('AppData', interfaces.nsIFile).path)
        : (environment.get('XDG_CONFIG_HOME') || PathUtils.join(PathUtils.homeDir, '.config'));
    return PathUtils.join(base, Zotero.isWin ? 'PaperTranslator' : 'paper-translator', 'zotero.json');
}

async function readConfig() {
    let path;
    try { path = configPath(); }
    catch (_error) { throw new Error('无法确定系统配置目录，请查看插件兼容性'); }
    let raw;
    try { raw = await Zotero.File.getContentsAsync(path); }
    catch (_error) {
        throw new Error('未找到或无法读取连接文件，请退出并重新启动新版桌面翻译器。路径：' + path);
    }
    let config;
    try { config = JSON.parse(raw); }
    catch (_error) { throw new Error('连接文件格式错误，请重新启动桌面翻译器'); }
    if (!config || typeof config !== 'object' || !/^http:\/\/127\.0\.0\.1:[0-9]{1,5}$/.test(config.url) ||
        typeof config.token !== 'string' || config.token.length > 128 || !config.token ||
        typeof config.generation !== 'string' || !config.generation)
        throw new Error('连接信息无效，请重新启动桌面翻译器');
    return config;
}

function normalize(text) { return text.replace(/\s+/g, ' ').trim(); }

function contextAround(page, selected) {
    page = normalize(page); selected = normalize(selected);
    const index = page.indexOf(selected);
    if (!selected || index < 0) return '';
    return page.slice(Math.max(0, index - 900), index + selected.length + 900).slice(0, 4000);
}

async function nearbyContext(event, text) {
    try {
        const selection = event.doc.getSelection?.();
        const parent = selection?.anchorNode?.parentElement;
        if (parent?.textContent) {
            const context = contextAround(parent.textContent, text);
            if (context.length > text.length + 10) return context;
        }
        // PDF.js access is optional: unavailable internals leave context empty.
        // Only request the selected page, never the full document.
        const reader = event.reader._internalReader;
        const primary = reader?._lastViewPrimary !== false;
        const view = primary ? reader?._primaryView : reader?._secondaryView;
        const win = view?._iframeWindow?.wrappedJSObject || view?._iframeWindow;
        const pdf = win?.PDFViewerApplication?.pdfDocument;
        const index = event.params.annotation.position?.pageIndex;
        if (!pdf || !Number.isInteger(index) || index < 0) return '';
        const page = await pdf.getPage(index + 1);
        const content = await page.getTextContent();
        return contextAround(content.items.map(item => item.str || '').join(' '), text);
    } catch (_error) { return ''; }
}

function selectionChanged(event) {
    const text = event.params?.annotation?.text?.trim();
    if (!active || !text || text.length > 10000) return;
    const ticket = ++sequence;
    if (timer !== null) { clearTimeout(timer); timer = null; }
    stopCopyWatch();
    const status = event.doc.createElement('div');
    status.textContent = 'Paper Translator：等待选区稳定…';
    event.append(status);
    copyDocument = event.doc;
    copyHandler = () => {
        if (!active || ticket !== sequence) return;
        sequence++;
        if (timer !== null) { clearTimeout(timer); timer = null; }
        status.textContent = 'Paper Translator：已复制，取消自动翻译';
        stopCopyWatch();
    };
    copyDocument.addEventListener?.('copy', copyHandler, true);
    (async () => {
        let config;
        try { config = await readConfig(); }
        catch (error) {
            status.textContent = 'Paper Translator：' + error.message;
            stopCopyWatch(); return;
        }
        if (!active || ticket !== sequence) return;
        if (!config.enabled) { status.textContent = 'Paper Translator：已暂停'; stopCopyWatch(); return; }
        const position = JSON.stringify(event.params.annotation.position || {});
        const key = `${config.generation}:${event.reader.itemID}:${position}:${text}`;
        if (key === lastSent && Date.now() - lastSentAt < 1500) {
            status.textContent = 'Paper Translator：该选区已发送'; stopCopyWatch(); return;
        }
        timer = setTimeout(async () => {
            timer = null;
            stopCopyWatch();
            if (!active || ticket !== sequence || !status.isConnected) return;
            try {
                const context = config.mode === 'paper' ? await nearbyContext(event, text) : '';
                const current = await readConfig();
                if (!active || ticket !== sequence || !status.isConnected || !current.enabled ||
                    current.generation !== config.generation) {
                    status.textContent = 'Paper Translator：选区已取消或翻译已暂停'; return;
                }
                await Zotero.HTTP.request('POST', config.url + '/selection', {
                    headers: {'Content-Type':'application/json', 'Authorization':'Bearer ' + config.token},
                    body:JSON.stringify({text, context, generation:config.generation}),
                    timeout:3000, logBodyLength:0,
                });
                if (active && ticket === sequence) {
                    lastSent = key;
                    lastSentAt = Date.now();
                    status.textContent = context ? 'Paper Translator：已发送选区及附近上下文' : 'Paper Translator：已发送选区';
                }
            } catch (_error) {
                status.textContent = 'Paper Translator：未连接，请确认翻译器正在运行且未暂停';
            }
        }, 1000);
    })();
}

async function startup(data) {
    pluginID = data.id; active = true; sequence++; lastSent = ''; lastSentAt = 0;
    handler = selectionChanged;
    Zotero.Reader.registerEventListener('renderTextSelectionPopup', handler, pluginID);
}

function shutdown() {
    active = false; sequence++; lastSent = ''; lastSentAt = 0;
    if (timer !== null) { clearTimeout(timer); timer = null; }
    stopCopyWatch();
    if (handler) Zotero.Reader.unregisterEventListener('renderTextSelectionPopup', handler);
    handler = null;
}
function install() {}
function uninstall() {}
