// Character studio: grid -> keep -> more like this / inpaint -> save -> variation set (2026-10-24)
const $ = (id) => document.getElementById(id);
const AOI = "1girl, solo, aoi, 17 years old, short asymmetric black bob, one long strand over right eye, " +
  "hair over one eye, sharp narrow eyes, thin eyebrows, mole under left eye, slim, high collar, dark school blazer, " +
  "white piping, loose red ribbon, red necktie, monochrome, greyscale, manga, clean lineart, ink, screentone, " +
  "upper body, looking at viewer, simple background, white background";
const PRESETS = {
  aoi: { prompt: AOI, traits: "17-year-old girl, short asymmetric black bob with one long strand over her right eye, " +
    "sharp narrow eyes, thin eyebrows, small beauty mark under her left eye, high-collar dark school blazer with white " +
    "piping, loose red ribbon tie" },
  haze: { prompt: "1girl, solo, haze (deadlock), dark-skinned female, very dark skin, black hair, messy hair bun, " +
    "black eye mask, glowing eyes, orange shirt, military shirt, short sleeves, breast pockets, black neckerchief, " +
    "black corset, knives on belt, long black gloves, black pants, jodhpurs, knee boots, serious, adult, monochrome, " +
    "greyscale, manga, clean lineart, ink, screentone, cowboy shot, looking at viewer, simple background, white background",
    traits: "dark-skinned adult woman, black messy hair bun, black mask band across her eyes with glowing eyes, " +
      "short-sleeve military shirt with breast pockets and a black neckerchief, black corset belt with throwing knives, " +
      "long black gloves, black jodhpur trousers" },
  rem: { prompt: "solo, rem (deadlock), no humans, small furry creature, black fur, fluffy, large pointy ears, " +
    "big round white eyes, no pupils, small black beak, long thin tail, tail tuft, blue nightcap, quilted pajama coat, " +
    "wavy pattern, claws, holding pillow, cute, monochrome, greyscale, manga, clean lineart, ink, screentone, full body, " +
    "looking at viewer, simple background, white background",
    traits: "small child-sized black furry creature, large pointy ears, big round blank white eyes, small black beak, " +
      "long thin tail with a fur tuft, nightcap and quilted pajama coat with a wavy pattern" },
};
const KINDS = { t2i: "Grid", i2i: "More like this", inpaint: "Inpaint", var: "Variations" };

let S = { jobs: [], kept: [], characters: [], models: {} };
let sel = null;   // selected kept ref
let snap = "";

function fileUrl(name) { return "/api/files/" + name.split("/").map(encodeURIComponent).join("/"); }
function refUrl(ref) { return "/api/studio/file/" + ref.split("/").map(encodeURIComponent).join("/"); }
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function toast(msg) {
  const t = $("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 3500);
}
async function post(url, data, file) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(data)) fd.append(k, v);
  if (file) fd.append(file.name, file.blob, "mask.png");
  const r = await fetch(url, { method: "POST", body: fd });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { toast(j.detail || `error ${r.status}`); throw new Error(j.detail); }
  return j;
}

// ---------- 1. prompt ----------
const cprompt = $("cprompt");
try { cprompt.value = localStorage.getItem("studio.prompt") || AOI; } catch (e) { cprompt.value = AOI; }
cprompt.addEventListener("input", () => { try { localStorage.setItem("studio.prompt", cprompt.value); } catch (e) {} });
let preset = null;
try { preset = localStorage.getItem("studio.preset"); } catch (e) {}
function presetFor(prompt) {
  return Object.keys(PRESETS).find((k) => PRESETS[k].prompt === prompt) || null;
}
function renderPresets() {
  const box = $("presets");
  box.innerHTML = "";
  for (const k of Object.keys(PRESETS)) {
    const b = el("button", k === presetFor(cprompt.value) ? "on" : "", k[0].toUpperCase() + k.slice(1));
    b.addEventListener("click", () => {
      cprompt.value = PRESETS[k].prompt;
      try { localStorage.setItem("studio.prompt", cprompt.value); } catch (e) {}
      renderPresets();
    });
    box.appendChild(b);
  }
}
renderPresets();
cprompt.addEventListener("input", renderPresets);
$("gen").addEventListener("click", async () => {
  await post("/api/studio/grid", { prompt: cprompt.value, count: 16 });
  toast("16 pictures queued");
  refresh();
});

