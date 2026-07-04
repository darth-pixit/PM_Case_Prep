// PM Case Prep — browser client. Real-interview feel:
//  * a start gate makes "the mic is always on" impossible to miss (and the
//    click doubles as the user gesture that grants mic permission),
//  * one presence indicator answers listening / thinking / speaking at a
//    glance, with a live voice meter so you SEE it hearing you,
//  * only the interviewer's LATEST message stays on screen (history one click
//    away), your own words are never echoed,
//  * always-on mic + simultaneous typing,
//  * grading shows a progress bar; the scorecard is a visual report with a
//    score gauge, band ladder, trajectory sparkline and learning links.

const $ = (id) => document.getElementById(id);
const wsUrl = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws";

// --- Analytics (PostHog) -------------------------------------------------
// The key comes from /config (server env), is publishable by design, and when
// absent everything silently no-ops. Autocapture covers pageviews + every
// click; track() adds the interview-funnel events. No transcript content is
// ever sent — only event names and coarse properties.

let phReady = false;
const phQueue = [];

function track(name, props) {
  if (phReady) window.posthog.capture(name, props);
  else phQueue.push([name, props]);
}

(async function initAnalytics() {
  try {
    const cfg = await (await fetch("/config")).json();
    if (!cfg.posthog_key) return;
    const assets = cfg.posthog_host.replace(".i.posthog.com", "-assets.i.posthog.com");
    const s = document.createElement("script");
    s.src = assets + "/static/array.js";
    s.onload = () => {
      window.posthog.init(cfg.posthog_key, {
        api_host: cfg.posthog_host,
        defaults: "2025-05-24",
        person_profiles: "always", // every visitor becomes a distinct person
      });
      phReady = true;
      phQueue.splice(0).forEach(([n, p]) => window.posthog.capture(n, p));
    };
    document.head.appendChild(s);
  } catch (e) { /* analytics must never break the interview */ }
})();

// --- State ----------------------------------------------------------------

let ws;
let micOn = false;
let voiceSupported = false;
let userStarted = false;
let audioCtx, micStream, workletNode, micSource;
let ended = false;
let currentState = "connecting";
let speakTimer = null;

const STATE_META = {
  connecting: { label: "Connecting…", hint: "" },
  listening: { label: "Listening", hint: "Mic is on — think out loud, take your time" },
  thinking: { label: "Thinking…", hint: "Maya is considering what you said" },
  speaking: { label: "Maya is speaking", hint: "Her reply is below" },
  grading: { label: "Grading your case…", hint: "" },
  error: { label: "Problem", hint: "see top right" },
  done: { label: "Interview complete", hint: "" },
  textonly: { label: "Ready (text only)", hint: "No voice key — type your answers below" },
};

