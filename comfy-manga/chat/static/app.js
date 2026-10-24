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
const imgUrl = (id) => `/api/images/${id}`;
const thumbUrl = (id, s) => `/api/images/${id}/thumb${s ? "?s=" + s : ""}`;

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
  if (vv.offsetTop) window.scrollTo(0, 0);
}
if (window.visualViewport) {
  visualViewport.addEventListener("resize", fitViewport);
  visualViewport.addEventListener("scroll", fitViewport);
  fitViewport();
}

// ---------- navigation + back button ----------
const VIEWS = { chat: "Chat", gallery: "Gallery", chars: "Characters", char: "Character", page: "Make page" };
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
      if (d.comfy !== "up") $("#banner").textContent = "Picture engine (ComfyUI) is starting — jobs wait and continue by themselves.";
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
      el("a", { class: "btn", href: imgUrl(j.image_id) + "?dl=1", download: "" }, "⬇ Save"),
      el("button", { class: "btn", onclick: () => again_(m.id) }, "↻ Again"),
      el("button", { class: "btn star", onclick: () => makeCharSheet(j.image_id) }, "★ Make character")));
  } else {
    const ar = m.shape === "wide" ? 1.75 : m.shape === "square" ? 1 : 0.68;
    if (j && (j.status === "queued" || j.status === "running")) res.append(el("div", { class: "ph", style: `--ar:${ar}` }, "✎"));
    res.append(jobStatus(j));
    const acts = el("div", { class: "acts" });
    if (j && (j.status === "queued" || j.status === "running")) acts.append(el("button", { class: "btn danger", onclick: () => stopJob(j.id) }, "■ Stop"));
    if (j && (j.status === "failed" || j.status === "cancelled")) acts.append(el("button", { class: "btn", onclick: () => again_(m.id) }, "↻ Try again"));
    if (acts.childNodes.length) res.append(acts);
  }
  return el("div", { class: "msg", "data-id": m.id }, el("div", { class: "me" }, m.text, who), res);
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
async function again_(mid) {
  try { await api("POST", `/api/messages/${mid}/again`); log.scrollTop = log.scrollHeight; refresh(); }
  catch (e) { toast(e.message, { err: true }); }
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
  $("#vdl").href = imgUrl(it.id) + "?dl=1";
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
$("#sheet").addEventListener("click", (e) => { if (e.target.id === "sheet") closeOv("sheet"); });

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
  if (c.status === "building") return `making pictures · ${c.made} / ${c.planned}`;
  if (c.status === "checking") return "checking faces…";
  if (c.status === "ready") return `ready · ${c.refs.length} pictures`;
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
  list.replaceChildren(...chars.map((c) => {
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
        busyC ? el("button", { class: "btn danger", onclick: () => api("POST", `/api/characters/${c.id}/cancel`).then(refresh) }, "■ Stop") : null,
        c.status === "failed" || c.status === "cancelled" ? el("button", { class: "btn", onclick: () => api("POST", `/api/characters/${c.id}/retry`).then(refresh).catch((e) => toast(e.message, { err: true })) }, "↻ Retry") : null));
  }));
}
function useInChat(c) { state.chars = [c.slug]; LS.set("manga-chars", state.chars); paintChips(); go("chat"); }
function pageWith(c) { pageSel = new Set([c.slug]); go("page"); }
async function loadChar(id) {
  const c = await api("GET", `/api/characters/${id}`);
  charCache[id] = c;
  $("#title").textContent = c.name;
  const box = $("#chardetail");
  const refs = c.refs.map((i) => ({ id: i }));
  const dropped = (c.dropped || []).map((i) => ({ id: i }));
  const all = (c.status === "ready" ? refs : (c.all || []).map((i) => ({ id: i })));
  const gridOf = (L, cls) => el("div", { class: "refs " + (cls || "") }, L.map((it, k) => el("button", { onclick: () => openViewer(L, k) },
    el("img", { src: thumbUrl(it.id), loading: "lazy", alt: "" }))));
  box.replaceChildren(el("div", { class: "card" },
    el("div", { class: "crow" }, el("img", { src: thumbUrl(c.source_image), alt: "", onclick: () => openViewer([{ id: c.source_image }], 0) }),
      el("div", { class: "grow" }, el("h3", { text: c.name }), el("div", { class: "sub" + (c.status === "failed" ? " err" : ""), text: charLine(c) }))),
    c.status === "ready" ? el("div", { class: "acts", style: "padding:10px 0 0" },
      el("button", { class: "btn", onclick: () => useInChat(c) }, "💬 Use in chat"),
      el("button", { class: "btn", onclick: () => pageWith(c) }, "📖 Make page")) : null,
    all.length ? gridOf(all) : el("div", { class: "empty", text: "Pictures appear here as they are made." }),
    dropped.length ? el("div", {}, el("div", { class: "label", text: `Not kept (${dropped.length}, looked less alike)` }), gridOf(dropped, "dropped")) : null));
}

