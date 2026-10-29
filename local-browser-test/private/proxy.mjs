// Private chat page: http://127.0.0.1:11435 -> llama.cpp chat page on :11434.
// Same page, own browser storage (different port = different origin). On every new tab it first wipes the
// chats saved for this address, and it asks the browser to delete them again when the tab closes.
import http from 'node:http';
import zlib from 'node:zlib';

const UP = { host: '127.0.0.1', port: 11434 };
const PORT = 11435;
const DBS = ['LlamaUi', 'LlamacppWebui', 'LlamaCppWebui'];

const INJECT = `<script>(function(){
var D=${JSON.stringify(DBS)};
function wipeNow(){D.forEach(function(n){try{indexedDB.deleteDatabase(n)}catch(e){}})}
try{
 if(!sessionStorage.getItem('privateChatReady')){
  sessionStorage.setItem('privateChatReady','1');
  window.stop();
  try{localStorage.clear()}catch(e){}
  var list=indexedDB.databases?indexedDB.databases().then(function(l){return l.map(function(d){return d.name})}):Promise.resolve([]);
  list.then(function(names){
   names=names.concat(D);
   return Promise.all(names.map(function(n){return new Promise(function(r){var q=indexedDB.deleteDatabase(n);q.onsuccess=q.onerror=q.onblocked=function(){r()}})}));
  }).then(function(){location.reload()},function(){location.reload()});
 } else {
  window.addEventListener('pagehide',wipeNow);
 }
}catch(e){}
document.title='Private chat';
})();</script>`;

http.createServer((req, res) => {
  const headers = { ...req.headers, host: `${UP.host}:${UP.port}` };
  // the chat page checks Origin on some calls: present ourselves as the normal page
  if (headers.origin) headers.origin = `http://${UP.host}:${UP.port}`;
  const isPage = req.method === 'GET' && (req.url === '/' || req.url.startsWith('/?') || req.url.startsWith('/index.html'));
  if (isPage) headers['accept-encoding'] = 'gzip';
  const up = http.request({ ...UP, method: req.method, path: req.url, headers }, (ur) => {
    const ct = String(ur.headers['content-type'] || '');
    if (isPage && ct.includes('text/html')) {
      const chunks = [];
      ur.on('data', (c) => chunks.push(c));
      ur.on('end', () => {
        let buf = Buffer.concat(chunks);
        if (String(ur.headers['content-encoding'] || '').includes('gzip')) buf = zlib.gunzipSync(buf);
        let html = buf.toString('utf8');
        html = html.includes('<head>') ? html.replace('<head>', '<head>' + INJECT) : INJECT + html;
        const h = { ...ur.headers };
        delete h['content-length']; delete h['content-encoding']; delete h['etag'];
        h['cache-control'] = 'no-store';
        res.writeHead(ur.statusCode, h);
        res.end(html);
      });
    } else {
      res.writeHead(ur.statusCode, ur.headers);
      ur.pipe(res);
    }
  });
  up.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end('chat server not running (llm-up)'); });
  req.pipe(up);
}).listen(PORT, '127.0.0.1', () => console.log(`private chat on http://127.0.0.1:${PORT}`));
