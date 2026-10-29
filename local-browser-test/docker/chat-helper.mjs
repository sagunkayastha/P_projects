// Auto-compact helper for long tasks in the llama.cpp chat page (the chat window on CDP port 9334).
// Loop: the model posts a PROGRESS REPORT and stops -> click "Compact conversation" (context gauge) -> wait ->
// send "continue". Answers the "Agentic turn limit reached. Continue?" prompt up to a cap. Stops on the final
// answer (idle, no PROGRESS REPORT), on an error dialog, or after a stall (page unchanged STALL_S while running:
// press Stop, send "continue" once; a second stall ends the run).
// Env: PORT=9334 STALL_S=180 MAX_TURN_CONTINUES=4 (x agenticMaxTurns 60 = ~300 turns) MAX_ROUNDS=15 LOG=/out/helper.log
import fs from 'node:fs';
const PORT = process.env.PORT || 9334, STALL_S = +(process.env.STALL_S || 180);
const MAX_TURN_CONTINUES = +(process.env.MAX_TURN_CONTINUES || 4), MAX_ROUNDS = +(process.env.MAX_ROUNDS || 15);
const LOG = process.env.LOG || '/out/chat-helper.log';
const MAX_USED = +(process.env.MAX_USED || 70);    // context % that forces a stop + compaction mid-run
const MAX_NUDGES = +(process.env.MAX_NUDGES || 5);   // model stopped mid-task (no report, no final table)
const t0 = Date.now();
const log = (m) => { const l = `[${new Date().toISOString().slice(11, 19)} +${Math.round((Date.now() - t0) / 1000)}s] ${m}`; console.log(l); fs.appendFileSync(LOG, l + '\n'); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

let ws, id = 0; const pend = {};
async function connect() {
  const tabs = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).filter(t => t.type === 'page' && t.url.includes(':11434'));
  if (!tabs.length) throw new Error('chat page tab not found on port ' + PORT);
  ws = new WebSocket(tabs[0].webSocketDebuggerUrl); await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  ws.onmessage = m => { const d = JSON.parse(m.data); if (pend[d.id]) { pend[d.id](d); delete pend[d.id]; } };
}
const call = (method, params = {}) => new Promise(r => { pend[++id] = r; ws.send(JSON.stringify({ id, method, params })); });
const ev = async (expr) => (await call('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
async function mouse(selectorExpr, click) {   // selectorExpr = JS expression returning an element
  const xy = await ev(`(()=>{const e=${selectorExpr}; if(!e) return null; e.scrollIntoView({block:'center'}); const b=e.getBoundingClientRect(); return [b.x+b.width/2,b.y+b.height/2]})()`);
  if (!xy) return false;
  await call('Input.dispatchMouseEvent', { type: 'mouseMoved', x: xy[0], y: xy[1] });
  if (click) for (const type of ['mousePressed', 'mouseReleased']) await call('Input.dispatchMouseEvent', { type, x: xy[0], y: xy[1], button: 'left', clickCount: 1 });
  return true;
}
const btn = (re) => `[...document.querySelectorAll('button')].find(b=>${re}.test((b.getAttribute('aria-label')||'')+' '+b.innerText))`;
const state = () => ev(`(()=>{const t=document.body.innerText; const b=[...document.querySelectorAll('button')].map(x=>(x.getAttribute('aria-label')||'')+'|'+x.innerText.trim());
  return {len:t.length, tail:t.slice(-4000), running:b.some(x=>/^Stop( generation)?\\|/.test(x)), compacting:/Compacting\\.\\.\\./.test(t),
    turnLimit:/Agentic turn limit reached/.test(t), error:!!document.querySelector('[role=alertdialog]') || /Server Error/.test(t.slice(-3000)),
    used:(t.match(/(\\d+)% used/)||[])[1]}})()`);
async function send(text) {
  await ev(`document.querySelector('textarea').focus()`);
  await call('Input.insertText', { text });
  for (const type of ['keyDown', 'keyUp']) await call('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: type === 'keyDown' ? '\r' : undefined });
  log(`sent "${text}"`);
}
async function usedPct() {
  await mouse(`document.querySelector('[aria-label="Context usage"]')`, false); await sleep(800);
  const v = await ev(`(document.body.innerText.match(/(\\d+)% used/)||[])[1]`);
  await call('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 5, y: 5 });
  return v ? +v : null;
}
let lastPctCheck = 0, staleUntil = 0, stalePct = null;  // gauge keeps the old % until the next turn ends
async function compact() {
  await mouse(`document.querySelector('[aria-label="Context usage"]')`, false); await sleep(1200);
  const pct = (await state()).used;
  if (!await mouse(btn('/Compact conversation/'), true)) { log(`no "Compact conversation" button (context ${pct}% used); skipping compaction`); await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape' }); return false; }
  log(`compacting (context ${pct}% used)`); await sleep(2000);
  for (let i = 0; i < 300; i++) { const s = await state(); if (!s.compacting && !s.running) break; await sleep(2000); }
  log('compaction done'); return true;
}

await connect();
log(`helper started: stall ${STALL_S}s, max turn-limit continues ${MAX_TURN_CONTINUES}, max rounds ${MAX_ROUNDS}`);
let forced = 0, nudges = 0, lastLen = -1, lastChange = Date.now(), stalls = 0, turnContinues = 0, rounds = 0, compactions = 0, idleSince = null, seenRunning = false;
for (;;) {
  await sleep(3000);
  let s; try { s = await state(); } catch (e) { log('lost the page: ' + e.message); try { await connect(); } catch {} continue; }
  if (s.len !== lastLen) { lastLen = s.len; lastChange = Date.now(); }
  if (s.error) { log('ERROR on page, stopping: ' + (await ev(`(document.querySelector('[role=alertdialog]')||{}).innerText||''`) || s.tail.slice(-300)).replace(/\s+/g,' ').slice(0, 300)); break; }
  if (s.turnLimit) {
    if (turnContinues >= MAX_TURN_CONTINUES) { log(`turn limit reached ${turnContinues + 1} times: cap hit, stopping`); break; }
    if (await mouse(btn('/^\\s*Continue\\s*$/'), true)) { turnContinues++; log(`turn limit: clicked Continue (${turnContinues}/${MAX_TURN_CONTINUES})`); }
    continue;
  }
  if (s.running || s.compacting) {
    seenRunning = true; idleSince = null;
    if (!s.compacting && Date.now() - lastPctCheck > 20000) {
      lastPctCheck = Date.now(); const pct = await usedPct();
      if (pct !== null && pct >= MAX_USED && !(pct === stalePct && Date.now() < staleUntil + 600000) && Date.now() > staleUntil) {
        forced++; log(`context ${pct}% used >= ${MAX_USED}%: stopping the run to compact (forced ${forced})`);
        await mouse(btn('/^Stop( generation)?/'), true);
        for (let i = 0; i < 30 && (await state()).running; i++) await sleep(1000);
        await sleep(2000);
        if (await compact()) compactions++;
        stalePct = await usedPct(); staleUntil = Date.now() + 90000; log(`after compaction the gauge shows ${stalePct}% (ignored until it changes)`);
        await send('continue (the conversation was compacted: trust the NOTE lines, do not redo DONE items)');
        seenRunning = false; idleSince = null; lastChange = Date.now();
        for (let i = 0; i < 20 && !(await state()).running; i++) await sleep(1000);
        seenRunning = true; continue;
      }
    }
    if ((Date.now() - lastChange) / 1000 > STALL_S) {
      stalls++; log(`STALL: page unchanged for ${STALL_S}s while running (stall ${stalls})`);
      await mouse(btn('/^Stop( generation)?/'), true); await sleep(3000);
      if (stalls >= 2) { log('second stall: stopping'); break; }
      await send('continue'); lastChange = Date.now();
    }
    continue;
  }
  if (!seenRunning) continue;                       // wait until the user starts a task
  idleSince = idleSince || Date.now();
  if (Date.now() - idleSince < 4000) continue;      // settle
  const last = s.tail.slice(-3500);
  if (/PROGRESS REPORT/i.test(last)) {
    rounds++;
    if (rounds > MAX_ROUNDS) { log(`round cap ${MAX_ROUNDS} hit, stopping`); break; }
    log(`round ${rounds}: PROGRESS REPORT seen`);
    if (await compact()) compactions++;
    await send('continue'); seenRunning = false; idleSince = null; lastChange = Date.now();
    for (let i = 0; i < 20 && !(await state()).running; i++) await sleep(1000);
    seenRunning = true;
    continue;
  }
  const tableRows = (last.match(/^[^\n]*\t[^\n]*\t[^\n]*$/gm) || []).length;   // rendered table rows (tab separated)
  if (tableRows < 6 && nudges < MAX_NUDGES) {
    nudges++; log(`model stopped without PROGRESS REPORT or final table (nudge ${nudges}/${MAX_NUDGES})`);
    await send('continue: make your next tool call now. If every item is done, give the final table.');
    seenRunning = false; idleSince = null; lastChange = Date.now();
    for (let i = 0; i < 20 && !(await state()).running; i++) await sleep(1000);
    seenRunning = true;
    continue;
  }
  log(`final answer (${tableRows} table rows). Rounds ${rounds}, compactions ${compactions} (forced ${forced}), turn-limit continues ${turnContinues}, nudges ${nudges}, stalls ${stalls}. Done.`);
  break;
}
process.exit(0);
