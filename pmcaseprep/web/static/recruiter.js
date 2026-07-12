// Recruiter Copilot — its own experiment, its own analytics namespace.
// Two halves:
//  * a login-gated CHAT (each reply is a paid model call) that interviews the
//    recruiter about the role, then maps it to today's interview landscape;
//  * a free FIELD GUIDE (question archetypes, concepts, evaluation technique,
//    learning links) rendered from the researched knowledge base.

const { track } = PMCP.experiment("recruiter");
const $ = (id) => document.getElementById(id);
const esc = PMCP.esc;

// --- Tiny markdown (bot replies): headers, bold, lists, links, paragraphs ----
function md(text) {
  const safe = esc(text);
  const lines = safe.split("\n");
  let html = "", inList = false;
  const inline = (s) => s
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  for (const raw of lines) {
    const l = raw.trimEnd();
    const m = l.match(/^(#{1,4})\s+(.*)/);
    const li = l.match(/^\s*[-*•]\s+(.*)/) || l.match(/^\s*\d+[.)]\s+(.*)/);
    if (li) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += "<li>" + inline(li[1]) + "</li>";
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    if (m) html += `<h3>${inline(m[2])}</h3>`;
    else if (l.trim()) html += `<p>${inline(l)}</p>`;
  }
  if (inList) html += "</ul>";
  return html;
}

// --- Chat ---------------------------------------------------------------------

const history = []; // {role, text}
let sending = false;

const PRESETS = [
  "We need a data scientist for our growth team",
  "Hiring an ML engineer to build LLM features",
  "First AI hire at a small startup — not sure what role",
  "Senior GenAI engineer — RAG + agents",
];

$("presets").innerHTML = PRESETS.map((p) =>
  `<button class="chip">${esc(p)}</button>`).join("");
$("presets").querySelectorAll(".chip").forEach((b) => {
  b.onclick = () => {
    $("chatInput").value = b.textContent;
    track("preset_clicked", { preset: b.textContent });
    if (!$("compose").hidden) send();
  };
});

function addMsg(role, text, thinking) {
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "user" : "bot") + (thinking ? " thinking" : "");
  if (role === "user" || thinking) div.textContent = text;
  else div.innerHTML = md(text);
  $("chat").appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
  return div;
}

