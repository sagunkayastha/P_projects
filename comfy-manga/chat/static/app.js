"use strict";
// Manga maker — one page, no framework. Views: chat, gallery, chars, char, page. Overlays: drawer, viewer, sheet.
// Live updates: long poll /api/wait (server bumps a revision on every change), then refetch the open view.

const $ = (s, r = document) => r.querySelector(s);
const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
  return e;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
const imgUrl = (id) => `/api/images/${id}?k=${window.STORE}`;  // k: this store (ids repeat across stores)
const thumbUrl = (id, s) => `/api/images/${id}/thumb?k=${window.STORE}${s ? "&s=" + s : ""}`;

async function api(method, url, body) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 20000);
  let r;
  try {
    r = await fetch(url, {
      method, signal: ctl.signal,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new Error(e.name === "AbortError" ? "no answer from the app (timeout)" : "can't reach the app (offline?)");
  } finally { clearTimeout(t); }
  if (!r.ok) {
    let msg = `error ${r.status}`;
    try { const j = await r.json(); if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) { /* not json */ }
    throw new Error(msg);
  }
  return r.json();
}

let toastTimer;
function toast(msg, opt = {}) {
  const t = $("#toast");
  t.replaceChildren(el("span", { text: msg }));
  if (opt.action) t.append(el("button", { text: opt.action, onclick: () => { t.hidden = true; opt.onaction(); } }));
  t.className = opt.err ? "err" : "";
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, opt.ms || (opt.err ? 6000 : 3500));
}

// ---------- keyboard-safe height (Chrome resizes for us via interactive-widget; this covers the rest) ----------
function fitViewport() {
  const vv = window.visualViewport;
  if (!vv) return;
  document.documentElement.style.setProperty("--vvh", vv.height + "px");
  document.documentElement.style.setProperty("--vvtop", vv.offsetTop + "px");
  if (vv.offsetTop) window.scrollTo(0, 0);
}
if (window.visualViewport) {
  visualViewport.addEventListener("resize", fitViewport);
  visualViewport.addEventListener("scroll", fitViewport);
  fitViewport();
}

// ---------- navigation + back button ----------
const VIEWS = { chat: "Chat", gallery: "Gallery", chars: "Characters", char: "Character", director: "Director", page: "Make page" };
let cur = { view: "chat", ov: [] };

function apply(st) {
  cur = { view: VIEWS[st.view] ? st.view : "chat", id: st.id, ov: st.ov || [] };
  for (const v of Object.keys(VIEWS)) $("#v-" + v).hidden = v !== cur.view;
  $("#title").textContent = cur.view === "char" && charCache[cur.id] ? charCache[cur.id].name : VIEWS[cur.view];
  for (const b of document.querySelectorAll(".ditem[data-view]")) b.classList.toggle("on", b.dataset.view === cur.view);
  const dOpen = cur.ov.includes("drawer");
  $("#drawer").classList.toggle("open", dOpen);
  $("#shade").classList.toggle("open", dOpen);
  if (!cur.ov.includes("viewer") || !V.list.length) closeViewerNow();
  if (!cur.ov.includes("sheet")) $("#sheet").hidden = true;
  refresh();
}
function go(view, id) {  // a new screen; back returns to the one before
  const st = { view, id, ov: [] };
  if (cur.ov.length) history.replaceState(st, "", "#" + view); else history.pushState(st, "", "#" + view);
  apply(st);
}
function openOv(name) {
  if (cur.ov.includes(name)) return;
  const st = { ...cur, ov: [...cur.ov, name] };
  history.pushState(st, "", location.hash);
  apply(st);
}
function closeOv(name) {
  if (!cur.ov.includes(name)) return;
  if (cur.ov[cur.ov.length - 1] === name && history.state && (history.state.ov || []).includes(name)) history.back();
  else { const st = { ...cur, ov: cur.ov.filter((x) => x !== name) }; history.replaceState(st, "", location.hash); apply(st); }
}
window.addEventListener("popstate", (e) => apply(e.state || { view: location.hash.slice(1) || "chat", ov: [] }));

$("#menu").addEventListener("click", () => { openOv("drawer"); loadDrawer(); });
$("#shade").addEventListener("click", () => closeOv("drawer"));
for (const b of document.querySelectorAll(".ditem[data-view]")) b.addEventListener("click", () => go(b.dataset.view));
$("#newchat").addEventListener("click", async () => {
  try { const c = await api("POST", "/api/chats"); setChat(c.id); go("chat"); $("#text").focus(); }
  catch (e) { toast(e.message, { err: true }); }
});

// ---------- live sync ----------
let rev = -1, waitCtl = null, version = window.APP_VERSION, queueN = 0;
function setConn(state) { $("#conn").className = "dot " + state; }
async function syncLoop() {
  for (;;) {
    waitCtl = new AbortController();
    const t = setTimeout(() => waitCtl.abort(), 40000);
    try {
      const r = await fetch(`/api/wait?since=${rev}`, { signal: waitCtl.signal });
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      setConn(d.comfy === "up" ? "up" : "wait");
      $("#banner").hidden = d.comfy === "up" && !(d.version !== version);
      if (d.comfy !== "up") $("#banner").textContent = "Picture engine (ComfyUI) is off or starting (LLM mode stops it) — jobs wait and continue by themselves.";
      if (d.version !== version) {
        $("#banner").replaceChildren("A new version of the app is ready.",
          el("button", { text: "Reload", onclick: () => location.reload() }));
        $("#banner").hidden = false;
      }
      queueN = d.queue;
      $("#queue").hidden = !queueN;
      $("#queue").textContent = `${queueN} in queue`;
      if (d.rev !== rev) { rev = d.rev; refresh(); }
    } catch (e) {
      if (!document.hidden && !(e.name === "AbortError" && waitCtl.reason === "wake")) {
        setConn("down");
        await sleep(2000);
      }
    } finally { clearTimeout(t); }
  }
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) { rev = -1; if (waitCtl) waitCtl.abort("wake"); }
});
window.addEventListener("pageshow", (e) => { if (e.persisted) { rev = -1; if (waitCtl) waitCtl.abort("wake"); } });

let busy = false, again = false;
async function refresh() {
  if (busy) { again = true; return; }
  busy = true;
  try {
    do {
      again = false;
      if (cur.view === "chat") await loadChat();
      else if (cur.view === "gallery") await galleryTop();
      else if (cur.view === "chars") await loadChars();
      else if (cur.view === "char") await loadChar(cur.id);
      else if (cur.view === "page") await loadPages();
      else if (cur.view === "director") await loadDirector();
      if (cur.ov.includes("drawer")) await loadDrawer();
    } while (again);
  } catch (e) { /* shown by the sync dot; next change retries */ }
  finally { busy = false; }
}

// ---------- chat ----------
let chatId = LS.get("manga-chat", null);
const pending = new Map();  // ckey -> {text, shape, chars, state, error}
let msgs = [];
const rendered = new Map();  // message id -> {sig, node}
let state = { shape: LS.get("manga-shape", "tall"), chars: LS.get("manga-chars", []) };
const log = $("#log"), text = $("#text");

function setChat(id) {
  chatId = id; LS.set("manga-chat", id);
  msgs = []; rendered.clear(); pending.clear();
  for (const n of [...log.querySelectorAll(".msg")]) n.remove();
}
async function ensureChat() {
  if (chatId) return;
  const list = await api("GET", "/api/chats");
  setChat(list.length ? list[0].id : (await api("POST", "/api/chats")).id);
}

const nearBottom = () => log.scrollHeight - log.scrollTop - log.clientHeight < 80;
log.addEventListener("scroll", () => { if (nearBottom()) $("#tobottom").hidden = true; });
$("#tobottom").addEventListener("click", () => { log.scrollTop = log.scrollHeight; $("#tobottom").hidden = true; });

async function loadChat() {
  await ensureChat();
  let d;
  try { d = await api("GET", `/api/chats/${chatId}`); }
  catch (e) { if (/no such chat/.test(e.message)) { chatId = null; return loadChat(); } throw e; }
  msgs = d.messages;
  renderChat();
}

function jobStatus(j, est) {
  if (!j) return el("div", { class: "st", text: "…" });
  if (j.status === "queued") return el("div", { class: "st", text: j.ahead ? `waiting · ${j.ahead} ahead in the queue` : "waiting for the GPU…" });
  if (j.status === "running") {
    const pct = j.total ? Math.round((100 * j.progress) / j.total) : 0;
    return el("div", {}, el("div", { class: "bar" + (j.total ? "" : " ind") }, el("i", { style: `width:${pct}%` })),
      el("div", { class: "st", text: j.total ? `drawing · step ${j.progress}/${j.total}` : "starting (loading the model)…" }));
  }
  if (j.status === "failed") return el("div", { class: "st err", text: "failed: " + (j.error || "unknown error") });
  if (j.status === "cancelled") return el("div", { class: "st", text: "stopped" });
  return null;
}

