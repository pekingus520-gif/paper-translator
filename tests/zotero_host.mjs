// Minimal Zotero host fixture, executing shipped bootstrap against a real HTTP bridge.
import fs from 'node:fs/promises';
import vm from 'node:vm';
let handler,resolve;
const sent=new Promise(r=>{resolve=r;});
const scope={
    Components:{classes:{'@mozilla.org/process/environment;1':{getService:()=>({get:()=>''})}},interfaces:{nsIEnvironment:{},nsIFile:{}}},
    PathUtils:{homeDir:'/unused',join:(...parts)=>parts.join('/')},
    Services:{dirsvc:{get:()=>({path:'/unused'})}},setTimeout,clearTimeout,
    Zotero:{isWin:false,File:{getContentsAsync:()=>fs.readFile(process.argv[2],'utf8')},
        Reader:{registerEventListener:(type,fn)=>{handler=fn;},unregisterEventListener:()=>{}},
        HTTP:{request:async(method,url,options)=>{
            const response=await fetch(url,{method,headers:options.headers,body:options.body});
            if(!response.ok)throw Error('Bridge HTTP '+response.status);
            resolve();return {status:response.status};
        }},logError:()=>{}},
};
vm.createContext(scope);
vm.runInContext(await fs.readFile(new URL('../zotero-plugin/bootstrap.js',import.meta.url),'utf8'),scope);
await scope.startup({id:'paper-translator@local'});
handler({params:{annotation:{text:'attention',position:{pageIndex:0}}},
    reader:{itemID:42,_internalReader:{_primaryView:{_iframeWindow:{PDFViewerApplication:{pdfDocument:{
        getPage:async()=>({getTextContent:async()=>({items:[{str:'Neural networks use attention to weight the values.'}]})})
    }}}}}},doc:{createElement:()=>({isConnected:true})},append:()=>{}});
let timeout;
try { await Promise.race([sent,new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Plugin timed out')),5000);})]); }
finally {clearTimeout(timeout);scope.shutdown();}
console.log('Plugin delivered selection through real localhost HTTP');
