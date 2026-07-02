// PM Case Prep — browser client. Real-interview feel: always-on mic, no echo of
// your own words (just a "listening" pulse), interviewer speaks sparingly, no
// live stats, stable window (only the conversation scrolls).

const $ = (id) => document.getElementById(id);
const wsUrl = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws";

let ws;
let micOn = false;
let voiceSupported = false;
let audioCtx, micStream, workletNode, micSource;
let ended = false;
let listenTimer = null;

function setStatus(text, cls = "") {
  const el = $("status");
  el.textContent = text;
  el.className = "status " + cls;
}

function addMaya(text) {
  const log = $("log");
  const div = document.createElement("div");
  div.className = "msg maya";
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = "Interviewer";
  div.appendChild(who);
  div.appendChild(document.createTextNode(text));
  log.appendChild(div);
  // Scroll ONLY the log, not the page.
  log.scrollTop = log.scrollHeight;
}

function pulseListening() {
  const el = $("listening");
  el.hidden = false;
  if (listenTimer) clearTimeout(listenTimer);
  listenTimer = setTimeout(() => { el.hidden = true; }, 1400);
}

// --- WebSocket ---------------------------------------------------------------

function connect() {
  ws = new WebSocket(wsUrl);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => setStatus("connected", "ok");
  ws.onerror = () => setStatus("connection error", "err");
  ws.onclose = () => {
    setStatus("disconnected", "err");
    if (!ended) $("reconnect").hidden = false; // session dropped mid-interview
  };
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
}

function handle(m) {
  switch (m.type) {
    case "case":
      $("caseArchetype").textContent = `${m.archetype} · ${m.case_type}`;
      $("caseTitle").textContent = m.title;
      $("casePrompt").textContent = m.prompt;
      addMaya(m.prompt);
      voiceSupported = !!m.voice;
      if (voiceSupported) startMic();
      else { const b = $("micBtn"); b.textContent = "🎤 voice off (no key)"; b.classList.add("off"); b.disabled = true; }
      break;
    case "listening":
      pulseListening();
      break;
    case "reply":
      addMaya(m.text);
      break;
    case "status":
      setStatus(m.text === "grading" ? "grading your case…" : m.text, "ok");
      break;
    case "scorecard":
      renderScorecard(m);
      break;
    case "error":
      setStatus(m.text, "err");
      break;
    // Note: we intentionally do NOT render the candidate's own transcript.
  }
}

// --- Text + control actions --------------------------------------------------

function sendText() {
  const t = $("textInput").value.trim();
  if (!t || ended || !ws || ws.readyState !== 1) return;
  ws.send(JSON.stringify({ type: "text", text: t }));
  $("textInput").value = ""; // you typed it; we don't echo it back
}

$("sendBtn").onclick = sendText;
$("textInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendText(); }
});
$("hintBtn").onclick = () => { if (ws && ws.readyState === 1 && !ended) ws.send(JSON.stringify({ type: "hint" })); };
$("doneBtn").onclick = () => {
  if (ws && ws.readyState === 1 && !ended) { ws.send(JSON.stringify({ type: "done" })); ended = true; setStatus("grading your case…", "ok"); }
};
$("micBtn").onclick = () => {
  if (!voiceSupported) return;
  if (!audioCtx) { startMic(); return; }
  micOn = !micOn;
  $("micBtn").textContent = micOn ? "🎤 Mic: on" : "🎤 Mic: off";
  $("micBtn").classList.toggle("off", !micOn);
  if (micOn && audioCtx.state === "suspended") audioCtx.resume();
};
$("reloadBtn").onclick = () => location.reload();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && audioCtx && audioCtx.state === "suspended") audioCtx.resume();
});

// --- Microphone: capture -> resample to 16k Int16 -> stream ------------------

async function startMic() {
  if (audioCtx) return;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    await audioCtx.audioWorklet.addModule("/static/worklet.js");
    micSource = audioCtx.createMediaStreamSource(micStream);
    workletNode = new AudioWorkletNode(audioCtx, "pcm-worklet");
    const inRate = audioCtx.sampleRate;
    workletNode.port.onmessage = (e) => {
      if (!micOn || ended || !ws || ws.readyState !== 1) return;
      ws.send(floatTo16(resampleTo16k(e.data, inRate)).buffer);
    };
    micSource.connect(workletNode);
    const sink = audioCtx.createGain();
    sink.gain.value = 0; // keep the graph pulling frames without audible output
    workletNode.connect(sink).connect(audioCtx.destination);
    micOn = true;
    $("micBtn").textContent = "🎤 Mic: on";
    $("micBtn").classList.remove("off");
  } catch (err) {
    micOn = false;
    $("micBtn").textContent = "🎤 mic blocked";
    $("micBtn").classList.add("off");
    setStatus("mic permission needed — you can still type", "err");
  }
}

function resampleTo16k(input, inRate) {
  if (inRate === 16000) return input;
  const ratio = inRate / 16000;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const idx = i * ratio;
    const i0 = Math.floor(idx);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = idx - i0;
    out[i] = input[i0] * (1 - frac) + input[i1] * frac;
  }
  return out;
}

function floatTo16(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

// --- Scorecard ---------------------------------------------------------------

function renderScorecard(m) {
  const c = m.card;
  const dims = c.dimension_scores.map(
    (d) => `<div class="dim"><span class="score s${d.score}">${d.score}/4</span>
      <span><b>${d.dimension}</b> — ${esc(d.justification)}</span></div>`
  ).join("");
  const checks = c.category_checklist.map(
    (i) => `<div class="check"><span class="${i.met ? "pass" : "miss"}">${i.met ? "✓" : "✗"}</span>
      ${esc(i.criterion)}${i.note ? " — <i>" + esc(i.note) + "</i>" : ""}</div>`
  ).join("");
  const flags = (c.red_flags || []).map((f) => `<div class="flag">⚑ ${esc(f)}</div>`).join("");
  $("scorecard").innerHTML = `
    <h2>Scorecard — <span class="band ${m.band}">${m.band.replace(/_/g, " ").toUpperCase()}</span>
      <small>(weighted ${m.weighted}/4)</small></h2>
    ${dims}
    <h3>Checklist</h3>${checks}
    ${flags ? "<h3>Red flags</h3>" + flags : ""}
    <h3>Top improvement</h3><p>${esc(c.top_improvement)}</p>
    <h3>Delivery</h3><p>${esc(m.delivery_summary)}</p>
    <p>${esc(c.summary)}</p>
    <h3>Skill graph</h3><pre class="graph">${esc(m.skill_graph)}</pre>`;
  $("scorecard").hidden = false;
  setStatus("done", "ok");
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

connect();
