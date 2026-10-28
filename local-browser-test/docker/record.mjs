// Save a JPEG of the active page in the test Chrome (127.0.0.1:9333) every 0.5 s to /out/NNNNN.jpg until killed.
const base = 'http://127.0.0.1:9333';
let n = 0, ws = null, wsUrl = null, id = 0;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
async function connect() {
  const tabs = (await (await fetch(base + '/json')).json()).filter(t => t.type === 'page');
  const t = tabs[0]; if (!t) return;
  if (ws && wsUrl === t.webSocketDebuggerUrl && ws.readyState === 1) return;
  try { ws?.close(); } catch {}
  wsUrl = t.webSocketDebuggerUrl; ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  ws.onmessage = async (m) => {
    const d = JSON.parse(m.data);
    if (d.result?.data) { const fs = await import('node:fs'); fs.writeFileSync(`/out/${String(n++).padStart(5, '0')}.jpg`, Buffer.from(d.result.data, 'base64')); }
  };
}
for (;;) {
  try { await connect(); ws.send(JSON.stringify({ id: ++id, method: 'Page.captureScreenshot', params: { format: 'jpeg', quality: 60 } })); } catch {}
  await sleep(500);
}
