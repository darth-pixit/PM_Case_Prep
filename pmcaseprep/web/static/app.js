// PM Case Prep — browser client: always-on mic + live transcript + delivery
// meters + simultaneous typed input, over one WebSocket to the FastAPI backend.

const $ = (id) => document.getElementById(id);
const wsUrl = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws";

let ws;
let micOn = false;
let voiceSupported = false;
let audioCtx, micStream, workletNode, micSource;
let ended = false;

function setStatus(text, cls = "") {
  const el = $("status");
  el.textContent = text;
  el.className = "status " + cls;
}

function addMsg(who, text, tag) {
  const div = document.createElement("div");
  div.className = "msg " + who;
  const w = document.createElement("span");
  w.className = "who";
  w.innerHTML = tag ? `${who === "maya" ? "Maya" : "You"} <span class="tag">· ${tag}</span>` : (who === "maya" ? "Maya" : "You");
  div.appendChild(w);
  div.appendChild(document.createTextNode(text));
  $("log").appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
}

// --- WebSocket ---------------------------------------------------------------

function connect() {
  ws = new WebSocket(wsUrl);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => setStatus("connected", "ok");
  ws.onclose = () => setStatus("disconnected", "err");
  ws.onerror = () => setStatus("connection error", "err");
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
}

function handle(m) {
  switch (m.type) {
    case "case":
      $("caseArchetype").textContent = `${m.archetype} · ${m.case_type}`;
      $("caseTitle").textContent = m.title;
      $("casePrompt").textContent = m.prompt;
      addMsg("maya", m.prompt);
      voiceSupported = !!m.voice;
      if (voiceSupported) startMic();
      else { $("micBtn").textContent = "🎤 voice off (no key)"; $("micBtn").classList.add("off"); $("micBtn").disabled = true; }
      break;
    case "transcript":
      showPartial(m.text);
      break;
    case "final_turn":
      hidePartial();
      addMsg("you", m.text, "spoke");
      break;
    case "delivery":
      updateMeters(m);
      break;
    case "reply":
      addMsg("maya", m.text);
      break;
    case "status":
      if (m.text === "grading") setStatus("grading your case…", "ok");
      break;
    case "scorecard":
      renderScorecard(m);
      break;
    case "error":
      setStatus(m.text, "err");
      break;
  }
}

function showPartial(text) {
  const el = $("partial");
  el.textContent = "🎙 " + text;
  el.hidden = false;
}
function hidePartial() {
  $("partial").hidden = true;
  $("partial").textContent = "";
}

function updateMeters(d) {
  $("mWpm").textContent = d.wpm || "–";
  $("mWords").textContent = d.words || 0;
  $("mFiller").textContent = d.filler_rate_per_100 ?? 0;
  $("mCore").textContent = d.core_fillers ?? 0;
  $("mPauses").textContent = d.pause_count ?? 0;
  $("mLongest").textContent = (d.longest_pause_s ?? 0).toFixed ? d.longest_pause_s.toFixed(1) : d.longest_pause_s;
}

// --- Text + control actions --------------------------------------------------

function sendText() {
  const t = $("textInput").value.trim();
  if (!t || ended || ws.readyState !== 1) return;
  ws.send(JSON.stringify({ type: "text", text: t }));
  addMsg("you", t, "typed");
  $("textInput").value = "";
}

$("sendBtn").onclick = sendText;
$("textInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendText(); }
});
$("hintBtn").onclick = () => { if (ws.readyState === 1 && !ended) ws.send(JSON.stringify({ type: "hint" })); };
$("doneBtn").onclick = () => {
  if (ws.readyState === 1 && !ended) { ws.send(JSON.stringify({ type: "done" })); ended = true; setStatus("grading your case…", "ok"); }
};
$("micBtn").onclick = () => {
  if (!voiceSupported) return;
  if (!audioCtx) { startMic(); return; }
  micOn = !micOn;
  $("micBtn").textContent = micOn ? "🎤 Mic: on" : "🎤 Mic: off";
  $("micBtn").classList.toggle("off", !micOn);
  if (audioCtx.state === "suspended" && micOn) audioCtx.resume();
};

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
      if (!micOn || ended || ws.readyState !== 1) return;
      const pcm = floatTo16(resampleTo16k(e.data, inRate));
      ws.send(pcm.buffer);
    };
    micSource.connect(workletNode);
    // Worklet needs a sink to keep pulling frames; route to a muted gain.
    const sink = audioCtx.createGain();
    sink.gain.value = 0;
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
  const el = $("scorecard");
  const dims = c.dimension_scores.map(
    (d) => `<div class="dim"><span class="score s${d.score}">${d.score}/4</span>
      <span><b>${d.dimension}</b> — ${escapeHtml(d.justification)}</span></div>`
  ).join("");
  const checks = c.category_checklist.map(
    (i) => `<div class="check"><span class="${i.met ? "pass" : "miss"}">${i.met ? "✓" : "✗"}</span>
      ${escapeHtml(i.criterion)}${i.note ? " — <i>" + escapeHtml(i.note) + "</i>" : ""}</div>`
  ).join("");
  const flags = (c.red_flags || []).map((f) => `<div class="flag">⚑ ${escapeHtml(f)}</div>`).join("");
  el.innerHTML = `
    <h2>Scorecard — <span class="band ${m.band}">${m.band.replace(/_/g, " ").toUpperCase()}</span>
      <small>(weighted ${m.weighted}/4)</small></h2>
    ${dims}
    <h3>Checklist</h3>${checks}
    ${flags ? "<h3>Red flags</h3>" + flags : ""}
    <h3>Top improvement</h3><p>${escapeHtml(c.top_improvement)}</p>
    <h3>Delivery</h3><p>${escapeHtml(m.delivery_summary)}</p>
    <p>${escapeHtml(c.summary)}</p>
    <h3>Skill graph</h3><pre class="graph">${escapeHtml(m.skill_graph)}</pre>`;
  el.hidden = false;
  el.scrollIntoView({ behavior: "smooth" });
  setStatus("done", "ok");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

connect();
