// Prep Engine (/prep and /prep-ds): fine-tune how your CV points READ +
// shape your own intro story — both through the role family's hiring lens.
//
// The job description is OPTIONAL by design: decode one when there's a
// specific opening; otherwise pick (or skip) an archetype + seniority and
// prep for the role in general.
//
// One script, two tracks. The page sets window.PREP_TRACK ("pm" default,
// "ds" on /prep-ds); the track picks the analytics namespace, the question
// wording, the pickers, and rides along on every call so the server prompts
// with the right hiring lens. The server persists the latest review + story
// kit per (login, track); this file restores them on login.

(() => {
  const TRACK = window.PREP_TRACK === "ds" ? "ds" : "pm";
  const x = PMCP.experiment(TRACK === "ds" ? "prep-ds" : "prep");
  const $ = (id) => document.getElementById(id);
  const esc = PMCP.esc;

  const UI = {
    pm: {
      whyRoleHead: "Why product?",
      seniorities: ["APM", "PM", "Senior", "Group", "Director"],
      archetypes: ["Growth", "Platform", "0-to-1", "Data", "AI", "Core"],
      questions: [
        { key: "spark", label: "What pulled you into product work?",
          ph: "The actual moment or project — not a philosophy. e.g. “I was the engineer who kept rewriting the spec, until someone let me own it…”" },
        { key: "drive", label: "Why do you do what you do?",
          ph: "The problems you keep coming back to — at work or outside it." },
        { key: "proud", label: "The work you're proudest of — and what did it change?",
          ph: "One or two moments. What was broken, what you did, what happened after." },
        { key: "now", label: "Why this role (or this kind of role), and why now?",
          ph: "What you want more of, what you want less of, and why this is the next chapter." },
        { key: "next", label: "What are you deliberately getting better at?",
          ph: "The edge you're building. Honest beats polished." },
      ],
      cvPh: "Paste your CV — or just the bullet points. e.g. Led checkout revamp at Acme (team of 6). Cut drop-off 18%. Also: the failed loyalty launch I killed after 2 sprints…",
    },
    ds: {
      whyRoleHead: "Why data science?",
      seniorities: ["Junior", "Mid", "Senior", "Staff", "Principal", "Lead"],
      archetypes: ["Product Analytics", "Experimentation", "ML & Modeling",
                   "GenAI & LLM", "Platform & Infra", "Decision Science"],
      questions: [
        { key: "spark", label: "What pulled you into data science?",
          ph: "The actual moment — the first question you HAD to answer with data." },
        { key: "drive", label: "Why do you do what you do?",
          ph: "The kinds of questions you keep coming back to." },
        { key: "proud", label: "The work you're proudest of — and what did it change?",
          ph: "What was unknown or broken, what you did, what decision or metric moved." },
        { key: "now", label: "Why this role (or this kind of role), and why now?",
          ph: "What you want more of, what you want less of, and why this is the next chapter." },
        { key: "next", label: "What are you deliberately getting better at?",
          ph: "The edge you're building. Honest beats polished." },
      ],
      cvPh: "Paste your CV — or just the bullet points. e.g. Built churn model at Acme (XGBoost, 2M users) — recall up 22% over the rules baseline. Ran the checkout A/B program…",
    },
  }[TRACK];

  const ISSUE_LABELS = {
    "vague-verb": "vague verb",
    "activity-not-outcome": "activity, not outcome",
    "feature-not-problem": "feature, not problem",
    "missing-scope": "no scope",
    "missing-user": "no user",
    "no-evidence": "no evidence",
    "buried-lede": "buried lede",
    "jargon": "jargon",
    "laundry-list": "laundry list",
    "no-ownership": "ownership unclear",
    "reads-junior": "reads junior",
    "too-long": "too long",
  };

  // Competency labels for the decoded-target chips (both tracks: the schema
  // is shared, the page shows whatever the decode returns for its track).
  const COMP_LABELS = {
    "product-sense": "Product sense", "zero-to-one-shipping": "0→1 shipping",
    "execution-delivery": "Execution & delivery", "data-driven-decisions": "Data-driven decisions",
    "influence-without-authority": "Influence w/o authority",
    "stakeholder-exec-communication": "Stakeholder & exec comms",
    "strategy-prioritization": "Strategy & prioritization", "technical-fluency": "Technical fluency",
    "conflict-disagreement": "Conflict & disagreement", "leadership-mentorship": "Leadership & mentorship",
    "user-empathy-research": "User empathy & research", "metrics-experimentation": "Metrics & experimentation",
    "sql-data-wrangling": "SQL & data wrangling", "statistics-probability": "Statistics & probability",
    "ml-fundamentals": "ML fundamentals", "experiment-design": "Experiment design & A/B",
    "product-metrics-sense": "Product & metrics sense", "ml-system-design": "ML system design",
    "genai-llm-fluency": "GenAI & LLM fluency", "coding-engineering-rigor": "Coding & engineering rigor",
    "data-storytelling": "Data storytelling", "stakeholder-influence": "Stakeholder influence",
    "project-ownership": "Project ownership", "business-impact": "Business impact",
  };

  const S = {
    mode: "general",   // "general" (no JD — the default) | "jd" (specific opening)
    target: null,      // decoded TargetProfile when mode === "jd"
    review: null,      // the latest CVReview
    kit: null,         // the latest StoryKit
  };

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

  const roleHint = () => (S.mode === "jd" ? {} : {
    seniority: $("seniority").value,
    archetype: $("archetype").value,
  });
  const targetForCall = () => (S.mode === "jd" ? S.target : null);

  // [ADD: …] placeholders are the truthfulness contract made visible — the
  // engine marks what YOU must fill with a real value, instead of inventing.
  const markAdds = (text) =>
    esc(text).replace(/\[ADD:[^\]]*\]/gi, (m) => `<mark class="add">${m}</mark>`);

  // --- Static chrome ---------------------------------------------------------

  $("seniority").innerHTML =
    `<option value="">Any seniority</option>` +
    UI.seniorities.map((s) => `<option>${esc(s)}</option>`).join("");
  $("archetype").innerHTML =
    `<option value="">Any archetype</option>` +
    UI.archetypes.map((a) => `<option>${esc(a)}</option>`).join("");
  $("cvText").placeholder = UI.cvPh;
  $("questionsOut").innerHTML = UI.questions.map((q) => `
    <div class="qa">
      <label for="q_${q.key}">${esc(q.label)}</label>
      <textarea id="q_${q.key}" rows="3" placeholder="${esc(q.ph)}"></textarea>
    </div>`).join("");

  // --- Auth + restore --------------------------------------------------------

  PMCP.mountAuth($("authMount"), {
    reason: "Sign in — your tuned CV and your story follow your account.",
    onLogin: async (email) => {
      $("whoami").textContent = email;
      ["whoFor", "cvCard", "storyCard"].forEach((id) => { $(id).hidden = false; });
      try { await loadBank(); } catch { /* restore is best-effort; building still works */ }
    },
  });

  async function loadBank() {
    const d = await api("bank?track=" + TRACK);
    if (d.review) {
      $("cvText").value = d.review.cvText || "";
      restoreTargeting(d.review);
      S.review = d.review.review || null;
      if (S.review) renderReview();
    }
    if (d.story) {
      const byLabel = {};
      (d.story.answers || []).forEach((a) => { byLabel[a.question] = a.answer; });
      UI.questions.forEach((q) => {
        if (byLabel[q.label]) $("q_" + q.key).value = byLabel[q.label];
      });
      if (!d.review) restoreTargeting(d.story);
      S.kit = d.story.kit || null;
      if (S.kit) renderKit();
    }
    if (d.review || d.story) x.track("prep_restored", {
      review: !!d.review, story: !!d.story,
    });
  }

  function restoreTargeting(doc) {
    if (doc.target) {
      S.target = doc.target;
      setMode("jd");
      renderTarget();
    } else if (doc.roleHint) {
      $("seniority").value = doc.roleHint.seniority || "";
      $("archetype").value = doc.roleHint.archetype || "";
    }
  }

  // --- Who are you presenting to? (the JD is optional — that's the point) ----

  function setMode(mode) {
    S.mode = mode;
    document.querySelectorAll('input[name="mode"]').forEach((r) => {
      r.checked = r.value === mode;
    });
    $("generalPick").hidden = mode !== "general";
    $("jdPick").hidden = mode !== "jd";
  }

  document.querySelectorAll('input[name="mode"]').forEach((r) => {
    r.onchange = () => {
      setMode(r.value);
      x.track("prep_mode_picked", { mode: r.value });
    };
  });

  $("decodeBtn").onclick = async () => {
    const text = $("jdText").value.trim();
    if (!text) { msg("decodeMsg", "paste the job description first", true); return; }
    $("decodeBtn").disabled = true;
    msg("decodeMsg", "reading between the lines…");
    try {
      const d = await api("target", { track: TRACK, text });
      S.target = d.target;
      renderTarget();
      msg("decodeMsg", "");
      x.track("prep_target_decoded", { archetype: d.target.archetype });
    } catch (e) {
      msg("decodeMsg", e.message, true);
    } finally {
      $("decodeBtn").disabled = false;
    }
  };

  function renderTarget() {
    const t = S.target;
    if (!t) { $("targetOut").innerHTML = ""; return; }
    const comps = (t.requiredCompetencies || [])
      .slice().sort((a, b) => b.weight - a.weight).slice(0, 6);
    $("targetOut").innerHTML = `
      <div class="target-sum">
        <p><b>${esc(t.roleTitle)}</b>${t.company ? " @ " + esc(t.company) : ""}
          <span class="pill">${esc(t.seniority)}</span>
          <span class="pill">${esc(t.archetype)}</span>
          <a href="#" id="clearTarget" class="hint">clear</a></p>
        <p class="hint">The unwritten pain behind the hire: ${esc(t.unwrittenPain)}</p>
        <p class="chips">${comps.map((c) =>
          `<span class="chip">${esc(COMP_LABELS[c.competency] || c.competency)} ·
           ${"★".repeat(c.weight)}</span>`).join(" ")}</p>
      </div>`;
    $("clearTarget").onclick = (e) => {
      e.preventDefault();
      S.target = null;
      $("targetOut").innerHTML = "";
      $("jdText").value = "";
    };
  }

  // --- Fine-tune the CV points ----------------------------------------------

  $("reviewBtn").onclick = async () => {
    const cvText = $("cvText").value.trim();
    if (!cvText) { msg("reviewMsg", "paste your CV first", true); return; }
    if (S.mode === "jd" && !S.target) {
      msg("reviewMsg", "decode the JD first — or switch to “a role in general”", true);
      return;
    }
    $("reviewBtn").disabled = true;
    msg("reviewMsg", "reading your CV the way a screener will…");
    try {
      const d = await api("review", {
        track: TRACK, cvText, target: targetForCall(), roleHint: roleHint(),
      });
      S.review = d.review;
      renderReview();
      msg("reviewMsg", "");
      x.track("prep_review_built", {
        points: d.review.points.length, jd: !!targetForCall(),
      });
    } catch (e) {
      msg("reviewMsg", e.message, true);
    } finally {
      $("reviewBtn").disabled = false;
    }
  };

  function renderReview() {
    const rv = S.review;
    if (!rv) { $("overallOut").innerHTML = ""; $("pointsOut").innerHTML = ""; return; }
    const o = rv.overall || {};
    const list = (items) => items && items.length
      ? `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`
      : "";
    $("overallOut").innerHTML = `
      <div class="overall">
        ${o.readsAs ? `<h3>How you come across today</h3><p>${esc(o.readsAs)}</p>` : ""}
        ${o.leadWith && o.leadWith.length ? `<h3>Lead with</h3>${list(o.leadWith)}` : ""}
        ${o.cut && o.cut.length ? `<h3>Cut or merge</h3>${list(o.cut)}` : ""}
        ${o.missing && o.missing.length ? `<h3>Honest gaps — go gather, don't spin</h3>${list(o.missing)}` : ""}
        ${o.ordering ? `<h3>Ordering</h3><p>${esc(o.ordering)}</p>` : ""}
      </div>`;
    $("pointsOut").innerHTML = rv.points.map((p) => `
      <div class="point">
        <blockquote>${esc(p.original)}</blockquote>
        <p class="reads"><b>How it reads:</b> ${esc(p.read)}</p>
        ${p.issues.length ? `<p class="chips">${p.issues.map((i) =>
          `<span class="chip issue">${esc(ISSUE_LABELS[i] || i)}</span>`).join(" ")}</p>` : ""}
        <p class="stronger"><b>Stronger:</b> ${markAdds(p.rewrite)}</p>
        <p class="hint">${esc(p.why)}</p>
        ${p.flags.length ? `<div class="claims"><b>Check before you use it</b>
          <ul>${p.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></div>` : ""}
      </div>`).join("");
    $("clearReviewBtn").hidden = false;
    $("exportCard").hidden = false;
  }

  $("clearReviewBtn").onclick = async () => {
    if (!confirm("Clear your saved CV review? Your story kit is kept.")) return;
    try {
      await api("bank/clear", { track: TRACK, kind: "review" });
      S.review = null;
      renderReview();
      $("clearReviewBtn").hidden = true;
      $("exportCard").hidden = !S.kit;
      x.track("prep_cleared", { kind: "review" });
    } catch (e) { msg("reviewMsg", e.message, true); }
  };

  // --- The intro story -------------------------------------------------------

  const collectAnswers = () => UI.questions
    .map((q) => ({ question: q.label, answer: $("q_" + q.key).value.trim() }))
    .filter((a) => a.answer);

  async function buildStory(prior, note, msgId) {
    const answers = collectAnswers();
    if (!answers.length) {
      msg(msgId, "answer at least one question first — any one of them", true);
      return;
    }
    if (S.mode === "jd" && !S.target) {
      msg(msgId, "decode the JD first — or switch to “a role in general”", true);
      return;
    }
    $("storyBtn").disabled = true; $("refineBtn").disabled = true;
    msg(msgId, prior ? "revising your story…" : "shaping your story…");
    try {
      const d = await api("story", {
        track: TRACK, answers, cvText: $("cvText").value.trim(),
        target: targetForCall(), roleHint: roleHint(),
        prior: prior || undefined, note: note || undefined,
      });
      S.kit = d.kit;
      renderKit();
      msg(msgId, "");
      x.track(prior ? "prep_story_refined" : "prep_story_built", {
        answers: answers.length, jd: !!targetForCall(),
      });
    } catch (e) {
      msg(msgId, e.message, true);
    } finally {
      $("storyBtn").disabled = false; $("refineBtn").disabled = false;
    }
  }

  $("storyBtn").onclick = () => buildStory(null, "", "storyMsg");
  $("refineBtn").onclick = () => {
    buildStory(S.kit, $("refineNote").value.trim(), "refineMsg");
  };

  function renderKit() {
    const k = S.kit;
    if (!k) { $("kitOut").innerHTML = ""; return; }
    const whyThisHead = S.target ? "Why this role" : "Why this kind of role";
    $("kitOut").innerHTML = `
      <p class="spine">${esc(k.throughLine)}</p>
      <h3>Tell me about yourself <span class="hint">(60–90s spoken)</span></h3>
      <div class="story-body">${markAdds(k.tellMe)}</div>
      <h3>${esc(UI.whyRoleHead)}</h3>
      <div class="story-body">${markAdds(k.whyRole)}</div>
      <h3>${whyThisHead}</h3>
      <div class="story-body">${markAdds(k.whyThis)}</div>
      ${k.beats.length ? `<h3>The beats <span class="hint">(adapt live — don't memorize)</span></h3>
        <ol class="beats">${k.beats.map((b) => `<li>${markAdds(b)}</li>`).join("")}</ol>` : ""}
      ${k.tips.length ? `<h3>Delivery</h3>
        <ul class="beats">${k.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      ${k.flags.length ? `<div class="claims"><b>Check before you say it</b>
        <ul>${k.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></div>` : ""}`;
    $("refineRow").hidden = false;
    $("clearStoryBtn").hidden = false;
    $("exportCard").hidden = false;
  }

  $("clearStoryBtn").onclick = async () => {
    if (!confirm("Clear your saved story kit? Your CV review is kept.")) return;
    try {
      await api("bank/clear", { track: TRACK, kind: "story" });
      S.kit = null;
      renderKit();
      $("refineRow").hidden = true;
      $("clearStoryBtn").hidden = true;
      $("exportCard").hidden = !S.review;
      x.track("prep_cleared", { kind: "story" });
    } catch (e) { msg("storyMsg", e.message, true); }
  };

  // --- Export (client-side .md — nothing extra leaves the browser) -----------

  $("exportBtn").onclick = () => {
    const L = [];
    const t = S.target;
    L.push(`# Prep sheet — ${TRACK === "ds" ? "Data Science" : "Product Management"}`);
    L.push(t ? `Target: ${t.roleTitle}${t.company ? " @ " + t.company : ""} (${t.seniority} · ${t.archetype})`
             : "Target: the role in general");
    if (S.review) {
      const o = S.review.overall || {};
      L.push("", "## Your CV, tuned");
      if (o.readsAs) L.push("", `**How you come across today:** ${o.readsAs}`);
      if (o.ordering) L.push("", `**Ordering:** ${o.ordering}`);
      if (o.missing && o.missing.length) {
        L.push("", "**Honest gaps to close (gather, don't spin):**");
        o.missing.forEach((m) => L.push(`- ${m}`));
      }
      S.review.points.forEach((p) => {
        L.push("", `### ${p.original}`);
        L.push(`- How it reads: ${p.read}`);
        if (p.issues.length) L.push(`- Issues: ${p.issues.map((i) => ISSUE_LABELS[i] || i).join(", ")}`);
        L.push(`- Stronger: ${p.rewrite}`);
        L.push(`- Why: ${p.why}`);
        p.flags.forEach((f) => L.push(`- ⚠ ${f}`));
      });
    }
    if (S.kit) {
      const k = S.kit;
      L.push("", "## Your story");
      L.push("", `**Through-line:** ${k.throughLine}`);
      L.push("", "### Tell me about yourself", k.tellMe);
      L.push("", `### ${UI.whyRoleHead}`, k.whyRole);
      L.push("", `### ${S.target ? "Why this role" : "Why this kind of role"}`, k.whyThis);
      if (k.beats.length) { L.push("", "### Beats"); k.beats.forEach((b) => L.push(`1. ${b}`)); }
      if (k.tips.length) { L.push("", "### Delivery"); k.tips.forEach((tp) => L.push(`- ${tp}`)); }
      k.flags.forEach((f) => L.push(`- ⚠ ${f}`));
    }
    if (L.length <= 2) { msg("exportMsg", "nothing to export yet", true); return; }
    const blob = new Blob([L.join("\n") + "\n"], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `prep-sheet-${TRACK}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
    msg("exportMsg", "downloaded");
    x.track("prep_export", { review: !!S.review, story: !!S.kit });
  };
})();