// ---------- tiles ----------
function tile(src, opts = {}) {
  const t = el("div", "tile");
  if (src) {
    const img = el("img"); img.loading = "lazy"; img.src = src; img.alt = "";
    t.appendChild(img);
    const z = el("button", "zoom", "⤢"); z.title = "enlarge";
    z.addEventListener("click", (e) => { e.stopPropagation(); openLightbox(src); });
    t.appendChild(z);
  }
  if (opts.label) t.appendChild(el("span", "lbl", opts.label));
  if (opts.onTap) t.addEventListener("click", opts.onTap);
  return t;
}

function jobTile(j) {
  if (j.status === "done") {
    const t = tile(refUrl(j.filename), {
      label: j.kind === "var" ? j.params.label : `seed ${j.params.seed}`,
      onTap: async () => {
        if (j.kept) { select(j.kept); return; }
        const r = await post("/api/studio/keep", { job: j.id });
        toast("kept"); await refresh(); select(r.ref);
      },
    });
    if (j.kept) { t.classList.add("kept"); t.appendChild(el("span", "star", "★ kept")); }
    return t;
  }
  const t = tile(null);
  const w = el("div", "wait");
  if (j.status === "running") {
    w.appendChild(el("div", null, j.total ? `step ${j.progress}/${j.total}` : "starting…"));
    const b = el("div", "bar"); const i = el("i");
    i.style.width = j.total ? Math.round((j.progress / j.total) * 100) + "%" : "5%";
    b.appendChild(i); w.appendChild(b);
  } else if (j.status === "failed") {
    w.textContent = "failed: " + (j.error || "");
    w.style.color = "var(--err)";
  } else {
    w.textContent = j.status === "queued" ? "waiting…" : j.status;
  }
  t.appendChild(w);
  return t;
}

function renderBatches() {
  const box = $("batches");
  const groups = new Map();
  for (const j of S.jobs) {
    if (j.kind === "frame" || j.kind === "var") continue;  // frames show under their line, variation sets under the character
    if (!groups.has(j.batch)) groups.set(j.batch, []);
    groups.get(j.batch).push(j);
  }
  const list = [...groups.entries()].reverse().slice(0, 6);
  box.innerHTML = "";
  if (!list.length) { box.appendChild(el("div", "muted small", "No pictures yet. Press Make 16.")); return; }
  for (const [batch, js] of list) {
    const sec = el("div", "batch");
    const head = el("div", "batch-head");
    const k = js[0].kind;
    head.appendChild(el("b", null, KINDS[k] + (k === "var" ? " · " + (S.models[js[0].params.model] || {}).label : "")));
    const done = js.filter((j) => j.status === "done");
    const open = js.filter((j) => j.status === "queued" || j.status === "running").length;
    let txt = `${done.length}/${js.length}`;
    if (done.length) txt += ` · ~${Math.round(done.reduce((a, j) => a + j.elapsed, 0) / done.length)} s each`;
    if (k === "i2i" || k === "inpaint") txt += ` · strength ${js[0].params.denoise}`;
    head.appendChild(el("span", null, txt));
    if (open) {
      const stop = el("button", "btn small danger", "Stop");
      stop.addEventListener("click", () => post("/api/studio/cancel", { batch }).then(refresh));
      head.appendChild(stop);
    }
    sec.appendChild(head);
    const g = el("div", "grid");
    for (const j of js) g.appendChild(jobTile(j));
    sec.appendChild(g);
    box.appendChild(sec);
  }
}

// ---------- 3. kept ----------
function renderKept() {
  const box = $("kept");
  box.innerHTML = "";
  for (const k of [...S.kept].reverse()) {
    const t = tile(refUrl(k.ref), { onTap: () => select(k.ref) });
    if (k.ref === sel) t.classList.add("sel");
    box.appendChild(t);
  }
}

// ---------- 4. work ----------
const stage = $("stage"), wimg = $("wimg"), mask = $("wmask"), mctx = mask.getContext("2d");
let tab = "more", erasing = false;

function select(ref) {
  const k = S.kept.find((x) => x.ref === ref);
  if (!k) return;
  sel = ref;
  $("work").hidden = false;
  wimg.src = refUrl(ref);
  mctx.clearRect(0, 0, mask.width, mask.height);
  $("mprompt").value = k.prompt || cprompt.value;
  $("iprompt").value = k.prompt || cprompt.value;
  const pk = presetFor(k.prompt) || presetFor((k.parent && k.parent.prompt) || "");
  $("cname").value = pk || "";
  $("ctraits").value = pk ? PRESETS[pk].traits : "";
  const bits = [`seed ${k.seed}`, k.kind === "t2i" ? "from the grid" : `${KINDS[k.kind]} (strength ${k.denoise})`];
  if (k.parent) bits.push(`from seed ${k.parent.seed}`);
  $("wmeta").textContent = bits.join(" · ");
  renderKept();
  $("work").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  tab = b.dataset.t;
  [...$("tabs").children].forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(".pane").forEach((p) => { p.hidden = p.dataset.p !== tab; });
  stage.classList.toggle("painting", tab === "paint");
});