function chatImages() { return msgs.filter((m) => m.job && m.job.image_id).map((m) => ({ id: m.job.image_id })); }

function renderMsg(m) {
  const j = m.job;
  const who = (m.chars || []).length ? el("span", { class: "who", text: "with " + m.chars.join(", ") }) : null;
  const res = el("div", { class: "res" });
  if (j && j.image_id) {
    const img = el("img", { src: thumbUrl(j.image_id, "m"), alt: m.text, width: j.w, height: j.h, loading: "lazy" });
    img.addEventListener("click", () => { const L = chatImages(); openViewer(L, L.findIndex((x) => x.id === j.image_id)); });
    res.append(img, el("div", { class: "acts" },
      el("a", { class: "btn", href: imgUrl(j.image_id) + "&dl=1", download: "" }, "⬇ Save"),
      el("button", { class: "btn star", onclick: () => makeCharSheet(j.image_id) }, "★ Make character")),
      el("div", { class: "retry" }, "Try again:",
        el("button", { class: "btn", onclick: () => again_(m.id, "new") }, "New seed"),
        el("button", { class: "btn", onclick: () => again_(m.id, "same") }, "Same seed")));
  } else {
    const ar = m.shape === "wide" ? 1.75 : m.shape === "square" ? 1 : 0.68;
    if (j && (j.status === "queued" || j.status === "running")) res.append(el("div", { class: "ph", style: `--ar:${ar}` }, "✎"));
    res.append(jobStatus(j));
    const acts = el("div", { class: "acts" });
    if (j && (j.status === "queued" || j.status === "running")) acts.append(el("button", { class: "btn danger", onclick: () => stopJob(j.id) }, "■ Stop"));
    if (j && (j.status === "failed" || j.status === "cancelled")) acts.append(el("button", { class: "btn", onclick: () => again_(m.id, "new") }, "↻ Try again"));
    if (acts.childNodes.length) res.append(acts);
  }
  const line = el("div", { class: "me" }, m.text, who);
  const cp = el("button", { class: "btn small", onclick: () => copyText(m.text, cp, line) }, "Copy prompt");
  const tools = el("div", { class: "msgtools" }, cp, el("button", { class: "btn small", onclick: () => editMsg(m) }, "Edit"));
  return el("div", { class: "msg", "data-id": m.id }, line, tools, res);
}

function renderPending(key, p) {
  const node = el("div", { class: "msg pending", "data-key": key },
    el("div", { class: "me" }, p.text, p.chars.length ? el("span", { class: "who", text: "with " + p.chars.join(", ") }) : null));
  if (p.state === "failed") node.append(el("button", { class: "notsent", onclick: () => sendPending(key) }, `Not sent: ${p.error} · tap to retry`));
  else node.append(el("div", { class: "st", text: "sending…" }));
  return node;
}

function renderChat() {
  const stick = nearBottom();
  const ids = new Set(msgs.map((m) => m.id));
  for (const [id, r] of rendered) if (!ids.has(id)) { r.node.remove(); rendered.delete(id); }
  let prev = $("#log-empty");
  let added = false;
  for (const m of msgs) {
    const sig = JSON.stringify([m.text, m.chars, m.job]);
    let r = rendered.get(m.id);
    if (!r || r.sig !== sig) {
      const node = renderMsg(m);
      if (r) r.node.replaceWith(node); else { added = true; }
      r = { sig, node }; rendered.set(m.id, r);
    }
    if (prev.nextSibling !== r.node) prev.after(r.node);
    prev = r.node;
  }
  for (const n of [...log.querySelectorAll(".msg.pending")]) n.remove();
  for (const [k, p] of pending) { const n = renderPending(k, p); prev.after(n); prev = n; }
  $("#log-empty").hidden = msgs.length + pending.size > 0;
  if (stick) log.scrollTop = log.scrollHeight;
  else if (added) $("#tobottom").hidden = false;
}

function autosize() { text.style.height = "auto"; text.style.height = Math.min(text.scrollHeight, 160) + "px"; }
text.value = LS.get("manga-draft", "");
text.addEventListener("input", () => { autosize(); LS.set("manga-draft", text.value); });
text.addEventListener("keydown", (e) => {
  // Enter sends on a desktop keyboard; on phones Enter is a new line and the ➤ button sends
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && !matchMedia("(pointer: coarse)").matches) { e.preventDefault(); send(); }
});
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });

async function send() {
  const t = text.value.trim();
  if (!t) { text.focus(); return; }
  const key = uid();
  pending.set(key, { text: t, shape: state.shape, chars: [...state.chars], state: "sending" });
  text.value = ""; LS.set("manga-draft", ""); autosize();
  renderChat(); log.scrollTop = log.scrollHeight;
  await sendPending(key);
}
async function sendPending(key) {
  const p = pending.get(key);
  if (!p) return;
  p.state = "sending"; renderChat();
  try {
    await ensureChat();
    const m = await api("POST", `/api/chats/${chatId}/messages`, { text: p.text, shape: p.shape, chars: p.chars, ckey: key });
    pending.delete(key);
    if (!msgs.find((x) => x.id === m.id)) msgs.push(m);
    renderChat(); log.scrollTop = log.scrollHeight;
  } catch (e) {
    p.state = "failed"; p.error = e.message; renderChat();
  }
}
// Copy: the LAN page is plain http, where navigator.clipboard is missing (iPhone Safari) -> hidden textarea +
// execCommand("copy"); if even that fails, select the prompt text so the user can copy it by hand.
function copyText(t, btn, node) {
  const done = (ok) => {
    if (ok) { btn.textContent = "Copied"; setTimeout(() => { btn.textContent = "Copy prompt"; }, 1500); return; }
    const r = document.createRange(); r.selectNodeContents(node);
    const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
    btn.textContent = "Selected - copy it";
  };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(t).then(() => done(true), () => done(legacyCopy(t)));
  else done(legacyCopy(t));
}
function legacyCopy(t) {
  const ta = el("textarea", { readonly: true, style: "position:fixed;top:0;left:0;opacity:0;font-size:16px" });
  ta.value = t; document.body.append(ta);
  ta.focus(); ta.select(); ta.setSelectionRange(0, t.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  ta.remove();
  return ok;
}
async function again_(mid, seed) {
  try { await api("POST", `/api/messages/${mid}/again`, { seed: seed || "new" }); log.scrollTop = log.scrollHeight; refresh(); }
  catch (e) { toast(e.message, { err: true }); }
}
function editMsg(m) {  // put this message back in the box to change it; sending makes one new picture
  text.value = m.text; LS.set("manga-draft", text.value); autosize();
  state.chars = (m.chars || []).filter((s) => charBySlug[s]); LS.set("manga-chars", state.chars); paintChips();
  if (m.shape) { state.shape = m.shape; LS.set("manga-shape", state.shape); paintChips(); }
  text.focus(); text.setSelectionRange(text.value.length, text.value.length);
  toast("Change the text, then ➤ to draw it again");
}
async function stopJob(jid) {
  try { await api("POST", `/api/jobs/${jid}/cancel`); refresh(); } catch (e) { toast(e.message, { err: true }); }
}

// shape + characters for the next message
function paintChips() {
  for (const b of $("#shape").querySelectorAll("button")) b.classList.toggle("on", b.dataset.v === state.shape);
  const c = $("#charpick");
  c.textContent = state.chars.length ? "With: " + state.chars.map((s) => (charBySlug[s] || { name: s }).name).join(", ") : "With: nobody";
  c.classList.toggle("on", state.chars.length > 0);
}
$("#shape").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  state.shape = b.dataset.v; LS.set("manga-shape", state.shape); paintChips();
});
$("#charpick").addEventListener("click", async () => {
  await loadCharList();
  const ready = chars.filter((c) => c.status === "ready");
  const sel = new Set(state.chars.filter((s) => charBySlug[s] && charBySlug[s].status === "ready"));
  const body = el("div", {}, el("h2", { text: "Draw with a character" }),
    el("div", { class: "sub", text: ready.length ? "Pick up to 2. The picture keeps their face and outfit." : "No characters yet. Tap ★ Make character on any picture first." }));
  const pick = el("div", { class: "pick" });
  const paint = () => { for (const b of pick.children) b.classList.toggle("on", sel.has(b.dataset.slug)); };
  for (const c of ready) {
    pick.append(el("button", { "data-slug": c.slug, onclick: () => {
      if (sel.has(c.slug)) sel.delete(c.slug); else if (sel.size < 2) sel.add(c.slug); else toast("2 characters at most");
      paint();
    } }, el("img", { src: thumbUrl(c.source_image), alt: "" }), c.name));
  }
  paint();
  body.append(pick, el("div", { class: "two" },
    el("button", { class: "ghost", onclick: () => { sel.clear(); paint(); } }, "Nobody"),
    el("button", { class: "primary", onclick: () => { state.chars = [...sel]; LS.set("manga-chars", state.chars); paintChips(); closeOv("sheet"); } }, "Done")));
  openSheet(body);
});

