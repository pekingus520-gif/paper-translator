import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
const environmentValues = {};
let listener, removed, config = {url:'http://127.0.0.1:12345', token:'secret-token', generation:'one', enabled:true, mode:'paper'};
const calls=[], timers=new Map(); let timerID=0;
const scope = {
    Zotero: {isWin:false, File:{getContentsAsync:async()=>JSON.stringify(config)},
        Reader:{registerEventListener:(type,handler,id)=>{assert.equal(type,'renderTextSelectionPopup');listener=handler;},
            unregisterEventListener:(type,handler)=>{removed=handler;}},
        HTTP:{request:async(method,url,options)=>{calls.push({method,url,options});return {status:202};}},
        logError:()=>{}},
    // Actual Zotero bootstrap exposes Components/PathUtils, not Services.env or global Ci.
    Components:{classes:{'@mozilla.org/process/environment;1':{getService:()=>({get:name=>environmentValues[name]||''})}},interfaces:{nsIEnvironment:{},nsIFile:{}}},
    PathUtils:{homeDir:'/home/test',join:(...parts)=>scope.Zotero.isWin?path.win32.join(...parts):path.posix.join(...parts)},
    Services:{dirsvc:{get:()=>({path:'/home/test'})}},
    setTimeout:(fn)=>{const id=++timerID;timers.set(id,fn);return id;},clearTimeout:(id)=>timers.delete(id),console,
};
vm.createContext(scope);
vm.runInContext(fs.readFileSync(new URL('../zotero-plugin/bootstrap.js',import.meta.url),'utf8'),scope);
assert.equal(scope.configPath(),'/home/test/.config/paper-translator/zotero.json');
environmentValues.XDG_CONFIG_HOME='/custom/config';
assert.equal(scope.configPath(),'/custom/config/paper-translator/zotero.json');
delete environmentValues.XDG_CONFIG_HOME;
environmentValues.SNAP_USER_COMMON='/home/test/snap/zotero/common';
assert.equal(scope.configPath(),'/home/test/snap/zotero/common/paper-translator/zotero.json');
delete environmentValues.SNAP_USER_COMMON;
scope.Zotero.isWin=true;environmentValues.APPDATA='C:\\Users\\test\\AppData\\Roaming';
assert.equal(scope.configPath(),'C:\\Users\\test\\AppData\\Roaming\\PaperTranslator\\zotero.json');
scope.Zotero.isWin=false;
const readContents = scope.Zotero.File.getContentsAsync;
scope.Zotero.File.getContentsAsync = async()=>{throw new Error('host read failed');};
await assert.rejects(scope.readConfig(), /未找到或无法读取连接文件.*\/home\/test\/\.config\/paper-translator\/zotero\.json/);
scope.Zotero.File.getContentsAsync = async()=>'{private-token';
await assert.rejects(scope.readConfig(), /连接文件格式错误/);
scope.Zotero.File.getContentsAsync = async()=>'null';
await assert.rejects(scope.readConfig(), /连接信息无效/);
scope.Zotero.File.getContentsAsync = readContents;
await scope.startup({id:'paper-translator@local'});
const event = text => ({reader:{itemID:1},params:{annotation:{text}},doc:{createElement:()=>({isConnected:true,textContent:''})},append:()=>{}});
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
const settle=async()=>{await flush();const pending=[...timers.values()];timers.clear();for(const fn of pending)await fn();await flush();};
listener(event('old')); listener(event('new'));await settle();
assert.equal(calls.length,1);assert.equal(JSON.parse(calls[0].options.body).text,'new');
assert.equal(calls[0].options.headers.Authorization,'Bearer secret-token');
listener(event('new'));await settle();assert.equal(calls.length,1);
listener(event('before pause'));await flush();config={...config,generation:'two',enabled:false};await settle();assert.equal(calls.length,1);
config={...config,generation:'three',enabled:true};listener(event('resumed'));await settle();assert.equal(calls.length,2);
const otherPage = event('resumed');
otherPage.params.annotation.position = {pageIndex:1,rects:[[1,2,3,4]]};
listener(otherPage);await settle();assert.equal(calls.length,3);
listener(event('disconnect'));await flush();scope.shutdown();await settle();assert.equal(calls.length,3);assert.equal(removed,listener);
// Context extraction never sends an unrelated page; selection is centered and bounded.
assert.equal(scope.contextAround('unrelated text','selected'), '');
const context=scope.contextAround('a'.repeat(5000)+' selected '+'b'.repeat(5000),'selected');
assert(context.includes('selected') && context.length<=4000);
console.log('Zotero plugin debounce, pause, lifecycle, context tests passed');