$("denoise").addEventListener("input", (e) => { $("dval").textContent = (+e.target.value).toFixed(2); });
$("idenoise").addEventListener("input", (e) => { $("ival").textContent = (+e.target.value).toFixed(2); });

$("more").addEventListener("click", async () => {
  await post("/api/studio/more", { src: sel, prompt: $("mprompt").value, denoise: $("denoise").value, count: 4 });
  toast("4 variations queued"); refresh();
  $("batches").scrollIntoView({ behavior: "smooth" });
});

// mask painting (canvas is 896x1152 = picture size; red marks = repaint)
let drawing = false, last = null;
function pos(e) {
  const r = mask.getBoundingClientRect();
  return { x: (e.clientX - r.left) * (mask.width / r.width), y: (e.clientY - r.top) * (mask.height / r.height) };
}
function stroke(p) {
  const size = +$("brush").value * (mask.width / 448);
  mctx.globalCompositeOperation = erasing ? "destination-out" : "source-over";
  mctx.strokeStyle = mctx.fillStyle = "#ff2a2a";
  mctx.lineWidth = size; mctx.lineCap = mctx.lineJoin = "round";
  mctx.beginPath();
  if (last) { mctx.moveTo(last.x, last.y); mctx.lineTo(p.x, p.y); mctx.stroke(); }
  else { mctx.arc(p.x, p.y, size / 2, 0, Math.PI * 2); mctx.fill(); }
  last = p;
}
mask.addEventListener("pointerdown", (e) => { drawing = true; last = null; mask.setPointerCapture(e.pointerId); stroke(pos(e)); });
mask.addEventListener("pointermove", (e) => { if (drawing) stroke(pos(e)); });
["pointerup", "pointercancel"].forEach((n) => mask.addEventListener(n, () => { drawing = false; last = null; }));
$("erase").addEventListener("click", () => { erasing = !erasing; $("erase").classList.toggle("on", erasing); });
$("clearm").addEventListener("click", () => mctx.clearRect(0, 0, mask.width, mask.height));

function maskBlob() {
  const src = mctx.getImageData(0, 0, mask.width, mask.height);
  const out = document.createElement("canvas");
  out.width = mask.width; out.height = mask.height;
  const o = out.getContext("2d");
  const d = o.createImageData(mask.width, mask.height);
  let painted = 0;
  for (let i = 0; i < src.data.length; i += 4) {
    const v = src.data[i + 3] > 20 ? 255 : 0;
    painted += v ? 1 : 0;
    d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255;
  }
  o.putImageData(d, 0, 0);
  return new Promise((res) => out.toBlob((b) => res({ blob: b, painted })));
}
$("inpaint").addEventListener("click", async () => {
  const m = await maskBlob();
  if (!m.painted) { toast("paint the area first"); return; }
  await post("/api/studio/inpaint", { src: sel, prompt: $("iprompt").value, denoise: $("idenoise").value, count: 2 },
    { name: "mask", blob: m.blob });
  toast("inpaint queued"); refresh();
  $("batches").scrollIntoView({ behavior: "smooth" });
});

$("save").addEventListener("click", async () => {
  const r = await post("/api/studio/save", { ref: sel, name: $("cname").value, traits: $("ctraits").value });
  toast(`saved as ${r.name}`); refresh();
});
$("unkeep").addEventListener("click", async () => {
  await post("/api/studio/hide", { ref: sel });
  sel = null; $("work").hidden = true; refresh();
});

