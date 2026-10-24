const feed = document.getElementById("feed");
const estline = document.getElementById("estline");
const promptBox = document.getElementById("prompt");
const shapeBox = document.getElementById("shape");

const SHAPES = { wide: "1344x768", square: "1024x1024", tall: "832x1216" };
const EST = 16;  // warm seconds on this PC
const state = { shape: "tall" };

function updateHint() {
  estline.textContent = `Manga · ${SHAPES[state.shape]} · ~${EST} s`;
}
[...shapeBox.querySelectorAll("button")].forEach((b) => b.classList.toggle("on", b.dataset.v === state.shape));
shapeBox.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  state.shape = b.dataset.v;
  [...shapeBox.querySelectorAll("button")].forEach((x) => x.classList.toggle("on", x === b));
  updateHint();
});
updateHint();

promptBox.addEventListener("input", () => {
  promptBox.style.height = "auto";
  promptBox.style.height = Math.min(promptBox.scrollHeight, 160) + "px";
});
promptBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
document.getElementById("send").addEventListener("click", send);

async function send() {
  const text = promptBox.value.trim();
  if (!text) return;
  const fd = new FormData();
  fd.append("prompt", text);
  fd.append("shape", state.shape);
  fd.append("seed", "0");
  promptBox.value = ""; promptBox.style.height = "auto";
  await fetch("/api/messages", { method: "POST", body: fd });
  poll();
}

function fileUrl(name) { return "/api/files/" + name.split("/").map(encodeURIComponent).join("/"); }

function action(label, cls, fn) {
  const b = document.createElement("button");
  b.className = "btn " + (cls || "");
  b.textContent = label;
  b.addEventListener("click", fn);
  return b;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderMsg(m) {
  const wrap = document.createElement("div");
  wrap.className = "msg";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = m.prompt;
  wrap.appendChild(bubble);

  let params = {};
  try { params = JSON.parse(m.params || "{}"); } catch (e) { params = {}; }

  const meta = document.createElement("div");
  meta.className = "meta";
  const secs = m.elapsed ? ` · ${Math.round(m.elapsed)} s` : "";
  meta.textContent = `Anima Manga · ${params.width || "?"}x${params.height || "?"}${secs}`;
  wrap.appendChild(meta);

  const result = document.createElement("div");
  result.className = "result";
  wrap.appendChild(result);

  if (m.status === "queued") {
    result.innerHTML = '<div class="status">waiting for the GPU…</div>';
  } else if (m.status === "running") {
    const p = document.createElement("div");
    p.className = "progress";
    const i = document.createElement("i");
    if (m.total && m.total > 0) i.style.width = Math.round((m.progress / m.total) * 100) + "%";
    else p.classList.add("indeterminate");
    p.appendChild(i);
    const st = document.createElement("div");
    st.className = "status run";
    let left = "";
    if (m.total && m.progress) {
      const rem = Math.max(0, Math.round((params.est_seconds || 16) * (1 - m.progress / m.total)));
      left = rem >= 60 ? ` · ~${Math.round(rem / 60)} min left` : ` · ~${rem} s left`;
    }
    st.textContent = (m.total ? `step ${m.progress}/${m.total}` : "working") + left;
    result.appendChild(p);
    result.appendChild(st);
    const actions = document.createElement("div");
    actions.className = "actions";
    actions.appendChild(action("Stop", "danger", () =>
      fetch(`/api/messages/${m.id}/cancel`, { method: "POST" }).then(poll)));
    result.appendChild(actions);
  } else if (m.status === "done") {
    const el = document.createElement("img");
    el.src = fileUrl(m.filename);
    el.title = "tap to enlarge";
    el.addEventListener("click", () => openLightbox(el.src));
    result.appendChild(el);
    const actions = document.createElement("div");
    actions.className = "actions";
    const a = document.createElement("a");
    a.className = "btn"; a.textContent = "Download"; a.href = fileUrl(m.filename);
    a.download = ""; a.target = "_blank";
    actions.appendChild(a);
    actions.appendChild(action("New seed", "", () => retry(m.id, "new")));
    actions.appendChild(action("Same seed", "", () => retry(m.id, "same")));
    result.appendChild(actions);
  } else if (m.status === "failed") {
    result.innerHTML = `<div class="status err">failed: ${escapeHtml(m.error || "unknown error")}</div>`;
    const actions = document.createElement("div");
    actions.className = "actions";
    actions.appendChild(action("Try again", "", () => retry(m.id, "new")));
    result.appendChild(actions);
  } else if (m.status === "cancelled") {
    result.innerHTML = '<div class="status">cancelled</div>';
  }
  return wrap;
}

function retry(id, mode) {
  const fd = new FormData();
  fd.append("seed_mode", mode);
  return fetch(`/api/messages/${id}/again`, { method: "POST", body: fd }).then(poll);
}

// Lightbox: tap a result to see it full-screen; × / backdrop / Esc closes.
const lb = document.getElementById("lightbox");
const lbImg = document.getElementById("lightbox-img");
function openLightbox(src) {
  lbImg.src = src;
  lb.hidden = false;
  document.body.classList.add("noscroll");
}
function closeLightbox() {
  lb.hidden = true;
  lbImg.src = "";
  document.body.classList.remove("noscroll");
}
lb.addEventListener("click", (e) => {
  if (e.target === lb || e.target.id === "lightbox-close") closeLightbox();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !lb.hidden) closeLightbox();
});

let lastFeed = "";
async function poll() {
  try {
    const data = await (await fetch("/api/feed")).json();
    busy = data.some((m) => m.status === "queued" || m.status === "running");
    const snap = JSON.stringify(data);
    if (snap === lastFeed) return;
    lastFeed = snap;
    const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 120;
    feed.innerHTML = "";
    for (const m of data) feed.appendChild(renderMsg(m));
    if (nearBottom) feed.scrollTop = feed.scrollHeight;
  } catch (e) { /* server restarting */ }
}

let busy = false;
async function gpu() {
  try {
    const r = await fetch("/api/gpu");
    if (r.ok) {
      const d = await r.json();
      document.getElementById("gpu").textContent =
        `GPU ${d.name} · ${d.util}% · ${d.temp} °C · ${(d.used / 1024).toFixed(1)}/${(d.total / 1024).toFixed(1)} GB`;
    }
  } catch (e) { /* ignore */ }
  setTimeout(gpu, busy ? 2500 : 10000);
}

poll();
gpu();
setInterval(poll, 2000);
