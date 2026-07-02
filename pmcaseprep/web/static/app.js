// PM Case Prep — browser client. Real-interview feel:
//  * only the interviewer's LATEST message stays on screen (no chat history),
//  * exactly two labeled states: Listening and Interviewer is responding
//    (voice activity just brightens the orb — no third label),
//  * your own words are never echoed,
//  * always-on mic + simultaneous typing,
//  * grading shows a progress bar, and the scorecard ends with "Do another case".

const $ = (id) => document.getElementById(id);
const wsUrl = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws";

let ws;
let micOn = false;
let voiceSupported = false;
let audioCtx, micStream, workletNode, micSource;
let ended = false;
let voiceTimer = null;
let currentState = "connecting";

const STATE_LABELS = {
  connecting: "connecting…",
  listening: "Listening — take your time",
  responding: "Interviewer is responding…",
  grading: "Grading your case…",
  error: "problem — see top right",
  done: "Interview complete",
  textonly: "Ready (text only — no voice key)",
};

function setState(state) {
  currentState = state;
  const orb = $("orb");
  orb.className = "orb " + (state === "textonly" || state === "done" ? "listening" : state);
  $("stateLabel").textContent = STATE_LABELS[state] || state;
  $("gradingOverlay").hidden = state !== "grading";
  if (state === "grading") startGradeProgress();
  else stopGradeProgress();
}

function setError(text) {
  const el = $("status");
  el.textContent = text;
  el.className = "status err";
}

// Every reply the interviewer has made, oldest first. The stage still shows only
// the latest one, but nothing is ever lost — "earlier replies" opens the rest.
const replyHistory = [];

function showMaya(text) {
  const prev = $("mayaText").textContent;
  if (!$("mayaMsg").hidden && prev) replyHistory.push(prev);
  $("historyBtn").hidden = replyHistory.length === 0;
  $("mayaText").textContent = text;
  const box = $("mayaMsg");
  box.hidden = false;
  // retrigger the fade-in
  box.style.animation = "none";
  void box.offsetWidth;
  box.style.animation = "";
  box.scrollTop = 0;
}

$("historyBtn").onclick = () => {
  $("historyList").innerHTML = replyHistory
    .slice()
    .reverse()
    .map((t) => `<div class="history-item">${esc(t)}</div>`)
    .join("");
  $("historyPanel").hidden = false;
};
$("historyClose").onclick = () => { $("historyPanel").hidden = true; };
$("historyPanel").addEventListener("click", (e) => {
  if (e.target === $("historyPanel")) $("historyPanel").hidden = true;
});

// Voice activity only brightens the orb; the label stays "Listening".
function pulseVoice() {
  if (currentState !== "listening") return;
  $("orb").classList.add("voiced");
  if (voiceTimer) clearTimeout(voiceTimer);
  voiceTimer = setTimeout(() => $("orb").classList.remove("voiced"), 1200);
}

// --- Grading progress -----------------------------------------------------
// The server can't stream real percentages out of one long model call, so we
// animate toward (never past) 95% and jump to 100% when the scorecard lands.
// Better a bar that's honest-ish and moving than a spinner that looks hung.

const GRADE_STAGES = [
  [0, "Re-reading your full transcript…"],
  [22, "Scoring the six dimensions against the rubric…"],
  [45, "Working through the case checklist…"],
  [65, "Weighing red flags and your spoken delivery…"],
  [82, "Writing your coaching notes…"],
];
let gradeTimer = null;
let gradeStart = 0;

function startGradeProgress() {
  if (gradeTimer) return;
  gradeStart = Date.now();
  setGradePct(0);
  gradeTimer = setInterval(() => {
    const t = (Date.now() - gradeStart) / 1000;
    setGradePct(Math.min(95, 100 * (1 - Math.exp(-t / 24))));
  }, 250);
}

function stopGradeProgress() {
  if (gradeTimer) { clearInterval(gradeTimer); gradeTimer = null; }
}

function setGradePct(pct) {
  const p = Math.round(pct);
  $("gradeFill").style.width = p + "%";
  $("gradePct").textContent = p + "%";
  for (const [at, label] of GRADE_STAGES) {
    if (p >= at) $("gradeStage").textContent = label;
  }
}

// --- WebSocket ---------------------------------------------------------------

function connect() {
  ws = new WebSocket(wsUrl);
  ws.binaryType = "arraybuffer";
  ws.onerror = () => setError("connection error");
  ws.onclose = () => {
    if (!ended) {
      setState("error");
      $("reconnect").hidden = false;
    }
  };
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
}

function handle(m) {
  switch (m.type) {
    case "case":
      $("caseArchetype").textContent = `${m.archetype} · ${m.case_type}`;
      $("caseTitle").textContent = m.title;
      $("casePrompt").textContent = m.prompt;
      // The case card already shows the prompt; the message panel stays hidden
      // until the interviewer actually says something.
      voiceSupported = !!m.voice;
      if (voiceSupported) startMic();
      else {
        const b = $("micBtn");
        b.textContent = "🎤 voice off (no key)";
        b.classList.add("off");
        b.disabled = true;
        setState("textonly");
      }
      break;
    case "state":
      // Voice-off sessions keep their clearer "text only" idle label.
      if (m.state === "listening" && !voiceSupported) setState("textonly");
      else setState(m.state);
      break;
    case "listening": // audio activity pulse from the server
      pulseVoice();
      break;
    case "reply":
      showMaya(m.text);
      break;
    case "status":
      if (m.text && m.text.includes("reconnect")) setError(m.text);
      break;
    case "scorecard":
      setGradePct(100);
      renderScorecard(m);
      break;
    case "error":
      setError(m.text);
      break;
  }
}