// ---------- 5. characters ----------
function renderChars() {
  const box = $("chars");
  box.innerHTML = "";
  if (!S.characters.length) { box.appendChild(el("div", "muted small", "No character saved yet.")); return; }
  for (const c of S.characters) {
    const card = el("div", "char");
    const top = el("div", "char-top");
    top.appendChild(tile(refUrl(c.ref)));
    const info = el("div", "char-info");
    info.appendChild(el("div", "nm", c.name));
    info.appendChild(el("div", "muted", `seed ${c.meta.seed} · saved ${c.meta.saved_at}`));
    const row = el("div", "row");
    const selm = el("select");
    for (const [k, m] of Object.entries(S.models)) {
      const o = el("option", null, m.label + (m.ready ? "" : " (not downloaded)"));
      o.value = k; o.disabled = !m.ready; selm.appendChild(o);
    }
    const go = el("button", "btn primary", `Make variation set (${S.plan})`);
    go.addEventListener("click", async () => {
      await post("/api/studio/variations", { name: c.name, model: selm.value });
      toast("variation set queued"); refresh();
      $("batches").scrollIntoView({ behavior: "smooth" });
    });
    row.appendChild(selm); row.appendChild(go);
    info.appendChild(row);
    top.appendChild(info);
    card.appendChild(top);
    for (const r of c.runs) {
      const run = el("div", "run");
      const secs = r.items.map((i) => i.gen_seconds).filter(Boolean);
      const avg = secs.length ? (secs.reduce((a, b) => a + b, 0) / secs.length).toFixed(1) : "–";
      run.appendChild(el("div", "batch-head", `${r.label} · ${r.run} · ${r.items.length}/${S.plan} · ${avg} s each`));
      const g = el("div", "grid");
      for (const i of r.items) g.appendChild(tile(refUrl(`${r.dir}/${i.file}`), { label: i.label }));
      run.appendChild(g);
      card.appendChild(run);
    }
    box.appendChild(card);
  }
}

// ---------- lightbox ----------
const lb = $("lightbox"), lbImg = $("lightbox-img");
function openLightbox(src) { lbImg.src = src; lb.hidden = false; document.body.classList.add("noscroll"); }
function closeLightbox() { lb.hidden = true; lbImg.src = ""; document.body.classList.remove("noscroll"); }
lb.addEventListener("click", (e) => { if (e.target === lb || e.target.id === "lightbox-close") closeLightbox(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !lb.hidden) closeLightbox(); });

// ---------- polling ----------
async function refresh() {
  try {
    const d = await (await fetch("/api/studio/state")).json();
    const s = JSON.stringify(d);
    if (s === snap) return;
    const keptChanged = JSON.stringify(d.kept) !== JSON.stringify(S.kept);
    snap = s; S = d;
    renderBatches();
    if (keptChanged) renderKept();
    renderChars();
  } catch (e) { /* server restarting */ }
}
refresh();
setInterval(refresh, 2000);

// ---------- 6. frames ----------
const DEMO = [
  { text: "Haze: I'm going to get you home.", shape: "wide", method: "anima", chars: ["haze", "rem"],
    prompt: "1girl, haze (deadlock), rem (deadlock), wide shot, two-shot, night, city street, haze kneeling down " +
      "to rem, hand on rem's shoulder, serious, rem looking up at her, monochrome, greyscale, manga, clean lineart, " +
      "ink, screentone, full body" },
  { text: "Rem: I trust you. You're my mom!", shape: "square", method: "anima", chars: ["rem"],
    prompt: "solo, rem (deadlock), no humans, close-up, beaming, big happy smile, open mouth, sparkling eyes, " +
      "sparkle, hugging pillow, monochrome, greyscale, manga, clean lineart, ink, screentone, simple background" },
  { text: "Haze: I'm not.", shape: "tall", method: "anima", chars: ["haze"],
    prompt: "1girl, solo, haze (deadlock), close-up, portrait, deadpan, expressionless, half-closed eyes, " +
      "looking down, monochrome, greyscale, manga, clean lineart, ink, screentone, dark background" },
  { text: "Rem: I mean, you kinda are.", shape: "square", method: "anima", chars: ["rem"],
    prompt: "solo, rem (deadlock), no humans, small, chibi, sheepish smile, sweatdrop, looking away, " +
      "fidgeting, monochrome, greyscale, manga, clean lineart, ink, screentone, simple background, white background" },
];
let F = null, fsnap = "";
const fproject = $("fproject");

