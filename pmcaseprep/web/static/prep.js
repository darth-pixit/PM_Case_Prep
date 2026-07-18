// Prep Engine (/prep): CV + JD -> story bank + target profile -> coverage
// heatmap -> STAR stories -> pressure-test until solid -> exportable prep pack.
//
// v1: the bank persists server-side (keyed by login), so the genome compounds
// across sessions and applications re-tune instantly. This file owns the UI
// state for ONE open application at a time; the bank is the source of truth.

(() => {
  const x = PMCP.experiment("prep");
  const $ = (id) => document.getElementById(id);
  const esc = PMCP.esc;

  const S = {
    units: [],            // the genome (bank rows)
    target: null, targetId: "",
    cells: [],
    stories: {},          // by competency: {id, story, solid}
    da: {},               // devil's advocate state by competency: {exchanges, attacks, verdicts}
    sprints: {},          // by competency
    twin: null,
    mock: { msgs: [], scorecard: null, running: false },
    debrief: null,
  };

  const LABELS = {
    "product-sense": "Product sense",
    "zero-to-one-shipping": "0→1 shipping",
    "execution-delivery": "Execution & delivery",
    "data-driven-decisions": "Data-driven decisions",
    "influence-without-authority": "Influence w/o authority",
    "stakeholder-exec-communication": "Stakeholder & exec comms",
    "strategy-prioritization": "Strategy & prioritization",
    "technical-fluency": "Technical fluency",
    "conflict-disagreement": "Conflict & disagreement",
    "leadership-mentorship": "Leadership & mentorship",
    "user-empathy-research": "User empathy & research",
    "metrics-experimentation": "Metrics & experimentation",
  };
  const COMPS = Object.keys(LABELS);
  const label = (c) => LABELS[c] || c;

  async function api(path, body, method) {
    const r = await fetch("/api/prep/" + path, body === undefined
      ? { method: method || "GET" }
      : { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!d.ok) throw new Error(d.error || "request failed (" + r.status + ")");
    return d;
  }

  function msg(id, text, bad) {
    const el = $(id);
    el.textContent = text || "";
    el.style.color = bad ? "var(--bad)" : "";
  }

  // --- Auth + bank load ------------------------------------------------------
  PMCP.mountAuth($("authMount"), {
    reason: "Sign in to run the engine — your story bank follows your account.",
    onLogin: async (email) => {
      $("whoami").textContent = email;
      $("builder").hidden = false;
      try { await loadBank(); } catch { /* bank loads lazily; build still works */ }
    },
  });

  async function loadBank() {
    const d = await api("bank");
    S.units = d.units;
    if (S.units.length) renderUnits();
    renderApps(d.targets);
    // Cards that only need the bank/genome:
    $("debriefCard").hidden = false;
  }

  function renderApps(targets) {
    if (!targets || !targets.length) { $("appsCard").hidden = true; return; }
    $("appsCard").hidden = false;
    $("appsOut").innerHTML = targets.map((t) => `
      <div class="app-row" data-id="${esc(t.id)}">
        <div class="who">
          <b>${esc(t.roleTitle)}</b> <span class="pill">${esc(t.company)}</span>
          <small class="hint">${esc(t.seniority)} · ${esc(t.archetype)}</small>
        </div>
        <span class="hm-mini"><i class="g">${t.green}</i>·<i class="a">${t.amber}</i>·<i class="r">${t.red}</i></span>
        <span class="pill ${t.solidStories ? "on" : ""}">${t.solidStories} solid ${t.solidStories === 1 ? "story" : "stories"}</span>
        <span class="act">
          <button class="btn small" data-open="${esc(t.id)}">Open</button>
          <button class="btn small ghost" data-del="${esc(t.id)}">✕</button>
        </span>
      </div>`).join("");
    $("appsOut").querySelectorAll("[data-open]").forEach((b) => {
      b.onclick = () => openApp(b.dataset.open);
    });
    $("appsOut").querySelectorAll("[data-del]").forEach((b) => {
      b.onclick = async () => {
        if (!confirm("Delete this application and its stories? Your story bank (units) is kept.")) return;
        try {
          await api("bank/target-delete", { id: b.dataset.del });
          if (S.targetId === b.dataset.del) resetTarget();
          await loadBank();
        } catch (e) { alert(e.message); }
      };
    });
  }

  function resetTarget() {
    S.target = null; S.targetId = ""; S.cells = []; S.stories = {}; S.da = {};
    S.sprints = {}; S.mock = { msgs: [], scorecard: null, running: false };
    ["targetCard", "heatmapCard", "storyCard", "twinCard", "mockCard"].forEach(
      (id) => { $(id).hidden = true; });
  }

  async function openApp(id) {
    try {
      const d = await api("bank/target?id=" + encodeURIComponent(id));
      S.target = d.target; S.targetId = d.id; S.cells = d.cells || [];
      S.stories = {}; S.da = {}; S.sprints = {}; S.twin = null;
      S.mock = { msgs: [], scorecard: null, running: false };
      (d.stories || []).forEach((row) => {
        S.stories[row.competency] = { id: row.id, story: row.story, solid: row.solid };
      });
      renderTarget();
      if (!$("spine").value.trim() && S.target.unwrittenPain) {
        $("spine").value = "I have repeatedly solved this exact pain: " + S.target.unwrittenPain;
      }
      if (S.cells.length) { renderHeatmap(); afterHeatmap(); }
      x.track("app_opened", { cells: S.cells.length });
      $("targetCard").scrollIntoView({ behavior: "smooth" });
    } catch (e) { alert(e.message); }
  }

  // --- The build loop --------------------------------------------------------
  $("buildBtn").onclick = async () => {
    const cv = $("cvText").value.trim();
    const jd = $("jdText").value.trim();
    if (!cv && !jd) { msg("buildMsg", "Paste your CV and the JD first.", true); return; }
    if (!jd) { msg("buildMsg", "Paste the JD too — the heatmap needs a target.", true); return; }
    $("buildBtn").disabled = true;
    x.track("build_started", { cv_chars: cv.length, jd_chars: jd.length });
    try {
      msg("buildMsg", cv ? "Extracting units + decoding the role…" : "Decoding the role…");
      const calls = [api("extract-target", { text: jd })];
      if (cv) calls.push(api("extract-units", { text: cv }));
      const [t, u] = await Promise.all(calls);
      if (u) S.units = u.units; // the merged genome, not just this extraction
      S.target = t.target; S.targetId = t.targetId;
      S.stories = {}; S.da = {}; S.sprints = {};
      if (S.units.length) renderUnits();
      renderTarget();
      if (S.target.unwrittenPain) {
        $("spine").value = "I have repeatedly solved this exact pain: " + S.target.unwrittenPain;
      }
      if (!S.units.length) {
        msg("buildMsg", "Role decoded. Paste a CV to build the heatmap.", true);
      } else {
        msg("buildMsg", "Scoring coverage…");
        const h = await api("heatmap", { units: S.units, target: S.target, targetId: S.targetId });
        S.cells = h.cells;
        renderHeatmap(); afterHeatmap();
        msg("buildMsg", "");
        x.track("heatmap_built", {
          units: S.units.length,
          green: S.cells.filter((c) => c.strength === "green").length,
          amber: S.cells.filter((c) => c.strength === "amber").length,
          red: S.cells.filter((c) => c.strength === "red").length,
        });
        $("heatmapCard").scrollIntoView({ behavior: "smooth" });
      }
      loadBank().catch(() => {});
    } catch (e) {
      msg("buildMsg", e.message, true);
      x.track("build_failed", { error: e.message });
    }
    $("buildBtn").disabled = false;
  };

  function afterHeatmap() {
    $("twinCard").hidden = false;
    $("mockCard").hidden = false;
    $("debriefCard").hidden = false;
  }

  // --- Target + units --------------------------------------------------------
  function renderTarget() {
    const t = S.target;
    $("targetCard").hidden = false;
    $("targetOut").innerHTML = `
      <p><b>${esc(t.roleTitle)}</b> · ${esc(t.seniority)} · ${esc(t.archetype)}
        &nbsp;<span class="pill">${esc(t.company)}</span></p>
      <div class="notice"><b>The unwritten pain:</b> ${esc(t.unwrittenPain)}</div>
      ${t.companyValues.length ? `<p class="hint">Values in play: ${t.companyValues.map((v) => `<span class="pill">${esc(v)}</span>`).join(" ")}</p>` : ""}`;
  }

  function renderUnits() {
    $("unitsCard").hidden = false;
    $("unitsHead").textContent = `Your story bank (${S.units.length} units)`;
    $("unitsOut").innerHTML = S.units.map((u, i) => `
      <div class="unit ${u.isFailure ? "fail" : ""}" data-i="${i}">
        <b>${esc(u.title)}</b> ${u.isFailure ? '<span class="pill hot">failure story — gold</span>' : ""}
        <small>${esc(u.context)}</small>
        <p>${esc(u.action)} → ${esc(u.result)}</p>
        <p class="metric">${u.metric ? "📈 " + esc(u.metric) : '<span class="nometric">no metric in source — none invented</span>'}</p>
        <div class="chips">${u.competencies.map((c) => `<span class="pill">${esc(label(c))}</span>`).join("")}</div>
        <details><summary>provenance</summary><blockquote>${esc(u.rawEvidence)}</blockquote></details>
        <div class="unit-act">
          <button class="btn small ghost" data-edit="${i}">✎ edit</button>
          <button class="btn small ghost" data-rm="${i}">delete</button>
        </div>
      </div>`).join("");
    $("unitsOut").querySelectorAll("[data-edit]").forEach((b) => {
      b.onclick = () => editUnit(+b.dataset.edit);
    });
    $("unitsOut").querySelectorAll("[data-rm]").forEach((b) => {
      b.onclick = async () => {
        const u = S.units[+b.dataset.rm];
        if (!confirm(`Delete "${u.title}" from your bank?`)) return;
        try {
          await api("bank/unit-delete", { id: u.id });
          S.units.splice(+b.dataset.rm, 1);
          renderUnits();
          x.track("unit_deleted");
        } catch (e) { alert(e.message); }
      };
    });
  }

  function editUnit(i) {
    const u = S.units[i];
    const card = $("unitsOut").querySelector(`[data-i="${i}"]`);
    const f = (name, val, ph) =>
      `<input data-f="${name}" type="text" value="${esc(val == null ? "" : val)}" placeholder="${ph}" />`;
    card.innerHTML = `
      <div class="unit-form">
        ${f("title", u.title, "title")}
        ${f("context", u.context, "context (company / team / when)")}
        <textarea data-f="action" rows="2" placeholder="what YOU did">${esc(u.action)}</textarea>
        <textarea data-f="result" rows="2" placeholder="outcome in words">${esc(u.result)}</textarea>
        ${f("metric", u.metric, "metric — leave empty if you don't have a number")}
        ${f("scale", u.scale, "scale (team size / users / $)")}
        ${f("skills", u.skills.join(", "), "skills, comma-separated")}
        <div class="chips">${COMPS.map((c) => `
          <label class="pill ${u.competencies.includes(c) ? "on" : ""}">
            <input type="checkbox" data-comp="${c}" ${u.competencies.includes(c) ? "checked" : ""} hidden>${esc(label(c))}
          </label>`).join("")}</div>
        <label class="hint"><input type="checkbox" data-f="isFailure" ${u.isFailure ? "checked" : ""}> failure / conflict story</label>
        <div class="unit-act">
          <button class="btn small" data-save="1">Save</button>
          <button class="btn small ghost" data-cancel="1">Cancel</button>
        </div>
      </div>`;
    card.querySelectorAll("label.pill").forEach((l) => {
      l.querySelector("input").addEventListener("change", (e) =>
        l.classList.toggle("on", e.target.checked));
    });
    card.querySelector("[data-cancel]").onclick = () => renderUnits();
    card.querySelector("[data-save]").onclick = async () => {
      const v = (name) => card.querySelector(`[data-f="${name}"]`).value.trim();
      const edited = {
        ...u,
        title: v("title") || u.title,
        context: v("context"),
        action: v("action"),
        result: v("result"),
        metric: v("metric") || null,
        scale: v("scale") || null,
        skills: v("skills") ? v("skills").split(",").map((s) => s.trim()).filter(Boolean) : [],
        competencies: [...card.querySelectorAll("[data-comp]:checked")].map((c) => c.dataset.comp),
        isFailure: card.querySelector('[data-f="isFailure"]').checked,
      };
      try {
        const d = await api("bank/units", { units: [edited] });
        S.units = d.units;
        renderUnits();
        x.track("unit_edited");
      } catch (e) { alert(e.message); }
    };
  }

  // --- Heatmap ---------------------------------------------------------------
  function weights() {
    return Object.fromEntries(S.target.requiredCompetencies.map((rc) => [rc.competency, rc.weight]));
  }

  function renderHeatmap() {
    $("heatmapCard").hidden = false;
    const weight = weights();
    const evidence = Object.fromEntries(
      S.target.requiredCompetencies.map((rc) => [rc.competency, rc.evidence]));
    const unitById = Object.fromEntries(S.units.map((u) => [u.id, u]));
    const cells = [...S.cells].sort((a, b) => (weight[b.competency] || 0) - (weight[a.competency] || 0));
    $("heatmapOut").innerHTML = `<table class="hm">
      <tr><th>competency</th><th>weight</th><th>coverage</th><th>your move</th></tr>
      ${cells.map((c) => {
        const u = c.bestUnitId ? unitById[c.bestUnitId] : null;
        const st = S.stories[c.competency];
        const move = c.strength === "red"
          ? `<span class="gap">${esc(c.gapAction || "")}</span>
             <button class="btn small ghost" data-sprint="${esc(c.competency)}">${S.sprints[c.competency] ? "View 2-week plan" : "2-week plan"}</button>`
          : `<button class="btn small" data-comp="${esc(c.competency)}">${st ? "View story" : "Draft story"}</button>
             ${st && st.solid ? '<span class="pill solid">✓ solid</span>' : ""}
             ${c.strength === "amber" && c.gapAction ? `<div class="gap hint">${esc(c.gapAction)}</div>` : ""}`;
        return `<tr>
          <td><b>${esc(label(c.competency))}</b><br><small class="hint" title="${esc(evidence[c.competency] || "")}">JD: “${esc((evidence[c.competency] || "").slice(0, 60))}${(evidence[c.competency] || "").length > 60 ? "…" : ""}”</small></td>
          <td class="w">${"●".repeat(weight[c.competency] || 0)}${"○".repeat(5 - (weight[c.competency] || 0))}</td>
          <td><span class="hm-cell ${c.strength}">${c.strength}</span>${u ? `<br><small class="hint">${esc(u.title)}${u.metric ? " · " + esc(u.metric) : ""}</small>` : ""}</td>
          <td>${move}</td>
        </tr>`;
      }).join("")}
    </table>`;
    $("heatmapOut").querySelectorAll("button[data-comp]").forEach((b) => {
      b.onclick = () => story(b.dataset.comp, b);
    });
    $("heatmapOut").querySelectorAll("button[data-sprint]").forEach((b) => {
      b.onclick = () => sprint(b.dataset.sprint, b);
    });
  }

  // --- Stories + Devil's Advocate + rehearse ---------------------------------
  async function story(comp, btn) {
    if (S.stories[comp]) { renderStory(comp); return; }
    btn.disabled = true; btn.textContent = "Drafting…";
    x.track("story_requested", { competency: comp });
    try {
      const cell = S.cells.find((c) => c.competency === comp);
      const tagged = S.units.filter((u) => u.competencies.includes(comp)).map((u) => u.id);
      const unitIds = tagged.length ? tagged : (cell && cell.bestUnitId ? [cell.bestUnitId] : []);
      const d = await api("story", {
        competency: comp, spine: $("spine").value.trim(),
        units: S.units, unitIds, targetId: S.targetId,
      });
      S.stories[comp] = { id: d.story.id, story: d.story, solid: false };
      renderStory(comp);
      renderHeatmap();
      x.track("story_built", { competency: comp, flags: d.story.unverifiedClaims.length });
    } catch (e) {
      btn.textContent = "Draft story";
      msg("exportMsg", e.message, true);
    }
    btn.disabled = false;
  }

  function renderStory(comp) {
    const rec = S.stories[comp];
    const st = rec.story;
    $("storyCard").hidden = false;
    $("storyHead").textContent = "Story — " + label(comp);
    const tabs = [["thirtySec", "30 seconds"], ["twoMin", "2 minutes"], ["deepDive", "Deep dive"]];
    $("storyOut").innerHTML = `
      <p class="hint">Spine: ${esc(st.spineTag)}
        ${rec.solid ? '<span class="pill solid">✓ solid</span>' : ""}</p>
      ${st.unverifiedClaims.length ? `
        <div class="claims"><b>⚠ Confirm before you say it</b>
          <ul>${st.unverifiedClaims.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
        </div>` : ""}
      <div class="tabs" id="storyTabs">${tabs.map(([k, t], i) =>
        `<button data-v="${k}" class="${i === 1 ? "on" : ""}">${t}</button>`).join("")}</div>
      <div class="story-body" id="storyBody"></div>
      <h3>Nasty follow-ups to pre-answer</h3>
      <ul>${st.anticipatedFollowups.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>`;
    const show = (k) => { $("storyBody").textContent = st.versions[k]; };
    $("storyTabs").querySelectorAll("button").forEach((b) => {
      b.onclick = () => {
        $("storyTabs").querySelectorAll("button").forEach((o) => o.classList.remove("on"));
        b.classList.add("on"); show(b.dataset.v);
      };
    });
    show("twoMin");
    renderAttack(comp);
    renderRehearse(comp);
    $("storyCard").scrollIntoView({ behavior: "smooth" });
  }

  function renderAttack(comp) {
    const rec = S.stories[comp];
    const da = S.da[comp] || (S.da[comp] = { exchanges: [], attacks: [], verdicts: [] });
    $("attackOut").innerHTML = `
      <h3>⚔ Pressure-test (Devil's Advocate)</h3>
      <p class="hint">It attacks; you answer; it judges and attacks again — until YOU
      mark the story solid. Bulletproof is your call, not the model's.</p>
      ${da.verdicts.length ? `<div id="verdicts">${da.verdicts.map((v) => `
        <div class="attack"><span class="pill ${v.verdict === "held" ? "held" : "cracked"}">${v.verdict}</span>
          <b>${esc(v.question)}</b><p class="hint">${esc(v.why)}</p></div>`).join("")}</div>` : ""}
      ${da.attacks.length ? `<div id="attacks">${da.attacks.map((a, i) => `
        <div class="attack">
          <b>${esc(a.question)}</b>
          <p class="hint">probes: ${esc(a.probes)} · strong answer: ${esc(a.strongAnswer)}</p>
          <textarea data-ans="${i}" rows="2" placeholder="Your answer — out loud first, then the gist"></textarea>
        </div>`).join("")}</div>` : ""}
      <div class="prep-actions">
        <button class="btn" id="attackBtn">${da.attacks.length ? "Judge my answers & attack again" : "Start the attack"}</button>
        <button class="btn ghost" id="solidBtn">${rec.solid ? "Un-mark solid" : "Mark story solid ✓"}</button>
        <span class="hint" id="attackMsg"></span>
      </div>`;
    $("attackBtn").onclick = async () => {
      const btn = $("attackBtn");
      btn.disabled = true;
      // Fold typed answers into the exchange history before the next round.
      $("attackOut").querySelectorAll("[data-ans]").forEach((t) => {
        const answer = t.value.trim();
        if (answer) da.exchanges.push({ question: da.attacks[+t.dataset.ans].question, answer });
      });
      msg("attackMsg", "The devil is thinking…");
      try {
        const d = await api("attack", {
          story: rec.story, units: S.units, exchanges: da.exchanges,
        });
        da.verdicts = d.round.verdicts; da.attacks = d.round.attacks;
        renderAttack(comp);
        x.track("attack_round", { competency: comp, exchanges: da.exchanges.length });
      } catch (e) { msg("attackMsg", e.message, true); }
      btn.disabled = false;
    };
    $("solidBtn").onclick = async () => {
      try {
        await api("bank/story-solid", { id: rec.id, solid: !rec.solid });
        rec.solid = !rec.solid;
        renderStory(comp); renderHeatmap();
        x.track("story_solid", { competency: comp, solid: rec.solid });
      } catch (e) { msg("attackMsg", e.message, true); }
    };
  }

  // Delivery self-check: dictate (where the browser can) or type, with an
  // honest timer — pace and fillers are computed, structure is judged.
  function renderRehearse(comp) {
    const st = S.stories[comp].story;
    const questions = ["Walk me through this story.", ...st.anticipatedFollowups];
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    $("rehearseOut").innerHTML = `
      <h3>🎙 Rehearse it aloud</h3>
      <p class="hint">Pick a question, hit start, answer out loud${SR ? " (this browser can transcribe as you speak)" : ""},
      hit stop. Pace and fillers are computed; structure gets one honest read.</p>
      <select id="rhQ">${questions.map((q) => `<option>${esc(q)}</option>`).join("")}</select>
      <textarea id="rhText" rows="4" style="margin-top:0.5rem" placeholder="${SR ? "Transcript appears here as you speak — or type/paste it." : "Type or paste what you said."}"></textarea>
      <div class="prep-actions">
        <button class="btn ghost" id="rhTimer">⏱ Start</button>
        <span class="hint" id="rhClock">0:00</span>
        <button class="btn" id="rhCheck">Check my delivery</button>
        <span class="hint" id="rhMsg"></span>
      </div>
      <div id="rhOut"></div>`;
    let t0 = null, tick = null, seconds = 0, rec = null;
    $("rhTimer").onclick = () => {
      if (t0 === null) {
        t0 = Date.now();
        $("rhTimer").textContent = "⏹ Stop";
        tick = setInterval(() => {
          const s = Math.floor((Date.now() - t0) / 1000);
          $("rhClock").textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
        }, 500);
        if (SR) {
          try {
            rec = new SR();
            rec.continuous = true; rec.interimResults = false; rec.lang = "en-US";
            rec.onresult = (e) => {
              for (let i = e.resultIndex; i < e.results.length; i++) {
                if (e.results[i].isFinal) $("rhText").value += e.results[i][0].transcript + " ";
              }
            };
            rec.start();
          } catch { rec = null; }
        }
      } else {
        seconds = (Date.now() - t0) / 1000;
        t0 = null; clearInterval(tick);
        if (rec) { try { rec.stop(); } catch { /* already stopped */ } rec = null; }
        $("rhTimer").textContent = "⏱ Start";
      }
    };
    $("rhCheck").onclick = async () => {
      const transcript = $("rhText").value.trim();
      if (!transcript) { msg("rhMsg", "Say (or type) an answer first.", true); return; }
      if (t0 !== null) $("rhTimer").click(); // auto-stop a running timer
      $("rhCheck").disabled = true;
      msg("rhMsg", "Listening back…");
      try {
        const d = await api("delivery", {
          question: $("rhQ").value, transcript, seconds,
        });
        const s = d.stats, c = d.check;
        $("rhOut").innerHTML = `
          <div class="notice">
            <b>${s.wpm ? s.wpm + " wpm" : s.words + " words"}</b>
            ${s.wpm ? (s.wpm > 175 ? "— slow down." : s.wpm < 110 ? "— you can push the pace." : "— good pace.") : "(use the timer for pace)"}
            · fillers: ${s.coreFillers} hard, ${s.softFillers} soft
          </div>
          <p><b>Structure:</b> ${esc(c.structure)}</p>
          <p><b>Answered the question:</b> ${c.answered ? "yes" : "<span style='color:var(--bad)'>no</span>"} — ${esc(c.answeredNote)}</p>
          ${c.cuts.length ? `<p><b>Cut these:</b> ${c.cuts.map((q) => `<span class="pill">${esc(q)}</span>`).join(" ")}</p>` : ""}
          <p><b>Strongest 2-sentence version:</b></p>
          <div class="story-body">${esc(c.rewrite)}</div>`;
        msg("rhMsg", "");
        x.track("rehearse_checked", { wpm: s.wpm, fillers: s.coreFillers });
      } catch (e) { msg("rhMsg", e.message, true); }
      $("rhCheck").disabled = false;
    };
  }

  // --- Gap-to-Sprint ---------------------------------------------------------
  async function sprint(comp, btn) {
    if (S.sprints[comp]) { renderSprint(comp); return; }
    btn.disabled = true; btn.textContent = "Planning…";
    try {
      const cell = S.cells.find((c) => c.competency === comp);
      const d = await api("sprint", {
        competency: comp, gapAction: cell ? cell.gapAction : "", target: S.target,
      });
      S.sprints[comp] = d.sprint;
      renderSprint(comp);
      renderHeatmap();
      x.track("sprint_built", { competency: comp });
    } catch (e) {
      btn.disabled = false; btn.textContent = "2-week plan";
      msg("exportMsg", e.message, true);
    }
  }

  function renderSprint(comp) {
    const sp = S.sprints[comp];
    $("sprintOut").innerHTML = `
      <div class="notice">
        <b>🏃 2-week plan — ${esc(label(comp))}</b>
        <p>${esc(sp.goal)}</p>
        <table class="hm">${sp.milestones.map((m) => `
          <tr><td class="w" style="white-space:nowrap">${esc(m.days)}</td>
              <td>${esc(m.task)}</td><td class="hint">${esc(m.output)}</td></tr>`).join("")}
        </table>
        <p><b>Deliverable:</b> ${esc(sp.deliverable)} · <b>Proof metric:</b> ${esc(sp.proofMetric)}</p>
        <p class="hint">Once done, this becomes a true unit: “${esc(sp.unitOutline)}”</p>
      </div>`;
    $("sprintOut").scrollIntoView({ behavior: "smooth" });
  }

  // --- Interviewer twin ------------------------------------------------------
  $("twinBtn").onclick = async () => {
    const name = $("twinName").value.trim();
    const signals = $("twinSignals").value.trim();
    if (!name || !signals) { msg("twinMsg", "Name + pasted public signals, please.", true); return; }
    $("twinBtn").disabled = true;
    msg("twinMsg", "Reading the signals…");
    try {
      const d = await api("interviewer", {
        name, role: $("twinRole").value.trim(), signals, target: S.target,
      });
      S.twin = d.twin;
      const t = d.twin;
      $("twinOut").innerHTML = `
        <div class="notice"><b>${esc(t.profile.name)}</b> · ${esc(t.profile.role)}
          <p class="hint">${esc(t.rationale)}</p></div>
        <p><b>They'll probably probe:</b> ${t.profile.likelyFocus.map((c) => `<span class="pill">${esc(label(c))}</span>`).join(" ")}</p>
        <p><b>Signals used:</b></p>
        <ul>${t.profile.publicSignals.map((s) => `<li class="hint">${esc(s)}</li>`).join("")}</ul>
        <p><b>Questions to expect:</b></p>
        <ul>${t.predictedQuestions.map((q) => `<li>${esc(q.question)} <span class="pill">${esc(label(q.competency))}</span></li>`).join("")}</ul>
        <p><b>Tune your stories:</b></p>
        <ul>${t.prepTips.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;
      msg("twinMsg", "");
      x.track("twin_built", { questions: t.predictedQuestions.length });
    } catch (e) { msg("twinMsg", e.message, true); }
    $("twinBtn").disabled = false;
  };

  // --- Mock interview --------------------------------------------------------
  const MOCK_CAP = 8;

  function mockBubble(role, text) {
    const el = document.createElement("div");
    el.className = "msg " + (role === "user" ? "user" : "bot");
    el.textContent = text;
    $("mockChat").appendChild(el);
    el.scrollIntoView({ behavior: "smooth" });
  }

  async function mockTurn() {
    const thinking = document.createElement("div");
    thinking.className = "msg bot thinking";
    thinking.textContent = "…";
    $("mockChat").appendChild(thinking);
    try {
      const d = await api("mock", { messages: S.mock.msgs, target: S.target, cells: S.cells });
      thinking.remove();
      S.mock.msgs.push({ role: "assistant", text: d.reply });
      mockBubble("assistant", d.reply);
      const asked = S.mock.msgs.filter((m) => m.role === "assistant").length;
      msg("mockMsg", `question ${Math.min(asked, MOCK_CAP)} of ${MOCK_CAP}`);
      if (asked >= MOCK_CAP + 1) endMock(); // the +1th is the wrap-up line
    } catch (e) {
      thinking.remove();
      msg("mockMsg", e.message, true);
    }
  }

  $("mockStart").onclick = async () => {
    if (!S.cells.length) { msg("mockMsg", "Build the heatmap first.", true); return; }
    S.mock = { msgs: [], scorecard: null, running: true };
    $("mockChat").innerHTML = ""; $("mockScoreOut").innerHTML = "";
    $("mockCompose").hidden = false; $("mockEnd").hidden = false;
    $("mockStart").disabled = true;
    x.track("mock_started");
    await mockTurn();
  };

  $("mockSend").onclick = async () => {
    const text = $("mockInput").value.trim();
    if (!text || !S.mock.running) return;
    $("mockInput").value = "";
    S.mock.msgs.push({ role: "user", text });
    mockBubble("user", text);
    await mockTurn();
  };
  $("mockInput") && $("mockInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("mockSend").click(); }
  });

  async function endMock() {
    if (!S.mock.msgs.some((m) => m.role === "user")) {
      msg("mockMsg", "Answer at least one question first.", true);
      return;
    }
    S.mock.running = false;
    $("mockCompose").hidden = true; $("mockEnd").hidden = true;
    msg("mockMsg", "Grading…");
    try {
      const d = await api("mock-score", { messages: S.mock.msgs, target: S.target });
      S.mock.scorecard = d.scorecard;
      const sc = d.scorecard;
      $("mockScoreOut").innerHTML = `
        <h3>Scorecard</h3>
        <table class="hm">${sc.scores.map((s) => `
          <tr><td><b>${esc(label(s.competency))}</b></td>
              <td class="w">${"★".repeat(s.score)}${"☆".repeat(4 - s.score)}</td>
              <td class="hint">${esc(s.justification)}</td></tr>`).join("")}
        </table>
        <div class="notice"><b>Highest-leverage fix:</b> ${esc(sc.topImprovement)}</div>
        ${sc.pressureTestNext.length ? `<p><b>Pressure-test next:</b> ${sc.pressureTestNext.map((c) => `<span class="pill">${esc(label(c))}</span>`).join(" ")}</p>` : ""}`;
      msg("mockMsg", "");
      $("mockStart").disabled = false;
      $("mockStart").textContent = "Run another mock";
      x.track("mock_graded", { scores: sc.scores.length });
    } catch (e) { msg("mockMsg", e.message, true); $("mockStart").disabled = false; }
  }
  $("mockEnd").onclick = endMock;

  // --- Debrief -> write-back -------------------------------------------------
  $("debriefBtn").onclick = async () => {
    const notes = $("debriefText").value.trim();
    if (!notes) { msg("debriefMsg", "Write the debrief first.", true); return; }
    if (!S.target) { msg("debriefMsg", "Open the application this interview was for.", true); return; }
    $("debriefBtn").disabled = true;
    msg("debriefMsg", "Mining it…");
    try {
      const d = await api("debrief", { notes, target: S.target, targetId: S.targetId });
      S.debrief = d.insights;
      const ins = d.insights;
      $("debriefOut").innerHTML = `
        <h3>Lessons</h3>
        <ul>${ins.lessons.map((l) => `<li><b>${esc(l.lesson)}</b> — ${esc(l.adjustment)}</li>`).join("")}</ul>
        ${ins.focusNext.length ? `<p><b>Drill before the next round:</b> ${ins.focusNext.map((f) => `<span class="pill" title="${esc(f.why)}">${esc(label(f.competency))}</span>`).join(" ")}</p>` : ""}
        ${ins.suggestedUnits.length ? `
          <h3>Draft units mined from your debrief</h3>
          <p class="hint">You mentioned these — confirm what's true and add it to the bank.
          Metrics you didn't write were already stripped.</p>
          <div class="unit-grid">${ins.suggestedUnits.map((u, i) => `
            <div class="unit">
              <b>${esc(u.title)}</b>
              <p>${esc(u.action)} → ${esc(u.result)}</p>
              <p class="metric">${u.metric ? "📈 " + esc(u.metric) : '<span class="nometric">no metric</span>'}</p>
              <div class="chips">${u.competencies.map((c) => `<span class="pill">${esc(label(c))}</span>`).join("")}</div>
              <details><summary>from your debrief</summary><blockquote>${esc(u.rawEvidence)}</blockquote></details>
              <div class="unit-act"><button class="btn small" data-add="${i}">✓ True — add to bank</button></div>
            </div>`).join("")}</div>` : ""}`;
      $("debriefOut").querySelectorAll("[data-add]").forEach((b) => {
        b.onclick = async () => {
          const u = { ...ins.suggestedUnits[+b.dataset.add] };
          delete u.id; // the bank assigns identity, not the model
          try {
            const r = await api("bank/units", { units: [{ ...u, id: "" }] });
            S.units = r.units;
            renderUnits();
            b.textContent = "Added ✓"; b.disabled = true;
            x.track("debrief_unit_added");
          } catch (e) { alert(e.message); }
        };
      });
      msg("debriefMsg", "");
      x.track("debrief_mined", { lessons: ins.lessons.length, drafts: ins.suggestedUnits.length });
    } catch (e) { msg("debriefMsg", e.message, true); }
    $("debriefBtn").disabled = false;
  };

  // --- Export: one markdown prep pack the user keeps -------------------------
  $("exportBtn").onclick = () => {
    if (!S.target) { msg("exportMsg", "Build the heatmap first.", true); return; }
    const t = S.target;
    const unitById = Object.fromEntries(S.units.map((u) => [u.id, u]));
    const weight = weights();
    const L = [];
    L.push(`# Prep pack — ${t.roleTitle} @ ${t.company}`);
    L.push("");
    L.push(`*${t.seniority} · ${t.archetype} · generated by Prep Engine*`);
    L.push("");
    L.push(`**The unwritten pain behind this hire:** ${t.unwrittenPain}`);
    if (t.companyValues.length) L.push(`\n**Values in play:** ${t.companyValues.join(", ")}`);
    L.push("\n## Coverage heatmap\n");
    L.push("| competency | weight | coverage | best evidence | gap action |");
    L.push("|---|---|---|---|---|");
    [...S.cells]
      .sort((a, b) => (weight[b.competency] || 0) - (weight[a.competency] || 0))
      .forEach((c) => {
        const u = c.bestUnitId ? unitById[c.bestUnitId] : null;
        L.push(`| ${label(c.competency)} | ${weight[c.competency] || "?"}/5 | ${c.strength.toUpperCase()} | ${u ? u.title + (u.metric ? ` (${u.metric})` : "") : "—"} | ${c.gapAction || "—"} |`);
      });
    const told = Object.entries(S.stories);
    if (told.length) {
      L.push("\n## Stories\n");
      told.forEach(([comp, rec]) => {
        const st = rec.story;
        L.push(`### ${label(comp)}${rec.solid ? " ✓ (pressure-tested solid)" : ""}`);
        L.push(`*Spine: ${st.spineTag}*\n`);
        if (st.unverifiedClaims.length) {
          L.push("> ⚠ **Confirm before you say it:**");
          st.unverifiedClaims.forEach((c) => L.push(`> - ${c}`));
          L.push("");
        }
        L.push(`**30 seconds**\n\n${st.versions.thirtySec}\n`);
        L.push(`**2 minutes**\n\n${st.versions.twoMin}\n`);
        L.push(`**Deep dive**\n\n${st.versions.deepDive}\n`);
        L.push("**Anticipated follow-ups**\n");
        st.anticipatedFollowups.forEach((q) => L.push(`- ${q}`));
        L.push("");
      });
    }
    const sprints = Object.entries(S.sprints);
    if (sprints.length) {
      L.push("\n## Close-the-gap sprints\n");
      sprints.forEach(([comp, sp]) => {
        L.push(`### ${label(comp)} — 2 weeks`);
        L.push(`${sp.goal}\n`);
        sp.milestones.forEach((m) => L.push(`- **${m.days}:** ${m.task} → ${m.output}`));
        L.push(`\n**Deliverable:** ${sp.deliverable} · **Proof metric:** ${sp.proofMetric}\n`);
      });
    }
    if (S.twin) {
      L.push("\n## Interviewer twin (from public signals you pasted)\n");
      L.push(`**${S.twin.profile.name}** · ${S.twin.profile.role} — likely focus: ${S.twin.profile.likelyFocus.map(label).join(", ")}\n`);
      S.twin.predictedQuestions.forEach((q) => L.push(`- ${q.question} *(${label(q.competency)})*`));
      L.push("");
      S.twin.prepTips.forEach((p) => L.push(`- Tip: ${p}`));
    }
    if (S.mock.scorecard) {
      L.push("\n## Mock interview scorecard\n");
      S.mock.scorecard.scores.forEach((s) =>
        L.push(`- **${label(s.competency)}: ${s.score}/4** — ${s.justification}`));
      L.push(`\n**Highest-leverage fix:** ${S.mock.scorecard.topImprovement}`);
    }
    L.push("\n## Appendix — story bank (with provenance)\n");
    S.units.forEach((u) => {
      L.push(`### ${u.title}${u.isFailure ? " *(failure story)*" : ""}`);
      L.push(`- **Context:** ${u.context}`);
      L.push(`- **Action:** ${u.action}`);
      L.push(`- **Result:** ${u.result}`);
      L.push(`- **Metric:** ${u.metric || "none in source (none invented)"}`);
      if (u.scale) L.push(`- **Scale:** ${u.scale}`);
      L.push(`- **Competencies:** ${u.competencies.map(label).join(", ")}`);
      L.push(`- **Source:** “${u.rawEvidence}”`);
      L.push("");
    });
    const blob = new Blob([L.join("\n")], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `prep-pack-${(t.company || "role").toLowerCase().replace(/[^a-z0-9]+/g, "-")}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
    msg("exportMsg", "Downloaded.");
    x.track("pack_exported", { stories: told.length, units: S.units.length });
  };
})();