// ---------- pages ----------
let pageSel = new Set(LS.get("manga-pagechars", []));
const lineIds = ["l1", "l2", "l3", "l4"];
const pageDraft = LS.get("manga-pagelines", ["", "", "", ""]);
lineIds.forEach((id, i) => { const t = $("#" + id); t.value = pageDraft[i] || ""; t.addEventListener("input", () => { pageDraft[i] = t.value; LS.set("manga-pagelines", pageDraft); }); });
async function loadPages() {
  await loadCharList();
  const ready = chars.filter((c) => c.status === "ready");
  for (const s of [...pageSel]) if (!charBySlug[s] || charBySlug[s].status !== "ready") pageSel.delete(s);
  const pc = $("#pagechars");
  pc.replaceChildren(...(ready.length ? ready.map((c) => el("button", { type: "button", class: "chip" + (pageSel.has(c.slug) ? " on" : ""), onclick: () => {
    if (pageSel.has(c.slug)) pageSel.delete(c.slug); else if (pageSel.size < 2) pageSel.add(c.slug); else toast("2 characters at most");
    LS.set("manga-pagechars", [...pageSel]); loadPages();
  } }, c.name)) : [el("span", { class: "sub", text: "No characters yet: make one from any picture (★). Without one the page uses no reference." })]));
  const pages = await api("GET", "/api/pages");
  $("#pagelist").replaceChildren(...pages.map(pageCard));
}
function pageCard(p) {
  const working = p.status === "working";
  const panels = p.panels.map((x, i) => {
    const j = x.job;
    const running = j && (j.status === "queued" || j.status === "running");
    const pct = j && j.total ? Math.round(100 * j.progress / j.total) : 0;
    return el("div", { class: "panel" },
      el("div", { class: "thumb" }, x.image_id ? el("img", { src: thumbUrl(x.image_id), alt: "", onclick: () => openViewer(p.panels.filter((q) => q.image_id).map((q) => ({ id: q.image_id })), p.panels.filter((q) => q.image_id).findIndex((q) => q.image_id === x.image_id)) }) : null,
        running ? el("div", { class: "bar" + (j.status === "running" && j.total ? "" : " ind") }, el("i", { style: `width:${pct}%` })) : null),
      el("div", { class: "n", text: `${i + 1}` + (j && j.status === "failed" ? " · failed" : running ? (j.status === "queued" ? " · waiting" : " · drawing") : "") }),
      el("button", { class: "btn", disabled: running || undefined, onclick: () => redo(p.id, i) }, "↻ Redo"));
  });
  return el("div", { class: "card" },
    el("h3", { text: `Page ${p.id}` + (p.chars.length ? " · " + p.chars.map((s) => (charBySlug[s] || { name: s }).name).join(", ") : "") }),
    el("div", { class: "sub" + (p.error ? " err" : ""), text: working ? "drawing the 4 panels…" : (p.error || `done · prompts by ${p.writer}`) }),
    p.image_id ? el("img", { class: "pagepic", src: thumbUrl(p.image_id, "m"), alt: "page", onclick: () => openViewer([{ id: p.image_id, source: "page" }], 0) }) : null,
    el("div", { class: "panels" }, panels),
    p.image_id ? el("div", { class: "acts", style: "padding:10px 0 0" }, el("a", { class: "btn", href: imgUrl(p.image_id) + "?dl=1", download: "" }, "⬇ Download PNG")) : null);
}
async function redo(pid, i) {
  try { await api("POST", `/api/pages/${pid}/panels/${i}/redo`); refresh(); } catch (e) { toast(e.message, { err: true }); }
}
$("#pageform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const lines = lineIds.map((id) => $("#" + id).value.trim());
  const miss = lines.findIndex((x) => !x);
  if (miss >= 0) { toast(`Write panel ${miss + 1} first`); $("#" + lineIds[miss]).focus(); return; }
  const b = $("#makepage");
  b.disabled = true; b.textContent = "Starting…";
  try {
    await api("POST", "/api/pages", { lines, chars: [...pageSel] });
    toast("Page started: 4 panels, about 1 min");
    await loadPages();
    $("#pagelist").scrollIntoView({ behavior: "smooth" });
  } catch (err) { toast(err.message, { err: true }); }
  finally { b.disabled = false; b.textContent = "Make page"; }
});

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