// ---------- gallery ----------
const G = { items: [], ids: new Set(), next: undefined, loading: false, total: 0 };
const grid = $("#grid");
function gCell(it) {
  return el("button", { "data-id": it.id, onclick: () => openViewer(G.items, G.items.findIndex((x) => x.id === it.id), galleryMore) },
    el("img", { src: thumbUrl(it.id), loading: "lazy", alt: "", decoding: "async" }));
}
async function galleryMore() {
  if (G.loading || G.next === null) return;
  G.loading = true;
  try {
    const d = await api("GET", "/api/images?limit=60" + (G.next ? "&before=" + encodeURIComponent(G.next) : ""));
    for (const it of d.items) if (!G.ids.has(it.id)) { G.ids.add(it.id); G.items.push(it); grid.append(gCell(it)); }
    G.next = d.next; G.total = d.total;
    $("#grid-end").textContent = G.items.length ? (G.next ? "loading…" : `${G.items.length} pictures`) : "No pictures yet.";
  } finally { G.loading = false; }
}
async function galleryTop() {
  if (G.next === undefined) return galleryMore();
  const d = await api("GET", "/api/images?limit=30");
  const fresh = d.items.filter((it) => !G.ids.has(it.id));
  for (const it of fresh.reverse()) { G.ids.add(it.id); G.items.unshift(it); grid.prepend(gCell(it)); }
  if (fresh.length) $("#grid-end").textContent = G.next ? "loading…" : `${G.items.length} pictures`;
}
new IntersectionObserver((es) => { if (es[0].isIntersecting && cur.view === "gallery") galleryMore(); },
  { root: $("#gallery-scroll"), rootMargin: "800px" }).observe($("#grid-end"));

// ---------- full-screen viewer: swipe, pinch, double-tap zoom, pan ----------
const V = { list: [], idx: 0, more: null, s: 1, tx: 0, ty: 0 };
const strip = $("#vstrip"), slides = [...strip.children];
function openViewer(list, idx, more) {
  if (idx < 0) idx = 0;
  V.list = list; V.idx = idx; V.more = more || null;
  $("#viewer").hidden = false;
  paintViewer();
  openOv("viewer");
}
function closeViewerNow() { $("#viewer").hidden = true; V.list = []; for (const s of slides) s.replaceChildren(); }
$("#vclose").addEventListener("click", () => closeOv("viewer"));
function slideImg(k) {
  const i = V.idx - 1 + k, it = V.list[i];
  if (!it) return null;
  return el("img", { src: imgUrl(it.id), alt: "", draggable: "false" });
}
function paintViewer() {
  V.s = 1; V.tx = 0; V.ty = 0;
  slides.forEach((s, k) => s.replaceChildren(slideImg(k) || ""));
  strip.style.transition = "none";
  strip.style.transform = "translateX(-100vw)";
  const it = V.list[V.idx];
  $("#vcount").textContent = `${V.idx + 1} / ${V.list === G.items && G.total ? G.total : V.list.length}`;
  $("#vdl").href = imgUrl(it.id) + "&dl=1";
  $("#vchar").hidden = it.source === "page";
  if (V.more && V.idx > V.list.length - 6) V.more().then(() => { if (!$("#viewer").hidden) slides[2].replaceChildren(slideImg(2) || ""); });
}
$("#vchar").addEventListener("click", () => makeCharSheet(V.list[V.idx].id));
function curImg() { return slides[1].querySelector("img"); }
function setZoom() {
  const img = curImg(); if (!img) return;
  const r = img.getBoundingClientRect();
  const w = (r.width / V.s), h = (r.height / V.s);  // unscaled size
  const mx = Math.max(0, (w * V.s - innerWidth) / 2), my = Math.max(0, (h * V.s - innerHeight) / 2);
  V.tx = Math.max(-mx, Math.min(mx, V.tx)); V.ty = Math.max(-my, Math.min(my, V.ty));
  img.style.transform = `translate(${V.tx}px, ${V.ty}px) scale(${V.s})`;
}
function step(dir) {
  const ni = V.idx + dir;
  if (ni < 0 || ni >= V.list.length) { strip.style.transition = "transform .2s"; strip.style.transform = "translateX(-100vw)"; return; }
  strip.style.transition = "transform .22s ease-out";
  strip.style.transform = `translateX(${-100 - 100 * dir}vw)`;
  setTimeout(() => { V.idx = ni; paintViewer(); }, 220);
}
(() => {
  const pts = new Map();
  let g = null, lastTap = 0, tapTimer = null;
  const vw = () => innerWidth;
  const rel = (p) => ({ x: p.x - innerWidth / 2, y: p.y - innerHeight / 2 });
  const viewer = $("#viewer");
  viewer.addEventListener("pointerdown", (e) => {
    if (e.target.closest("#vbar")) return;
    viewer.setPointerCapture(e.pointerId);
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const P = [...pts.values()];
    if (P.length === 2) {
      const mid = rel({ x: (P[0].x + P[1].x) / 2, y: (P[0].y + P[1].y) / 2 });
      g = { kind: "pinch", d0: Math.hypot(P[0].x - P[1].x, P[0].y - P[1].y), s0: V.s, t0: { x: V.tx, y: V.ty }, m0: mid };
      strip.style.transform = "translateX(-100vw)";
    } else if (P.length === 1) {
      g = { kind: V.s > 1.01 ? "pan" : "swipe", x0: e.clientX, y0: e.clientY, t0: { x: V.tx, y: V.ty }, at: Date.now(), moved: false };
    }
  });
  viewer.addEventListener("pointermove", (e) => {
    if (!pts.has(e.pointerId) || !g) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const P = [...pts.values()];
    if (g.kind === "pinch" && P.length === 2) {
      const d = Math.hypot(P[0].x - P[1].x, P[0].y - P[1].y);
      const mid = rel({ x: (P[0].x + P[1].x) / 2, y: (P[0].y + P[1].y) / 2 });
      const s = Math.max(1, Math.min(6, g.s0 * d / g.d0));
      V.tx = mid.x - (s / g.s0) * (g.m0.x - g.t0.x); V.ty = mid.y - (s / g.s0) * (g.m0.y - g.t0.y); V.s = s;
      setZoom();
    } else if (g.kind === "pan") {
      V.tx = g.t0.x + e.clientX - g.x0; V.ty = g.t0.y + e.clientY - g.y0;
      if (Math.hypot(e.clientX - g.x0, e.clientY - g.y0) > 8) g.moved = true;
      setZoom();
    } else if (g.kind === "swipe") {
      const dx = e.clientX - g.x0, dy = e.clientY - g.y0;
      if (Math.hypot(dx, dy) > 8) g.moved = true;
      strip.style.transition = "none";
      if (g.dir === undefined && g.moved) g.dir = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
      if (g.dir === "x") strip.style.transform = `translateX(calc(-100vw + ${dx}px))`;
      else if (g.dir === "y" && dy > 0) strip.style.transform = `translate(-100vw, ${dy}px)`;
    }
  });
  const end = (e) => {
    if (!pts.has(e.pointerId)) return;
    pts.delete(e.pointerId);
    if (!g) return;
    if (g.kind === "pinch") {
      if (pts.size === 1) { const [p] = [...pts.values()]; g = { kind: V.s > 1.01 ? "pan" : "none", x0: p.x, y0: p.y, t0: { x: V.tx, y: V.ty }, moved: true }; }
      else g = null;
      if (V.s < 1.02) { V.s = 1; V.tx = 0; V.ty = 0; setZoom(); }
      return;
    }
    if (pts.size) return;
    const dx = e.clientX - g.x0, dy = e.clientY - g.y0, dt = Date.now() - (g.at || 0);
    if (g.kind === "swipe" && g.moved) {
      if (g.dir === "x" && (Math.abs(dx) > vw() * 0.2 || (Math.abs(dx) > 40 && dt < 250))) step(dx < 0 ? 1 : -1);
      else if (g.dir === "y" && dy > 120) { strip.style.transform = "translateX(-100vw)"; closeOv("viewer"); }
      else { strip.style.transition = "transform .2s"; strip.style.transform = "translateX(-100vw)"; }
    } else if (!g.moved) {
      const now = Date.now();
      if (now - lastTap < 300) {  // double tap: zoom in at the finger, or back out
        clearTimeout(tapTimer); lastTap = 0;
        const img = curImg();
        if (img) img.style.transition = "transform .2s";
        if (V.s > 1.01) { V.s = 1; V.tx = 0; V.ty = 0; }
        else { const p = rel({ x: e.clientX, y: e.clientY }); V.s = 2.5; V.tx = -1.5 * p.x; V.ty = -1.5 * p.y; }
        setZoom();
        setTimeout(() => { if (img) img.style.transition = ""; }, 220);
      } else {
        lastTap = now;
        tapTimer = setTimeout(() => { $("#vbar").hidden = !$("#vbar").hidden; }, 300);
      }
    }
    g = null;
  };
  viewer.addEventListener("pointerup", end);
  viewer.addEventListener("pointercancel", end);
  document.addEventListener("keydown", (e) => {
    if ($("#viewer").hidden) return;
    if (e.key === "ArrowRight") step(1); else if (e.key === "ArrowLeft") step(-1); else if (e.key === "Escape") closeOv("viewer");
  });
})();

