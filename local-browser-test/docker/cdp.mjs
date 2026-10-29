// Tiny CDP helper for the chat-page Chrome. Usage (in node:22 container, --network host):
//   node cdp.mjs <port> eval '<js>' | shot <file> | type '<text>' | key Enter | nav <url>
const [port, cmd, arg] = process.argv.slice(2);
const tabs = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).filter(t => t.type === 'page');
const ws = new WebSocket(tabs[0].webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const pend = {};
ws.onmessage = m => { const d = JSON.parse(m.data); if (pend[d.id]) { pend[d.id](d); delete pend[d.id]; } };
const call = (method, params = {}) => new Promise(r => { pend[++id] = r; ws.send(JSON.stringify({ id, method, params })); });
const fs = await import('node:fs');
if (cmd === 'eval') { const r = await call('Runtime.evaluate', { expression: arg, returnByValue: true, awaitPromise: true }); console.log(JSON.stringify(r.result?.result?.value ?? r.result)); }
if (cmd === 'shot') { const r = await call('Page.captureScreenshot', { format: 'png' }); fs.writeFileSync(arg, Buffer.from(r.result.data, 'base64')); console.log('saved', arg); }
if (cmd === 'type') { await call('Input.insertText', { text: arg }); console.log('typed'); }
if (cmd === 'key') { for (const type of ['keyDown', 'keyUp']) await call('Input.dispatchKeyEvent', { type, key: arg, code: arg, windowsVirtualKeyCode: arg === 'Enter' ? 13 : 0, text: type === 'keyDown' && arg === 'Enter' ? '\r' : undefined }); console.log('key', arg); }
if (cmd === 'hover' || cmd === 'click') {  // real mouse on the element matching CSS selector arg
  const r = await call('Runtime.evaluate', { expression: `(()=>{const e=document.querySelector(${JSON.stringify(arg)}); if(!e) return null; e.scrollIntoView({block:'center'}); const b=e.getBoundingClientRect(); return [b.x+b.width/2, b.y+b.height/2]})()`, returnByValue: true });
  const xy = r.result?.result?.value; if (!xy) { console.log('not found', arg); process.exit(1); }
  await call('Input.dispatchMouseEvent', { type: 'mouseMoved', x: xy[0], y: xy[1] });
  if (cmd === 'click') for (const type of ['mousePressed', 'mouseReleased']) await call('Input.dispatchMouseEvent', { type, x: xy[0], y: xy[1], button: 'left', clickCount: 1 });
  console.log(cmd, arg, xy.map(Math.round).join(','));
}
if (cmd === 'nav') { await call('Page.navigate', { url: arg }); console.log('nav', arg); }
process.exit(0);