// --- Text + control actions --------------------------------------------------

function sendText() {
  const t = $("textInput").value.trim();
  if (!t || ended || !ws || ws.readyState !== 1) return;
  ws.send(JSON.stringify({ type: "text", text: t }));
  $("textInput").value = ""; // your words aren't echoed — like speaking in the room
}

$("sendBtn").onclick = sendText;
$("textInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendText(); }
});
$("hintBtn").onclick = () => { if (ws && ws.readyState === 1 && !ended) ws.send(JSON.stringify({ type: "hint" })); };
$("doneBtn").onclick = () => {
  if (ws && ws.readyState === 1 && !ended) {
    ws.send(JSON.stringify({ type: "done" }));
    ended = true;
    setState("grading");
  }
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
    setError("mic permission needed — you can still type");
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

const DIM_NAMES = {
  structure: "Structure",
  user_empathy: "User empathy",
  prioritization: "Prioritization",
  creativity: "Creativity",
  communication: "Communication",
  data_business: "Data & business",
};

function dimName(key) {
  if (DIM_NAMES[key]) return DIM_NAMES[key];
  const s = String(key).replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function renderScorecard(m) {
  const c = m.card;

  // Dimension meters: fill = score severity, track = same hue lighter.
  const dims = c.dimension_scores.map((d) => {
    const tone = d.score <= 2 ? "m-low" : d.score === 3 ? "m-mid" : "m-high";
    return `<div class="sc-dim">
      <div class="sc-dim-head"><b>${esc(dimName(d.dimension))}</b>
        <span class="sc-dim-score">${d.score} / 4</span></div>
      <div class="sc-meter ${tone}"><i style="width:${(d.score / 4) * 100}%"></i></div>
      <p class="sc-dim-note">${esc(d.justification)}</p>
    </div>`;
  }).join("");

  const met = c.category_checklist.filter((i) => i.met).length;
  const checks = c.category_checklist.map(
    (i) => `<div class="sc-check">
      <span class="icon ${i.met ? "pass" : "miss"}">${i.met ? "✓" : "✗"}</span>
      <span>${esc(i.criterion)}${i.note ? `<small>${esc(i.note)}</small>` : ""}</span>
    </div>`
  ).join("");

  const flags = (c.red_flags || []).map(
    (f) => `<div class="sc-flag"><b>⚑ Watch-out</b><p>${esc(f)}</p></div>`
  ).join("");

  const dv = m.delivery || {};
  const delivery = dv.words > 0
    ? `<div class="sc-card"><h3>How you sounded</h3>
        <div class="sc-tiles">
          <div class="sc-tile"><div class="label">Pace</div><div class="value">${esc(dv.wpm)} <small>wpm</small></div></div>
          <div class="sc-tile"><div class="label">Hard fillers (um/uh)</div><div class="value">${esc(dv.core_fillers)}</div></div>
          <div class="sc-tile"><div class="label">Fillers per 100 words</div><div class="value">${esc(dv.filler_rate_per_100)}</div></div>
          <div class="sc-tile"><div class="label">Longest pause</div><div class="value">${esc(dv.longest_pause_s)} <small>s</small></div></div>
        </div>
        <p class="sc-dim-note">${esc(m.delivery_summary)}</p></div>`
    : "";

  const band = String(m.band);
  $("scorecard").innerHTML = `
    <div class="sc-wrap">
      <header class="sc-hero">
        <div class="sc-hero-left">
          <h2>Your scorecard</h2>
          <span class="sc-band ${esc(band)}">${esc(band.replace(/_/g, " ").toUpperCase())}</span>
        </div>
        <div class="sc-score"><span class="sc-num">${esc(m.weighted)}</span>
          <span class="sc-den">weighted score out of 4</span></div>
      </header>

      <div class="sc-card sc-opp"><h3>💡 Your biggest opportunity</h3>
        <p class="lede">${esc(c.top_improvement)}</p></div>

      <div class="sc-dims">${dims}</div>

      <details class="sc-fold">
        <summary>What the rubric looked for <span class="sc-count">${met} of ${c.category_checklist.length} met</span></summary>
        ${checks}
      </details>

      ${flags}
      ${delivery}

      <div class="sc-card"><h3>Coach's note</h3><p>${esc(c.summary)}</p></div>

      <details class="sc-fold">
        <summary>Your progress across cases</summary>
        <pre class="graph">${esc(m.skill_graph)}</pre>
      </details>

      <div class="sc-actions">
        <button id="newCaseBtn">Do another case →</button>
        <span class="sub">Starts a fresh interview</span>
      </div>
    </div>`;
  $("gradingOverlay").hidden = true;
  $("scorecard").hidden = false;
  $("newCaseBtn").onclick = () => location.reload();
  setState("done");
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

setState("connecting");
connect();