// ---------- sheet (bottom dialog) ----------
function openSheet(body) { $("#sheet-body").replaceChildren(body); $("#sheet").hidden = false; openOv("sheet"); }
// Close on the dark backdrop only when the press started AND ended there: when the phone keyboard opens, the
// page moves under the finger and a tap into a text box used to land on the backdrop (sheet closed, edit lost).
let sheetDown = null;
$("#sheet").addEventListener("pointerdown", (e) => { sheetDown = e.target.id === "sheet" ? Date.now() : null; });
$("#sheet").addEventListener("click", (e) => {
  if (e.target.id === "sheet" && sheetDown && Date.now() - sheetDown < 600 && !document.activeElement.matches("textarea, input")) closeOv("sheet");
  sheetDown = null;
});
$("#sheet").addEventListener("focusin", (e) => {  // keep the box being typed in above the keyboard
  if (e.target.matches("textarea, input")) setTimeout(() => e.target.scrollIntoView({ block: "center", behavior: "smooth" }), 350);
});

function makeCharSheet(imageId) {
  const name = el("input", { type: "text", placeholder: "Name, e.g. Mia", maxlength: "40", enterkeyhint: "go" });
  const go_ = el("button", { class: "primary", type: "submit" }, "Make character");
  const form = el("form", { onsubmit: async (e) => {
    e.preventDefault();
    const n = name.value.trim();
    if (!n) { name.focus(); toast("Give the character a name"); return; }
    go_.disabled = true; go_.textContent = "Starting…";
    try {
      const c = await api("POST", "/api/characters", { image_id: imageId, name: n });
      closeOv("sheet");
      toast(`Making ${c.name}: 28 pictures, about 3 min. You can lock the phone.`, { action: "Show", onaction: () => go("chars"), ms: 6000 });
    } catch (err) { toast(err.message, { err: true }); go_.disabled = false; go_.textContent = "Make character"; }
  } },
  el("img", { class: "srcpic", src: thumbUrl(imageId), alt: "" }),
  el("h2", { text: "Make a character from this picture?" }),
  el("div", { class: "sub", text: "Draws the same person 28 times (angles, faces, outfits) and keeps the 20 that look most alike. Takes about 3 minutes in the background." }),
  el("div", { style: "clear:both;height:10px" }), name,
  el("div", { class: "two" }, el("button", { class: "ghost", type: "button", onclick: () => closeOv("sheet") }, "Cancel"), go_));
  openSheet(form);
  setTimeout(() => name.focus(), 50);
}

// ---------- characters ----------
let chars = [], charBySlug = {}, charCache = {};
async function loadCharList() {
  chars = await api("GET", "/api/characters");
  charBySlug = Object.fromEntries(chars.map((c) => [c.slug, c]));
  paintChips();
  return chars;
}
function charLine(c) {
  if (c.status === "building") return `making pictures · ${c.made} / ${c.planned}` +
    (c.step ? ` · now: ${(c.step.label || "").replace("_", " ") || "view"} · ` + (c.step.total ? `step ${c.step.progress}/${c.step.total}` : "loading the model…") : c.ahead ? ` · waiting, ${c.ahead} other jobs first` : "");
  if (c.status === "checking") return "checking faces…";
  if (c.status === "ready") return `ready · ${c.refs.length} pictures`;
  if (c.status === "review") return "made · check the pictures, then Save";
  if (c.status === "cancelled") return "stopped";
  return "failed: " + (c.error || "unknown");
}
async function loadChars() {
  await loadCharList();
  const list = $("#charlist");
  if (!chars.length) {
    list.replaceChildren(el("div", { class: "empty", text: "No characters yet. Open any picture (chat or gallery) and tap ★ Make character." }));
    return;
  }
  renderKeyed(list, charNodes, chars, charCard, (c) => JSON.stringify([c.status, c.error, c.name, c.source_image, c.made, c.planned, c.refs.length]),
    (node, c) => { const sub = node.querySelector(".sub"); if (sub) sub.textContent = charLine(c); });
}
const charNodes = new Map();
function charCard(c) {
  {
    const busyC = c.status === "building" || c.status === "checking";
    const pct = c.planned ? Math.round(100 * c.made / c.planned) : 0;
    return el("div", { class: "card" },
      el("div", { class: "crow", onclick: () => go("char", c.id) },
        el("img", { src: thumbUrl(c.source_image), alt: "" }),
        el("div", { class: "grow" }, el("h3", { text: c.name }), el("div", { class: "sub" + (c.status === "failed" ? " err" : ""), text: charLine(c) }))),
      busyC ? el("div", { class: "bar" + (c.status === "checking" ? " ind" : ""), style: "margin-top:10px" }, el("i", { style: `width:${pct}%` })) : null,
      el("div", { class: "acts", style: "padding:10px 0 0" },
        el("button", { class: "btn", onclick: () => go("char", c.id) }, "Open"),
        c.status === "ready" ? el("button", { class: "btn", onclick: () => useInChat(c) }, "💬 Use in chat") : null,
        c.status === "ready" ? el("button", { class: "btn", onclick: () => pageWith(c) }, "📖 Make page") : null,
        c.status === "review" ? el("button", { class: "btn star", onclick: () => go("char", c.id) }, "✓ Check & save") : null,
        busyC ? el("button", { class: "btn danger", onclick: () => api("POST", `/api/characters/${c.id}/cancel`).then(refresh) }, "■ Stop") : null,
        c.status === "failed" || c.status === "cancelled" ? el("button", { class: "btn", onclick: () => api("POST", `/api/characters/${c.id}/retry`).then(refresh).catch((e) => toast(e.message, { err: true })) }, "↻ Retry") : null));
  }
}
function useInChat(c) { state.chars = [c.slug]; LS.set("manga-chars", state.chars); paintChips(); go("chat"); }
function pageWith(c) { pageSel = new Set([c.slug]); go("page"); }
const review = {};  // character id -> {keep:Set, traits:string} while the user is checking a new set
async function loadChar(id) {
  const c = await api("GET", `/api/characters/${id}`);
  charCache[id] = c;
  $("#title").textContent = c.name;
  const box = $("#chardetail");
  const ae = document.activeElement;
  if (ae && ae.tagName === "TEXTAREA" && box.contains(ae) && ae.dataset.cid === String(id)) return;  // typing: no repaint
  const sig = JSON.stringify([c.id, c.status, c.error, c.refs, c.all, c.dropped, c.traits, c.made, c.planned]);
  if (box.dataset.sig === sig && box.firstChild) {  // same content: only the progress line changes (taps stay on their buttons)
    const sub = box.querySelector(".crow .sub");
    if (sub) sub.textContent = charLine(c);
    return;
  }
  box.dataset.sig = sig;
  if (c.status === "review") return box.replaceChildren(reviewCard(c));
  const refs = c.refs.map((i) => ({ id: i }));
  const dropped = (c.dropped || []).map((i) => ({ id: i }));
  const all = (c.status === "ready" ? refs : (c.all || []).map((i) => ({ id: i })));
  const gridOf = (L, cls) => el("div", { class: "refs " + (cls || "") }, L.map((it, k) => el("button", { onclick: () => openViewer(L, k) },
    el("img", { src: thumbUrl(it.id), loading: "lazy", alt: "" }))));
  const looks = el("textarea", { rows: "3", maxlength: "400", placeholder: "e.g. short black bob, round glasses, striped scarf, long cardigan" });
  looks.dataset.cid = String(id);
  looks.value = c.traits || "";
  box.replaceChildren(el("div", { class: "card" },
    el("div", { class: "crow" }, el("img", { src: thumbUrl(c.source_image), alt: "", onclick: () => openViewer([{ id: c.source_image }], 0) }),
      el("div", { class: "grow" }, el("h3", { text: c.name }), el("div", { class: "sub" + (c.status === "failed" ? " err" : ""), text: charLine(c) }))),
    c.status === "ready" ? el("div", { class: "acts", style: "padding:10px 0 0" },
      el("button", { class: "btn", onclick: () => useInChat(c) }, "💬 Use in chat"),
      el("button", { class: "btn", onclick: () => pageWith(c) }, "📖 Make page"),
      el("button", { class: "btn", onclick: () => api("POST", `/api/characters/${c.id}/retry`).then(refresh).catch((e) => toast(e.message, { err: true })) }, "✓ Check pictures again")) : null,
    c.status === "ready" ? el("div", {}, el("label", { class: "label", text: "Looks (goes into every picture of " + c.name + ")" }), looks,
      el("button", { class: "btn", style: "margin-top:6px", onclick: () => api("POST", `/api/characters/${c.id}/traits`, { traits: looks.value }).then(() => { looks.blur(); toast("Saved"); refresh(); }).catch((e) => toast(e.message, { err: true })) }, "Save looks")) : null,
    all.length ? gridOf(all) : el("div", { class: "empty", text: "Pictures appear here as they are made." }),
    dropped.length ? el("div", {}, el("div", { class: "label", text: `Not kept (${dropped.length})` }), gridOf(dropped, "dropped")) : null));
}
function reviewCard(c) {
  const sc = c.scores || {};
  const ids = (c.all || []).filter((i) => !(sc[i] && sc[i].spare));
  const st = review[c.id] || (review[c.id] = { keep: new Set(c.refs), traits: c.traits || "" });
  const count = el("span");
  const save = el("button", { class: "primary", type: "button" });
  const paintCount = () => { count.textContent = `${st.keep.size} of ${ids.length} kept`; save.textContent = `Save ${c.name} (${st.keep.size} pictures)`; save.disabled = !st.keep.size; };
  const cells = ids.map((i, k) => {
    const s = sc[i] || {};
    const b = el("button", { class: "rv" + (st.keep.has(i) ? " on" : "") + (s.drifted ? " bad" : ""), "data-id": i, "aria-pressed": st.keep.has(i) ? "true" : "false", onclick: () => {
      if (st.keep.has(i)) st.keep.delete(i); else st.keep.add(i);
      b.classList.toggle("on", st.keep.has(i)); b.setAttribute("aria-pressed", st.keep.has(i) ? "true" : "false"); paintCount();
    } },
      el("img", { src: thumbUrl(i), loading: "lazy", alt: s.label || "" }),
      el("span", { class: "tick", text: "✓" }),
      el("span", { class: "lab", text: (s.label || "").replace("_", " ") + (s.drifted ? " · unlike" : "") }));
    b.addEventListener("contextmenu", (e) => { e.preventDefault(); openViewer(ids.map((x) => ({ id: x })), k); });
    return b;
  });
  const looks = el("textarea", { rows: "3", maxlength: "400", placeholder: "e.g. short black bob, round glasses, striped scarf, long cardigan" });
  looks.value = st.traits;
  looks.dataset.cid = String(c.id);
  looks.addEventListener("input", () => { st.traits = looks.value; });
  save.addEventListener("click", async () => {
    save.disabled = true;
    try { await api("POST", `/api/characters/${c.id}/save`, { keep: [...st.keep], traits: st.traits }); delete review[c.id]; toast(`${c.name} is ready`); refresh(); }
    catch (e) { toast(e.message, { err: true }); save.disabled = false; }
  });
  paintCount();
  return el("div", { class: "card review" },
    el("div", { class: "crow" }, el("img", { src: thumbUrl(c.source_image), alt: "", onclick: () => openViewer([{ id: c.source_image }], 0) }),
      el("div", { class: "grow" }, el("h3", { text: c.name }), el("div", { class: "sub", text: "Tap a picture to keep or drop it. Only kept pictures are used as references. Long-press to see it big." }))),
    el("div", { class: "label" }, count, el("span", { class: "dim", text: " · faded = looked unlike the first picture" })),
    el("div", { class: "rvgrid" }, cells),
    el("label", { class: "label", text: "Looks (written from the picture when the local AI is on; you can change it)" }), looks,
    el("div", { class: "two", style: "margin-top:12px" }, save));
}