async function send() {
  const text = $("chatInput").value.trim();
  if (!text || sending) return;
  $("chatInput").value = "";
  history.push({ role: "user", text });
  addMsg("user", text);
  track("message_sent", { turn: history.length });
  sending = true;
  $("chatSend").disabled = true;
  const spinner = addMsg("bot", "thinking about the market for this role…", true);
  try {
    const r = await fetch("/api/recruiter/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });
    const d = await r.json();
    spinner.remove();
    if (d.ok) {
      history.push({ role: "assistant", text: d.reply });
      addMsg("bot", d.reply);
    } else {
      addMsg("bot", d.error || "That didn't work — try again.", true);
      track("chat_error", { status: r.status });
    }
  } catch {
    spinner.remove();
    addMsg("bot", "Network problem — try again.", true);
  }
  sending = false;
  $("chatSend").disabled = false;
}

$("chatSend").onclick = send;
$("chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});

track("viewed", {});
PMCP.mountAuth($("authMount"), {
  reason: "Sign in to chat — it keeps the copilot for real recruiters (each answer runs a full model call). The field guide below is open, no login needed.",
  onLogin: (email, d) => {
    if (!d || !d.already) track("signed_in", {});
    $("whoami").textContent = email;
    $("chatGate").hidden = true;
    $("compose").hidden = false;
  },
});

// --- Field guide ----------------------------------------------------------------

let guide = null;
let tab = "archetypes";

const roleName = (key) => {
  const r = guide && guide.roles.find((x) => x.key === key);
  return r ? r.name : key;
};

function renderGuide() {
  if (!guide) return;
  const g = guide;
  let html = "";
  if (tab === "archetypes") {
    html = g.archetypes.map((a) => `
      <details class="fold">
        <summary>${esc(a.name)} <span class="count">${(a.roles || []).map(roleName).map(esc).join(" · ")}</span></summary>
        <div class="fold-body">
          <p>${esc(a.description)}</p>
          ${(a.example_questions || []).map((q) => `<div class="qa">“${esc(q)}”</div>`).join("")}
          <p><b class="good">Strong answers:</b> ${esc(a.good)}</p>
          <p><b class="bad">Weak answers:</b> ${esc(a.bad)}</p>
          ${a.seniority ? `<p class="hint"><b>By seniority:</b> ${esc(a.seniority)}</p>` : ""}
        </div>
      </details>`).join("");
  } else if (tab === "concepts") {
    html = `<p class="hint" style="margin:0.3rem 0 0.7rem">Every concept below assumes you know
      <i>nothing</i> — because that's the honest starting point, and it's enough.</p>` +
      g.concepts.map((c) => `
      <details class="fold">
        <summary>${esc(c.name)}</summary>
        <div class="fold-body">
          <p>${esc(c.plain_english)}</p>
          <p class="hint"><b>Why interviews test it:</b> ${esc(c.why_asked)}</p>
          ${(c.green_flags || []).length ? `<p><b class="good">Green flags when candidates talk about it:</b></p><ul>${c.green_flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
          ${(c.red_flags || []).length ? `<p><b class="bad">Red flags:</b></p><ul>${c.red_flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
        </div>
      </details>`).join("");
  } else if (tab === "evaluation") {
    html = `<p class="hint" style="margin:0.3rem 0 0.7rem">You don't need to know the answer to
      judge one — you need the right follow-ups and the right ears.</p>` +
      g.evaluation.map((e) => `
      <details class="fold">
        <summary>${esc(e.name)}</summary>
        <div class="fold-body">
          <p>${esc(e.description)}</p>
          ${(e.probes || []).map((q) => `<div class="qa">“${esc(q)}”</div>`).join("")}
          <p><b class="good">What depth sounds like:</b> ${esc(e.good)}</p>
          <p><b class="bad">What rehearsed-but-shallow sounds like:</b> ${esc(e.bad)}</p>
        </div>
      </details>`).join("");
  } else if (tab === "resources") {
    const byConcept = {};
    g.resources.forEach((r) => (byConcept[r.topic] = byConcept[r.topic] || []).push(r));
    html = Object.entries(byConcept).map(([topic, rs]) => `
      <details class="fold">
        <summary>${esc(topic)} <span class="count">${rs.length} picks</span></summary>
        <div class="fold-body">
          ${rs.map((r) => `<div class="res-row">
            <span class="kind">${esc(r.kind)}</span>
            <span><a href="${esc(r.url)}" target="_blank" rel="noopener" class="guide-res" data-topic="${esc(topic)}">${esc(r.title)}</a>
              — <small>${esc(r.why)} (${esc(r.time)})</small></span>
          </div>`).join("")}
        </div>
      </details>`).join("");
  }
  $("guide").innerHTML = html || "<p class='hint'>The field guide is being stocked — the chat already works.</p>";
  $("guide").querySelectorAll("details.fold > summary").forEach((s) => {
    s.addEventListener("click", () => track("guide_opened", { tab, item: s.textContent.trim().slice(0, 60) }));
  });
  $("guide").querySelectorAll("a.guide-res").forEach((a) => {
    a.addEventListener("click", () => track("resource_opened", { url: a.href, topic: a.dataset.topic }));
  });
}

$("tabs").querySelectorAll("button").forEach((b) => {
  b.onclick = () => {
    tab = b.dataset.tab;
    $("tabs").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    track("tab_opened", { tab });
    renderGuide();
  };
});

(async () => {
  try {
    guide = await (await fetch("/api/recruiter/guide")).json();
    renderGuide();
  } catch {
    $("guide").innerHTML = "<p class='hint'>Couldn't load the field guide — refresh to retry.</p>";
  }
})();