function setState(state) {
  currentState = state;
  const orb = $("orb");
  const orbState = state === "textonly" || state === "done" ? "listening" : state;
  orb.className = "orb big " + orbState;
  const meta = STATE_META[state] || { label: state, hint: "" };
  $("stateLabel").textContent = meta.label;
  $("stateHint").textContent = meta.hint;
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

// --- Grading progress -----------------------------------------------------
// The server can't stream real percentages out of one long model call, so we
// animate toward (never past) 95% and jump to 100% when the scorecard lands.

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
      track("case_started", { case_title: m.title, archetype: m.archetype, voice: !!m.voice });
      voiceSupported = !!m.voice;
      if (!voiceSupported) {
        const b = $("micBtn");
        b.textContent = "🎤 voice off (no key)";
        b.classList.add("off");
        b.disabled = true;
        $("startBtn").textContent = "Start interview (text only)";
        $("startNote").textContent = "No voice key configured — you can type everything.";
        if (userStarted) setState("textonly");
      } else if (userStarted && !audioCtx) {
        startMic();
      }
      break;
    case "state": {
      const s = m.state === "responding" ? "thinking" : m.state;
      // Give a fresh reply a beat on screen before flipping back to Listening.
      if (s === "listening" && currentState === "speaking") break;
      if (s === "listening" && !voiceSupported) setState("textonly");
      else setState(s);
      break;
    }
    case "listening": // server-side speech activity (kept for non-mic senders)
      break;
    case "reply":
      showMaya(m.text);
      setState("speaking");
      clearTimeout(speakTimer);
      speakTimer = setTimeout(() => {
        if (currentState === "speaking") setState(voiceSupported ? "listening" : "textonly");
      }, 2600);
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

// --- Start gate ---------------------------------------------------------------

$("startBtn").onclick = () => {
  userStarted = true;
  track("interview_started", { voice: voiceSupported });
  $("startOverlay").hidden = true;
  if (voiceSupported) startMic();
  else setState(currentState === "connecting" ? "connecting" : "textonly");
  $("textInput").focus();
};

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
$("hintBtn").onclick = () => {
  if (ws && ws.readyState === 1 && !ended) {
    track("hint_requested", {});
    ws.send(JSON.stringify({ type: "hint" }));
  }
};
$("doneBtn").onclick = () => {
  if (ws && ws.readyState === 1 && !ended) {
    track("interview_finished", {});
    ws.send(JSON.stringify({ type: "done" }));
    ended = true;
    setState("grading");
  }
};
$("micBtn").onclick = () => {
  if (!voiceSupported) return;
  if (!audioCtx) { startMic(); return; }
  micOn = !micOn;
  updateMicUi();
  if (micOn && audioCtx.state === "suspended") audioCtx.resume();
};
$("reloadBtn").onclick = () => location.reload();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && audioCtx && audioCtx.state === "suspended") audioCtx.resume();
});

function updateMicUi() {
  const b = $("micBtn");
  b.textContent = micOn ? "🎤 Mic is live" : "🔇 Muted — click to unmute";
  b.classList.toggle("off", !micOn);
  $("eq").hidden = !micOn;
}

// --- Microphone: capture -> resample to 16k Int16 -> stream ------------------
// A local RMS level drives the voice meter, so "it hears me" is visible with
// zero server round-trip.

let lastMeter = 0;
const EQ_WEIGHTS = [0.55, 0.85, 1.0, 0.7, 0.45];