// ---------- pages ----------
let pageSel = new Set(LS.get("manga-pagechars", []));
const lineIds = ["l1", "l2", "l3", "l4"];
const pageDraft = LS.get("manga-pagelines", ["", "", "", ""]);
{ const b = $("#lbible"); b.value = LS.get("manga-pagebible", ""); b.addEventListener("input", () => LS.set("manga-pagebible", b.value)); }
lineIds.forEach((id, i) => { const t = $("#" + id); t.value = pageDraft[i] || ""; t.addEventListener("input", () => { pageDraft[i] = t.value; LS.set("manga-pagelines", pageDraft); }); });
async function loadPages() {
  await loadCharList();
  const ready = chars.filter((c) => c.status === "ready");
  // drop a pick only when the character is gone; one that is busy for a moment (face check...) stays picked
  // (dropping it silently made pages with the other character only)
  for (const s of [...pageSel]) if (!charBySlug[s]) pageSel.delete(s);
  const shown = [...ready, ...chars.filter((c) => c.status !== "ready" && pageSel.has(c.slug))];
  const pc = $("#pagechars");
  pc.replaceChildren(...(shown.length ? shown.map((c) => el("button", { type: "button", class: "chip" + (pageSel.has(c.slug) ? " on" : ""), onclick: () => {
    if (pageSel.has(c.slug)) pageSel.delete(c.slug); else if (pageSel.size < 2) pageSel.add(c.slug); else toast("2 characters at most");
    LS.set("manga-pagechars", [...pageSel]); loadPages();
  } }, c.status === "ready" ? c.name : `${c.name} (busy)`)) : [el("span", { class: "sub", text: "No characters yet: make one from any picture (★). Without one the page uses no reference." })]));
  const pages = await api("GET", "/api/pages");
  renderKeyed($("#pagelist"), pageNodes, pages, pageCard, pageSig, patchPage);
}
// Keyed lists: a card is rebuilt only when what it shows changes; progress text is patched in place.
// (Rebuilding every card at each progress tick replaced buttons under the finger: taps on phones were lost.)
const pageNodes = new Map();
function renderKeyed(box, nodes, items, build, sig, patch) {
  const ids = new Set(items.map((x) => x.id));
  for (const [id, r] of nodes) if (!ids.has(id)) { r.node.remove(); nodes.delete(id); }
  let prev = null;
  for (const it of items) {
    const g = sig(it);
    let r = nodes.get(it.id);
    if (!r || r.sig !== g) {
      const node = build(it);
      if (r) r.node.replaceWith(node);
      r = { sig: g, node }; nodes.set(it.id, r);
    } else patch(r.node, it);
    if (prev ? prev.nextSibling !== r.node : box.firstChild !== r.node) { if (prev) prev.after(r.node); else box.prepend(r.node); }
    prev = r.node;
  }
}
const stripJob = (j) => j && { s: j.status, e: j.error, t: !!j.total };
function pageSig(p) {
  return JSON.stringify([p.status, p.error, p.image_id, p.chars, p.writer, p.bible,
    p.panels.map((x) => [x.image_id, x.line, x.cast, x.warn, x.fixed, (x.versions || []).map((v) => v.image_id), stripJob(x.job)]),
    Object.entries(p.scene || {}).map(([k, v]) => [k, v.image_id, v.error, stripJob(v.job)]), Object.keys(charBySlug).length]);
}
function patchPage(node, p) {
  const st = node.querySelector(".pstatus");
  if (st && p.status === "working") st.textContent = pageLine(p) + (p.image_id ? " · the other panels stay" : "");
  p.panels.forEach((x, i) => {
    const n = node.querySelector(`.panel[data-idx="${i}"] .n`), j = x.job;
    if (n && j && (j.status === "queued" || j.status === "running")) n.textContent = jobLine(j);
    const bar = node.querySelector(`.panel[data-idx="${i}"] .bar i`);
    if (bar && j && j.total) bar.style.width = Math.round(100 * j.progress / j.total) + "%";
  });
  for (const [k, v] of Object.entries(p.scene || {})) {
    const n = node.querySelector(`.sc[data-kind="${k}"] .n`), j = v.job;
    if (n && j && (j.status === "queued" || j.status === "running")) n.textContent = ({ plate: "Place", props: "Objects" }[k] || k) + " · " + jobLine(j);
  }
}
function pageCard(p) {
  const working = p.status === "working";
  const names = p.chars.map((s) => (charBySlug[s] || { name: s }).name);
  const panels = p.panels.map((x, i) => {
    const j = x.job;
    const running = j && (j.status === "queued" || j.status === "running");
    const pct = j && j.total ? Math.round(100 * j.progress / j.total) : 0;
    const shown = p.panels.filter((q) => q.image_id);
    const vs = x.versions || [];
    const who = (x.cast || []).map((k) => names[k]).filter(Boolean);
    return el("div", { class: "panel", "data-idx": i },
      el("div", { class: "thumb" }, x.image_id ? el("img", { src: thumbUrl(x.image_id), alt: `panel ${i + 1}`, onclick: () => openViewer(shown.map((q) => ({ id: q.image_id })), shown.findIndex((q) => q.image_id === x.image_id)) }) : null,
        running ? el("div", { class: "bar" + (j.status === "running" && j.total ? "" : " ind") }, el("i", { style: `width:${pct}%` })) : null,
        el("span", { class: "num", text: `${i + 1}` })),
      el("div", { class: "n" + (j && j.status === "failed" ? " err" : ""), text: j && j.status === "failed" ? "failed: " + (j.error || "") : running ? jobLine(j) : (who.length ? who.join(" + ") : "no character") }),
      el("div", { class: "line", text: x.line }),
      j && j.used ? el("div", { class: "used", text: "refs: " + j.used }) : null,
      x.fixed ? el("div", { class: "fixed", text: "spelling fixed (you wrote: " + x.fixed + ")" }) : null,
      x.warn ? el("div", { class: "warn", text: "⚠ " + x.warn }) : null,
      vs.length > 1 ? el("div", { class: "vers" }, vs.map((v, k) => el("button", { class: v.image_id === x.image_id ? "on" : "", "aria-label": `version ${k + 1}`, title: v.line, disabled: running || undefined, onclick: () => pickVersion(p.id, i, v.image_id) },
        el("img", { src: thumbUrl(v.image_id), alt: "" })))) : null,
      el("div", { class: "pbtns" },
        el("button", { class: "btn", disabled: running || (working && !j) || undefined, onclick: () => redo(p.id, i) }, "↻ Redo"),
        el("button", { class: "btn", disabled: running || (working && !j) || undefined, onclick: () => editPanel(p, i) }, "✎ Edit")));
  });
  return el("div", { class: "card", "data-page": p.id },
    el("h3", { text: `Page ${p.id}` + (names.length ? " · " + names.join(", ") : "") }),
    el("div", { class: "sub pstatus" + (p.error ? " err" : ""), text: working ? pageLine(p) + (p.image_id ? " · the other panels stay" : "") : (p.error || `done · prompts by ${p.writer}`) }),
    p.image_id ? el("img", { class: "pagepic", src: thumbUrl(p.image_id, "m"), alt: "page", onclick: () => openViewer([{ id: p.image_id, source: "page" }], 0) }) : null,
    sceneRow(p),
    el("div", { class: "hint", text: "Fix one panel: ↻ Redo draws it again, ✎ Edit changes its line or who is in it. Tap a small picture to go back to an older try." }),
    el("div", { class: "panels" }, panels),
    p.image_id ? el("div", { class: "acts", style: "padding:10px 0 0" }, el("a", { class: "btn", href: imgUrl(p.image_id) + "&dl=1", download: "" }, "⬇ Download PNG")) : null);
}
function jobLine(j) {  // "waiting · 3 ahead" / "loading the model…" / "step 2/4"
  if (!j) return "";
  if (j.status === "queued") return j.ahead ? `waiting · ${j.ahead} ahead` : "next";
  if (j.status === "running") return j.total ? `step ${j.progress}/${j.total}` : "loading the model…";
  return j.status;
}
function pageLine(p) {  // what this page is doing right now
  const items = [...Object.entries(p.scene || {}).map(([k, v]) => [{ plate: "place picture", props: "objects picture" }[k] || k, v.job]),
    ...p.panels.map((x, i) => [`panel ${i + 1}`, x.job])];
  const run = items.find(([, j]) => j && j.status === "running");
  const wait = items.filter(([, j]) => j && j.status === "queued");
  const parts = [];
  if (run) parts.push(`drawing ${run[0]} · ${jobLine(run[1])}`);
  if (wait.length) parts.push(`${wait.length} waiting` + (!run && wait[0][1].ahead ? ` (${wait[0][1].ahead} other jobs first)` : ""));
  const todo = p.panels.filter((x) => !x.job).length;
  const scenePending = Object.values(p.scene || {}).some((v) => !v.image_id && v.job && (v.job.status === "queued" || v.job.status === "running"));
  if (todo) parts.push(scenePending ? `${todo} panels start after the scene pictures` : `${todo} panel(s) start after the one before`);
  return parts.join(" · ") || "putting the page together…";
}
function sceneRow(p) {  // the place plate + prop sheet every panel of this page is drawn with
  const items = Object.entries(p.scene || {});
  if (!items.length) return null;
  const label = { plate: "Place", props: "Objects" };
  return el("div", { class: "scene" }, el("div", { class: "label", text: "Scene pictures (every panel gets them, plus the panel before it)" }),
    el("div", { class: "scenes" }, items.map(([k, v]) => {
      const j = v.job, running = j && (j.status === "queued" || j.status === "running");
      return el("div", { class: "sc", "data-kind": k },
        el("div", { class: "thumb" }, v.image_id ? el("img", { src: thumbUrl(v.image_id), alt: label[k] || k, onclick: () => openViewer([{ id: v.image_id }], 0) }) : null,
          running ? el("div", { class: "bar ind" }, el("i")) : null),
        el("div", { class: "n", text: (label[k] || k) + (running ? " · " + jobLine(j) : v.error ? " · failed" : "") }),
        el("button", { class: "btn", disabled: running || undefined, onclick: () => api("POST", `/api/pages/${p.id}/scene/${k}/redo`).then(() => { toast(`${label[k] || k}: drawing again. Redo panels to use the new one.`); refresh(); }).catch((e) => toast(e.message, { err: true })) }, "↻ Redo"));
    })));
}
async function redo(pid, i, body) {
  try { await api("POST", `/api/pages/${pid}/panels/${i}/redo`, body); toast(`Panel ${i + 1}: drawing again, the other panels stay`); refresh(); }
  catch (e) { toast(e.message, { err: true }); }
}
async function pickVersion(pid, i, imageId) {
  try { await api("POST", `/api/pages/${pid}/panels/${i}/pick`, { image_id: imageId }); refresh(); }
  catch (e) { toast(e.message, { err: true }); }
}
function editPanel(p, i) {
  const x = p.panels[i];
  const line = el("textarea", { rows: "3", maxlength: "400" });
  line.value = x.line;
  const sel = new Set(x.cast || []);
  const pick = el("div", { class: "chips wrap" });
  const paint = () => { for (const b of pick.children) b.classList.toggle("on", sel.has(+b.dataset.k)); };
  let touched = false;
  const nm = p.chars.map((s) => (charBySlug[s] || { name: s }).name);
  p.chars.forEach((s, k) => pick.append(el("button", { type: "button", class: "chip", "data-k": k, onclick: () => { touched = true; if (sel.has(k)) sel.delete(k); else sel.add(k); paint(); } }, nm[k])));
  paint();
  line.addEventListener("input", () => {  // same rule as the server: names in the line, else everybody
    if (touched) return;
    const named = nm.map((n, k) => new RegExp("\\b" + n.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(line.value.toLowerCase()) ? k : -1).filter((k) => k >= 0);
    sel.clear(); for (const k of (named.length ? named : nm.map((_, k) => k))) sel.add(k); paint();
  });
  const go_ = el("button", { class: "primary", type: "submit" }, "↻ Redo this panel");
  const form = el("form", { onsubmit: async (e) => {
    e.preventDefault();
    const t = line.value.trim();
    if (!t) { line.focus(); toast("Write what happens in this panel"); return; }
    go_.disabled = true;
    const body = { line: t };
    if (p.chars.length) body.cast = [...sel].sort();
    await redo(p.id, i, body);
    closeOv("sheet");
  } },
  el("h2", { text: `Panel ${i + 1}` }),
  el("div", { class: "sub", text: "Change what happens, then draw only this panel again. The other 3 panels stay." }),
  el("label", { class: "label", text: "What happens (\"quotes\" = speech bubble)" }), line,
  p.chars.length ? el("div", {}, el("div", { class: "label", text: "Who is in this panel (only they get their reference pictures)" }), pick,
    el("div", { class: "hint", text: "Picked by the names in the line; \"she\"/\"he\" or nicknames are not seen, so set it here." })) : null,
  el("div", { class: "two" }, el("button", { class: "ghost", type: "button", onclick: () => closeOv("sheet") }, "Cancel"), go_));
  openSheet(form);
}
function namedChars(lines) {  // ready characters whose name is written in the lines
  const t = lines.join(" ").toLowerCase();
  return chars.filter((c) => c.status === "ready" && new RegExp("\\b" + c.name.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(t));
}
function noCharSheet(lines) {  // nobody picked: every panel would draw a different person
  return new Promise((resolve) => {
    const ready = chars.filter((c) => c.status === "ready");
    const sel = new Set(namedChars(lines).map((c) => c.slug).slice(0, 2));
    const pick = el("div", { class: "pick" });
    const paint = () => { for (const b of pick.children) b.classList.toggle("on", sel.has(b.dataset.slug)); };
    for (const c of ready) pick.append(el("button", { type: "button", "data-slug": c.slug, onclick: () => {
      if (sel.has(c.slug)) sel.delete(c.slug); else if (sel.size < 2) sel.add(c.slug); else toast("2 characters at most");
      paint(); } }, el("img", { src: thumbUrl(c.source_image), alt: "" }), c.name));
    paint();
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); closeOv("sheet"); } };
    const body = el("div", { class: "nochar" }, el("h2", { text: "No character picked" }),
      el("div", { class: "sub", text: "Without a character every panel draws a different person. " + (ready.length ? "Pick who is in this page:" : "Make a character first: open any picture and tap ★ Make character.") }),
      ready.length ? pick : null,
      el("div", { class: "two" },
        el("button", { class: "ghost", type: "button", onclick: () => finish({ go: true, chars: [] }) }, "Make without"),
        ready.length ? el("button", { class: "primary", type: "button", onclick: () => { if (!sel.size) { toast("Pick a character, or Make without"); return; } finish({ go: true, chars: [...sel] }); } }, "Use them") : null));
    openSheet(body);
    const obs = setInterval(() => { if ($("#sheet").hidden) { clearInterval(obs); if (!done) { done = true; resolve({ go: false }); } } }, 300);
  });
}
$("#pageform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const lines = lineIds.map((id) => $("#" + id).value.trim());
  const miss = lines.findIndex((x) => !x);
  if (miss >= 0) { toast(`Write panel ${miss + 1} first`); $("#" + lineIds[miss]).focus(); return; }
  const md = await api("GET", "/api/mode").catch(() => null);
  if (md && md.status && md.status.comfyui_manga !== "running") {
    toast("Drawing is stopped (LLM mode). Open 🎬 Director and tap LLM down first.", { err: true, action: "Open", onaction: () => go("director") });
    return;
  }
  let pick = [...pageSel];
  const busy = pick.filter((s) => charBySlug[s] && charBySlug[s].status !== "ready");
  if (busy.length) { toast(`${charBySlug[busy[0]].name} is still busy: wait a moment or unpick it`, { err: true }); return; }
  if (!pick.length) {
    const r = await noCharSheet(lines);
    if (!r.go) return;
    pick = r.chars;
    if (pick.length) { pageSel = new Set(pick); LS.set("manga-pagechars", pick); }
  }
  const b = $("#makepage");
  b.disabled = true; b.textContent = "Starting…";
  try {
    await api("POST", "/api/pages", { lines, chars: pick, bible: $("#lbible").value.trim() });
    toast("Page started: 4 panels, about 1 min");
    await loadPages();
    $("#pagelist").scrollIntoView({ behavior: "smooth" });
  } catch (err) { toast(err.message, { err: true }); }
  finally { b.disabled = false; b.textContent = "Make page"; }
});