async function loadFrames() {
  const r = await fetch(`/api/frames/${encodeURIComponent(fproject.value)}`);
  if (!r.ok) return;
  F = await r.json();
  if (!F.lines.length && fproject.value === "deadlock-demo") { F.lines = DEMO.map((l) => ({ ...l })); saveFrames(); }
  fsnap = ""; renderFrames();
}
let saveT = null;
function saveFrames() {
  clearTimeout(saveT);
  saveT = setTimeout(() => fetch(`/api/frames/${encodeURIComponent(fproject.value)}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lines: F.lines }),
  }), 400);
}
fproject.addEventListener("change", loadFrames);
$("faddline").addEventListener("click", () => {
  F.lines.push({ text: "", shape: "wide", method: "anima", chars: [], prompt: "" });
  saveFrames(); fsnap = ""; renderFrames();
});

function frameJobs(i) {
  return S.jobs.filter((j) => j.kind === "frame" && j.params.project === F.project && j.params.line === i).slice(-8);
}

function renderFrames() {
  if (!F) return;
  const sig = JSON.stringify([F.lines.map((l) => l.chosen), F.lines.map((_, i) => frameJobs(i)), S.characters.map((c) => c.name)]);
  if (sig === fsnap) return;
  const typing = document.activeElement && document.activeElement.closest && document.activeElement.closest("#frames");
  if (typing && fsnap) return;  // do not redraw under the user's cursor
  fsnap = sig;
  const box = $("frames");
  box.innerHTML = "";
  F.lines.forEach((ln, i) => {
    const card = el("div", "fline");
    const head = el("div", "fhead");
    head.appendChild(el("b", null, `${i + 1}`));
    const txt = el("input", "ftext"); txt.value = ln.text || ""; txt.placeholder = "Speaker: line";
    txt.addEventListener("input", () => { ln.text = txt.value; saveFrames(); });
    head.appendChild(txt);
    card.appendChild(head);

    const row = el("div", "row");
    const shp = el("div", "chips");
    for (const k of Object.keys(F.shapes)) {
      const b = el("button", k === ln.shape ? "on" : "", k);
      b.addEventListener("click", () => { ln.shape = k; saveFrames(); fsnap = ""; renderFrames(); });
      shp.appendChild(b);
    }
    row.appendChild(shp);
    const meth = el("select");
    for (const [k, v] of Object.entries(F.methods)) { const o = el("option", null, v); o.value = k; meth.appendChild(o); }
    meth.value = ln.method || "anima";
    meth.addEventListener("change", () => { ln.method = meth.value; saveFrames(); });
    row.appendChild(meth);
    card.appendChild(row);

    const crow = el("div", "row small muted");
    crow.appendChild(el("span", null, "Characters:"));
    for (const c of S.characters) {
      const lab = el("label", "chk");
      const cb = el("input"); cb.type = "checkbox"; cb.checked = (ln.chars || []).includes(c.name);
      cb.addEventListener("change", () => {
        ln.chars = S.characters.map((x) => x.name).filter((n) => n === c.name ? cb.checked : (ln.chars || []).includes(n));
        saveFrames();
      });
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + c.name));
      crow.appendChild(lab);
    }
    if (!S.characters.length) crow.appendChild(el("span", null, "none saved yet"));
    card.appendChild(crow);

    const pr = el("textarea"); pr.rows = 3; pr.value = ln.prompt || "";
    pr.addEventListener("input", () => { ln.prompt = pr.value; saveFrames(); });
    card.appendChild(pr);

    const act = el("div", "row");
    const mk = el("button", "btn primary", "Make 4");
    mk.addEventListener("click", async () => {
      await post(`/api/frames/${encodeURIComponent(F.project)}/${i}/make`,
        { prompt: ln.prompt, shape: ln.shape, method: ln.method || "anima", chars: (ln.chars || []).join(","), count: 4 });
      toast(`line ${i + 1}: 4 frames queued`); refresh();
    });
    act.appendChild(mk);
    const js = frameJobs(i);
    const open = js.filter((j) => j.status === "queued" || j.status === "running");
    if (open.length) {
      const stop = el("button", "btn small danger", "Stop");
      stop.addEventListener("click", () => post("/api/studio/cancel", { batch: open[0].batch }).then(refresh));
      act.appendChild(stop);
    }
    card.appendChild(act);

    const g = el("div", "grid fgrid");
    if (ln.chosen) {
      const t = tile(refUrl(ln.chosen), { label: "picked" });
      t.classList.add("kept", "chosen");
      g.appendChild(t);
    }
    for (const j of js.slice().reverse()) {
      const t = j.status === "done"
        ? tile(refUrl(j.filename), { label: `${j.params.method} · seed ${j.params.seed}`, onTap: async () => {
            F = { ...F, ...(await post(`/api/frames/${encodeURIComponent(F.project)}/${i}/pick`, { job: j.id })) };
            toast(`line ${i + 1}: picked`); fsnap = ""; renderFrames();
          } })
        : jobTile(j);
      t.style.aspectRatio = `${j.params.width} / ${j.params.height}`;
      g.appendChild(t);
    }
    card.appendChild(g);
    box.appendChild(card);
  });
}
loadFrames();
setInterval(renderFrames, 2000);