function meter(frame) {
  const now = performance.now();
  if (now - lastMeter < 80) return;
  lastMeter = now;
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  const level = Math.min(1, Math.sqrt(sum / frame.length) * 9);
  const bars = $("eq").children;
  for (let i = 0; i < bars.length; i++) {
    bars[i].style.transform = `scaleY(${(0.18 + level * EQ_WEIGHTS[i]).toFixed(2)})`;
  }
  $("orb").style.setProperty("--lvl", level.toFixed(2));
}

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
      meter(e.data);
      ws.send(floatTo16(resampleTo16k(e.data, inRate)).buffer);
    };
    micSource.connect(workletNode);
    const sink = audioCtx.createGain();
    sink.gain.value = 0; // keep the graph pulling frames without audible output
    workletNode.connect(sink).connect(audioCtx.destination);
    micOn = true;
    updateMicUi();
  } catch (err) {
    micOn = false;
    $("micBtn").textContent = "🎤 mic blocked";
    $("micBtn").classList.add("off");
    track("mic_blocked", {});
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

const DIM_META = {
  structure: ["Structure", "🧭"],
  user_empathy: ["User empathy", "❤️"],
  prioritization: ["Prioritization", "⚖️"],
  creativity: ["Creativity", "✨"],
  communication: ["Communication", "🗣️"],
  data_business: ["Data & business", "📊"],
};

function dimMeta(key) {
  if (DIM_META[key]) return DIM_META[key];
  const s = String(key).replace(/_/g, " ");
  return [s.charAt(0).toUpperCase() + s.slice(1), "•"];
}

function resourceLink(r, where) {
  return `<a class="resource" href="${esc(r.url)}" target="_blank" rel="noopener"
    data-where="${esc(where)}">${esc(r.title)}</a> <small>· ${esc(r.author)}</small>`;
}

// Score gauge: an SVG donut that fills to weighted/4 on load.
function gauge(weighted, band) {
  const R = 52;
  const C = 2 * Math.PI * R;
  const frac = Math.max(0, Math.min(1, weighted / 4));
  const tone = band === "hire" || band === "strong_hire"
    ? "var(--good)" : weighted >= 2 ? "var(--warn)" : "var(--bad)";
  return `<svg class="sc-gauge" viewBox="0 0 120 120" role="img"
      aria-label="Weighted score ${esc(weighted)} out of 4">
    <circle cx="60" cy="60" r="${R}" class="g-track"/>
    <circle cx="60" cy="60" r="${R}" class="g-fill"
      style="stroke:${tone}; stroke-dasharray:${C.toFixed(1)}; stroke-dashoffset:${C.toFixed(1)}"
      data-target="${(C * (1 - frac)).toFixed(1)}"/>
    <text x="60" y="64" class="g-num">${esc(weighted)}</text>
    <text x="60" y="80" class="g-den">out of 4</text>
  </svg>`;
}

// Band ladder: where this score sits on strong-no-hire -> strong-hire.
function ladder(weighted) {
  const zones = [
    ["strong_no_hire", 0, 2.0, "strong no"],
    ["no_hire", 2.0, 2.75, "no hire"],
    ["hire", 2.75, 3.5, "hire"],
    ["strong_hire", 3.5, 4.0, "strong"],
  ];
  const seg = zones.map(([k, a, b, label]) =>
    `<div class="lz ${k}" style="width:${(((b - a) / 4) * 100).toFixed(2)}%"><span>${label}</span></div>`
  ).join("");
  const pct = Math.max(1, Math.min(99, (weighted / 4) * 100));
  return `<div class="lz-row">${seg}<div class="lz-marker" style="left:${pct.toFixed(1)}%"></div></div>`;
}

// Trajectory sparkline: per-case scores with the hire / strong-hire bars.
function sparkline(series) {
  if (!series || series.length < 2) return "";
  const W = 250, H = 76, P = 10;
  const x = (i) => P + (i * (W - 2 * P)) / (series.length - 1);
  const y = (v) => H - P - ((Math.max(1, v) - 1) / 3) * (H - 2 * P);
  const pts = series.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const dots = series.map((v, i) =>
    `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${i === series.length - 1 ? 4.5 : 3}"
       class="sp-dot${i === series.length - 1 ? " last" : ""}"/>`).join("");
  return `<svg class="sc-spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="Score per case">
    <line x1="${P}" x2="${W - P}" y1="${y(2.75).toFixed(1)}" y2="${y(2.75).toFixed(1)}" class="sp-bar hire"/>
    <text x="${W - P}" y="${(y(2.75) - 3).toFixed(1)}" class="sp-lbl" text-anchor="end">hire 2.75</text>
    <line x1="${P}" x2="${W - P}" y1="${y(3.5).toFixed(1)}" y2="${y(3.5).toFixed(1)}" class="sp-bar strong"/>
    <text x="${W - P}" y="${(y(3.5) - 3).toFixed(1)}" class="sp-lbl" text-anchor="end">strong 3.5</text>
    <polyline points="${pts}" class="sp-line"/>
    ${dots}
  </svg>`;
}

function trajectoryCard(t) {
  if (!t) return "";
  if (t.sessions < 2) {
    return `<div class="sc-card"><h3>Your trajectory</h3>
      <p class="sc-dim-note">${esc(t.note || "Finish one more case to unlock your trajectory.")}</p></div>`;
  }
  const tile = (label, val) => `<div class="sc-tile"><div class="label">${esc(label)}</div>
    <div class="value">${val}</div></div>`;
  const fmt = (n) => (n === 0 ? "✓ there" : n === null ? "—" : `~${n} case${n === 1 ? "" : "s"}`);
  const spark = sparkline(t.series);
  return `<div class="sc-card"><h3>Your trajectory</h3>
    <div class="sc-traj">
      ${spark}
      <div class="sc-tiles traj-tiles">
        ${tile("Cases done", esc(t.sessions))}
        ${tile("To HIRE bar", esc(fmt(t.to_hire)))}
        ${tile("To STRONG HIRE", esc(fmt(t.to_strong_hire)))}
      </div>
    </div>
    <p class="sc-dim-note">${esc(t.note)}</p></div>`;
}

function renderScorecard(m) {
  const c = m.card;
  const dimResources = (m.resources && m.resources.dimensions) || {};
  const caseResources = (m.resources && m.resources.case) || [];

  // Dimension meters: fill = score severity, track = same hue lighter.
  const dims = c.dimension_scores.map((d) => {
    const tone = d.score <= 2 ? "m-low" : d.score === 3 ? "m-mid" : "m-high";
    const [name, ico] = dimMeta(d.dimension);
    const links = (dimResources[d.dimension] || [])
      .map((r) => resourceLink(r, d.dimension)).join("<br>");
    return `<div class="sc-dim">
      <div class="sc-dim-head"><b><span class="dim-ico">${ico}</span> ${esc(name)}</b>
        <span class="sc-dim-score">${d.score} / 4</span></div>
      <div class="sc-meter ${tone}"><i style="width:0%" data-w="${(d.score / 4) * 100}"></i></div>
      <p class="sc-dim-note">${esc(d.justification)}</p>
      ${links ? `<p class="sc-links">Level up: ${links}</p>` : ""}
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
          ${ladder(m.weighted)}
        </div>
        ${gauge(m.weighted, band)}
      </header>

      <div class="sc-card sc-opp"><h3>💡 Your biggest opportunity</h3>
        <p class="lede">${esc(c.top_improvement)}</p></div>

      ${trajectoryCard(m.trajectory)}

      <div class="sc-dims">${dims}</div>

      <details class="sc-fold">
        <summary>What the rubric looked for <span class="sc-count">${met} of ${c.category_checklist.length} met</span></summary>
        ${checks}
      </details>

      ${flags}
      ${delivery}

      ${caseResources.length ? `<div class="sc-card"><h3>📚 Go deeper on this case's concepts</h3>
        ${caseResources.map((r) => `<div class="sc-res">${resourceLink(r, "case")}
          ${r.why ? `<small class="why">${esc(r.why)}</small>` : ""}</div>`).join("")}
      </div>` : ""}

      <div class="sc-card"><h3>Coach's note</h3><p>${esc(c.summary)}</p></div>

      <details class="sc-fold">
        <summary>Full skill graph</summary>
        <pre class="graph">${esc(m.skill_graph)}</pre>
      </details>

      <div class="sc-actions">
        <button id="newCaseBtn">Do another case →</button>
        <span class="sub">Starts a fresh interview</span>
      </div>
    </div>`;
  $("gradingOverlay").hidden = true;
  $("scorecard").hidden = false;
  // Kick the entrance animations once painted: meters fill, gauge sweeps.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.querySelectorAll(".sc-meter > i").forEach((el) => {
      el.style.width = el.dataset.w + "%";
    });
    const g = document.querySelector(".g-fill");
    if (g) g.style.strokeDashoffset = g.dataset.target;
  }));
  track("scorecard_viewed", { band: m.band, weighted: m.weighted, sessions: m.trajectory && m.trajectory.sessions });
  $("newCaseBtn").onclick = () => { track("new_case_clicked", {}); location.reload(); };
  $("scorecard").addEventListener("click", (e) => {
    const a = e.target.closest("a.resource");
    if (a) track("resource_opened", { url: a.href, where: a.dataset.where });
  });
  setState("done");
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

setState("connecting");
connect();