$("#queue").addEventListener("click", async () => {
  const L = await api("GET", "/api/queue").catch(() => []);
  openSheet(el("div", {}, el("h2", { text: `Queue · ${L.length}` }),
    el("div", { class: "sub", text: "The GPU does one job at a time, top first." }),
    el("div", { class: "qlist" }, L.map((j, k) => el("div", { class: "qrow" + (j.status === "running" ? " on" : "") },
      el("span", { class: "qn", text: j.status === "running" ? "▶" : String(k + 1) }),
      el("span", { class: "qw", text: j.what }),
      el("span", { class: "qs", text: j.status === "running" ? (j.total ? `step ${j.progress}/${j.total}` : "loading…") : "waiting" }),
      el("button", { class: "btn small danger", onclick: async () => { await api("POST", `/api/jobs/${j.id}/cancel`).catch((e) => toast(e.message, { err: true })); closeOv("sheet"); refresh(); } }, "■")))),
    el("div", { class: "two" }, el("button", { class: "ghost", type: "button", onclick: () => closeOv("sheet") }, "Close"))));
});

// ---------- director: chat with the local LLM -> shot list -> Make page ----------
let dchatId = LS.get("manga-dchat", null), dmsgs = [], dmode = null, dpoll = null;
const dsel = new Set(LS.get("manga-dchars", []));
const dIds = ["d1", "d2", "d3", "d4", "dnotes", "dtext"];
const dDraft = LS.get("manga-ddraft", {});
for (const id of dIds) { const t = $("#" + id); t.value = dDraft[id] || ""; t.addEventListener("input", () => { dDraft[id] = t.value; LS.set("manga-ddraft", dDraft); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; }); }

function modeCard(m) {
  const box = $("#modecard");
  const st = m && m.status;
  let text, btn = null, cls = "";
  if (!m || !m.helper) { text = m && m.llm.state !== "off" ? `LLM ${m.llm.state}${m.llm.model ? " · " + m.llm.model : ""}` : "Local LLM is off. Start Local LLMs first (llm-up or the hub card)."; cls = m && m.llm.state !== "off" ? "" : "warn"; }
  else if (st && st.error) { text = "GPU switch not reachable: " + st.error; cls = "warn"; }
  else if (st.switching) { text = "Switching the GPU… (about 1 min)"; cls = "busy"; }
  else if (st.gameMode) { text = "Game mode is on: GPU busy."; cls = "warn"; }
  else if (st.llm !== "OFF") {
    const ls = m.llm.state;
    text = ls === "ready" ? `LLM ready (${m.llm.model}) · drawing stopped` : ls === "loading" ? "LLM loading the model… · drawing stopped" : "LLM on (model loads with the first message) · drawing stopped";
    btn = el("button", { class: "btn", onclick: () => setMode("draw") }, "LLM down · back to drawing");
  } else if (st.comfyui_manga === "running") {
    text = "Drawing mode: ComfyUI has the GPU. The Director needs the LLM.";
    btn = el("button", { class: "btn star", onclick: () => setMode("llm") }, "LLM up");
  } else { text = "Nothing on the GPU."; btn = el("button", { class: "btn", onclick: () => setMode("draw") }, "Start drawing"); }
  box.className = "modecard " + cls;
  box.replaceChildren(...[el("span", { class: "mtext", text }), btn].filter(Boolean));
  const waiting = st && (st.switching || (st.llm !== "OFF" && m.llm.state === "loading"));
  clearTimeout(dpoll);
  if (waiting && cur.view === "director") dpoll = setTimeout(() => refresh(), 3000);
}
async function setMode(mode) {
  try {
    if (mode === "llm" && queueN) { toast("Pictures are still being drawn: wait or stop them first", { err: true }); return; }
    await api("POST", "/api/mode", { mode });
    toast(mode === "llm" ? "Stopping drawing, starting the LLM (about 1 min)" : "Stopping the LLM, starting drawing (about 1 min)");
    refresh();
  } catch (e) { toast(e.message, { err: true }); }
}
async function loadDirector() {
  await loadCharList();
  dmode = await api("GET", "/api/mode").catch(() => null);
  modeCard(dmode);
  if (dchatId) {
    try { const d = await api("GET", `/api/director/chats/${dchatId}`); dmsgs = d.messages; }
    catch (e) { if (/no such/.test(e.message)) { dchatId = null; LS.set("manga-dchat", null); dmsgs = []; } else throw e; }
  } else dmsgs = [];
  const ready = chars.filter((c) => c.status === "ready");
  $("#dchars").replaceChildren(...(ready.length ? ready.map((c) => el("button", { type: "button", class: "chip" + (dsel.has(c.slug) ? " on" : ""), onclick: () => {
    if (dsel.has(c.slug)) dsel.delete(c.slug); else dsel.add(c.slug); LS.set("manga-dchars", [...dsel]); loadDirector(); } }, c.name)) : [el("span", { class: "sub", text: "No characters yet (★ on any picture)." })]));
  const first = !dmsgs.length;
  $("#dfirst").hidden = !first;
  $("#dtext").hidden = first;
  renderDirector();
}
function renderDirector() {
  const box = $("#dlog");
  const ae = document.activeElement;
  if (ae && box.contains(ae) && ae.tagName === "TEXTAREA") return;  // editing a field: no repaint
  const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  const kids = [el("div", { class: "dtools" },
    el("button", { class: "btn small", onclick: newDirector }, "+ New"),
    el("button", { class: "btn small", onclick: skillsSheet }, "Director skills"))];
  if (!dmsgs.length) kids.push(el("div", { class: "empty", text: "Write your panel lines below. The Director turns them into a shot list (shots, angles, poses, place, light) you can change by chatting, then sends it to Make page." }));
  const lastSl = [...dmsgs].reverse().find((m) => m.shotlist);
  for (const m of dmsgs) {
    if (m.role === "user") {
      const cut = m.content.indexOf("\n\nI edited the shot list by hand");
      kids.push(el("div", { class: "msg" }, el("div", { class: "me", text: cut >= 0 ? m.content.slice(0, cut) + "\n(+ my hand edits)" : m.content })));
      continue;
    }
    const node = el("div", { class: "dans" });
    if (m.status === "working") node.append(el("div", { class: "st", text: m.content ? `writing… ${m.content.length} characters` : (dmode && dmode.llm.state !== "ready" ? "loading the model, then writing…" : "thinking…") }), el("div", { class: "bar ind" }, el("i")));
    else if (m.status === "failed") node.append(el("div", { class: "st err", text: "failed: " + (m.error || "") }), el("button", { class: "btn", onclick: () => retryDirector(m) }, "↻ Try again"));
    else if (m.shotlist) {
      const prose = m.content.replace(/```(?:json)?[\s\S]*?```/g, "").replace(/\{[\s\S]*\}/, "").trim();
      if (prose) node.append(el("div", { class: "dtext", text: prose }));
      node.append(shotCard(m, m === lastSl));
    }
    else node.append(el("div", { class: "dtext", text: m.content }), m.error ? el("div", { class: "st err", text: m.error }) : null);
    kids.push(node);
  }
  box.replaceChildren(...kids);
  if (stick) box.scrollTop = box.scrollHeight;
}
const dEdited = {};
function shotCard(m, latest) {
  const sl = m.shotlist;
  const save = () => { dEdited[m.id] = true; clearTimeout(save.t); save.t = setTimeout(() => api("POST", `/api/director/messages/${m.id}/shotlist`, { shotlist: sl }).catch((e) => toast(e.message, { err: true })), 600); };
  const field = (obj, k, label, rows) => {
    const t = el("textarea", { "data-k": k });
    t.value = Array.isArray(obj[k]) ? obj[k].join(", ") : (obj[k] || "");
    t.rows = Math.max(rows || 1, Math.ceil(t.value.length / 34));  // ~34 characters a line at phone width
    t.addEventListener("input", () => { obj[k] = k === "characters" ? t.value.split(",").map((x) => x.trim()).filter(Boolean) : t.value; save(); });
    return el("label", { class: "fld" }, el("span", { text: label }), t);
  };
  const b = sl.bible || (sl.bible = {});
  const body = el("div", { class: "shots" },
    el("h3", { text: sl.title || "Shot list" }),
    el("details", { class: "bible", open: latest || undefined }, el("summary", { text: "Scene bible (same in every panel)" }),
      field(b, "location", "Place", 2), field(b, "time_light", "Time + light", 2), field(b, "props", "Props", 2), field(b, "wardrobe", "Clothes", 2), field(b, "mood", "Mood")),
    ...(sl.panels || []).map((p, i) => el("details", { class: "shot", open: latest || undefined },
      el("summary", {}, el("b", { text: `Panel ${i + 1}` }), ` · ${p.shot || ""}${p.angle ? ", " + p.angle : ""}`),
      field(p, "shot", "Shot"), field(p, "angle", "Angle"), field(p, "characters", "Who (exact names)"), field(p, "action", "Action + pose", 2),
      field(p, "expression", "Face", 2), field(p, "setting", "Background", 2), field(p, "light", "Light"), field(p, "effects", "Manga effects"), field(p, "dialogue", "Dialogue"))),
    (sl.review || []).length ? el("div", { class: "hint", text: "Check when drawn: " + sl.review.join(" · ") }) : null,
    el("button", { class: "primary", type: "button", onclick: () => toPage(m) }, "📖 Send to Make page"));
  return body;
}
async function toPage(m) {
  try {
    await api("POST", `/api/director/messages/${m.id}/shotlist`, { shotlist: m.shotlist });
    const d = await api("POST", `/api/director/messages/${m.id}/page`);
    d.lines.slice(0, 4).forEach((t, i) => { $("#" + lineIds[i]).value = t; pageDraft[i] = t; });
    LS.set("manga-pagelines", pageDraft);
    $("#lbible").value = d.bible; LS.set("manga-pagebible", d.bible);
    const names = new Set((m.shotlist.panels || []).flatMap((p) => p.characters || []).map((n) => n.toLowerCase()));
    const pick = chars.filter((c) => c.status === "ready" && names.has(c.name.toLowerCase())).map((c) => c.slug).slice(0, 2);
    if (pick.length) { pageSel = new Set(pick); LS.set("manga-pagechars", pick); }
    go("page");
    const llmOn = dmode && dmode.status && dmode.status.llm !== "OFF";
    toast(llmOn ? "Filled in. The LLM still has the GPU: tap LLM down in Director before Make page." : "Filled in from the Director. Check it, then Make page.", { ms: 7000 });
  } catch (e) { toast(e.message, { err: true }); }
}
async function newDirector() { dchatId = null; LS.set("manga-dchat", null); dmsgs = []; for (const k of Object.keys(dEdited)) delete dEdited[k]; loadDirector(); }
async function retryDirector(m) {
  const u = [...dmsgs].reverse().find((x) => x.role === "user" && x.id < m.id);
  if (u) await dsend(u.content);
}
async function dsend(text) {
  if (!dchatId) { const c = await api("POST", "/api/director/chats"); dchatId = c.id; LS.set("manga-dchat", c.id); }
  await api("POST", `/api/director/chats/${dchatId}/messages`, { text, chars: [...dsel] });
}
$("#dcomposer").addEventListener("submit", async (e) => {
  e.preventDefault();
  let text;
  if (!dmsgs.length) {
    const lines = ["d1", "d2", "d3", "d4"].map((id) => $("#" + id).value.trim());
    if (lines.filter(Boolean).length < 1) { toast("Write at least panel 1"); $("#d1").focus(); return; }
    const names = chars.filter((c) => dsel.has(c.slug)).map((c) => c.name);
    text = "Panel lines:\n" + lines.map((t, i) => `${i + 1}. ${t || "(you decide)"}`).join("\n") +
      ($("#dnotes").value.trim() ? `\nNotes: ${$("#dnotes").value.trim()}` : "") + (names.length ? `\nCharacters in this page: ${names.join(", ")}` : "");
  } else {
    text = $("#dtext").value.trim();
    if (!text) { $("#dtext").focus(); return; }
    const last = [...dmsgs].reverse().find((m) => m.shotlist);
    if (last && dEdited[last.id]) { text += "\n\nI edited the shot list by hand; start from my version:\n```json\n" + JSON.stringify(last.shotlist) + "\n```"; delete dEdited[last.id]; }
  }
  const b = $("#dsend"); b.disabled = true;
  try {
    await dsend(text);
    for (const id of dIds) { if (id !== "dnotes" || dmsgs.length) { $("#" + id).value = ""; dDraft[id] = ""; } }
    LS.set("manga-ddraft", dDraft);
    refresh();
  } catch (err) { toast(err.message, { err: true }); }
  finally { b.disabled = false; }
});
async function skillsSheet() {
  const d = await api("GET", "/api/director/skills");
  const t = el("textarea", { rows: "16", class: "mono" }); t.value = d.text;
  openSheet(el("div", {}, el("h2", { text: "Director skills" }),
    el("div", { class: "sub", text: "The Director's instructions (system prompt), used on every message." + (d.custom ? " Your edited version." : " Default version.") }), t,
    el("div", { class: "two" },
      el("button", { class: "ghost", type: "button", onclick: async () => { await api("PUT", "/api/director/skills", { text: null }); closeOv("sheet"); toast("Back to the default skills"); } }, "Reset"),
      el("button", { class: "primary", type: "button", onclick: async () => { await api("PUT", "/api/director/skills", { text: t.value }); closeOv("sheet"); toast("Skills saved"); } }, "Save"))));
}

// ---------- drawer ----------
async function loadDrawer() {
  const [list, g] = await Promise.all([api("GET", "/api/chats"), api("GET", "/api/gpu").catch(() => null)]);
  $("#chatlist").replaceChildren(...list.map((c) => el("button", { class: c.id === chatId ? "on" : "", onclick: () => { setChat(c.id); go("chat"); } },
    c.title || `New chat`)));
  $("#gpu").textContent = g ? `GPU ${g.util}% · ${g.temp} °C · ${(g.used / 1024).toFixed(1)}/${(g.total / 1024).toFixed(1)} GB` : "";
  if (G.total) $("#gcount").textContent = G.total;
}

// ---------- start ----------
const start = (location.hash || "#chat").slice(1);
history.replaceState({ view: VIEWS[start] && start !== "char" ? start : "chat", ov: [] }, "", location.hash || "#chat");
paintChips();
autosize();
apply(history.state);
loadCharList().catch(() => {});
syncLoop();
