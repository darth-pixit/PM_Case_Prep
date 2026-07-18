// Prep Engine (/prep): CV + JD -> achievement units + target profile ->
// coverage heatmap -> STAR stories -> exportable prep pack.
//
// v0 is deliberately stateless server-side: this file holds the session's whole
// state (units, target, cells, stories) and sends what each endpoint needs.
// Refresh = clean slate, by design. Persistence is the v1 "story bank".

(() => {
  const x = PMCP.experiment("prep");
  const $ = (id) => document.getElementById(id);
  const esc = PMCP.esc;

  const S = { units: [], target: null, cells: [], stories: {} }; // stories by competency

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
  const label = (c) => LABELS[c] || c;

  async function api(path, body) {
    const r = await fetch("/api/prep/" + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!d.ok) throw new Error(d.error || "request failed (" + r.status + ")");
    return d;
  }

  // --- Auth gate -------------------------------------------------------------
  PMCP.mountAuth($("authMount"), {
    reason: "Sign in to run the engine — each step is a real model call.",
    onLogin: (email) => {
      $("whoami").textContent = email;
      $("builder").hidden = false;
    },
  });

  // --- The build loop --------------------------------------------------------
  $("buildBtn").onclick = async () => {
    const cv = $("cvText").value.trim();
    const jd = $("jdText").value.trim();
    if (!cv || !jd) { msg("buildMsg", "Both boxes, then build.", true); return; }
    $("buildBtn").disabled = true;
    x.track("build_started", { cv_chars: cv.length, jd_chars: jd.length });
    try {
      msg("buildMsg", "Extracting your achievement units + decoding the role…");
      const [u, t] = await Promise.all([
        api("extract-units", { text: cv }),
        api("extract-target", { text: jd }),
      ]);
      S.units = u.units; S.target = t.target; S.stories = {};
      renderUnits(); renderTarget();
      if (!$("spine").value.trim() && S.target.unwrittenPain) {
        $("spine").value = "I have repeatedly solved this exact pain: " + S.target.unwrittenPain;
      }
      msg("buildMsg", "Scoring coverage…");
      const h = await api("heatmap", { units: S.units, target: S.target });
      S.cells = h.cells;
      renderHeatmap();
      msg("buildMsg", "");
      x.track("heatmap_built", {
        units: S.units.length,
        green: S.cells.filter((c) => c.strength === "green").length,
        amber: S.cells.filter((c) => c.strength === "amber").length,
        red: S.cells.filter((c) => c.strength === "red").length,
      });
      $("heatmapCard").scrollIntoView({ behavior: "smooth" });
    } catch (e) {
      msg("buildMsg", e.message, true);
      x.track("build_failed", { error: e.message });
    }
    $("buildBtn").disabled = false;
  };

  function msg(id, text, bad) {
    const el = $(id);
    el.textContent = text;
    el.style.color = bad ? "var(--bad)" : "";
  }

  // --- Renderers -------------------------------------------------------------
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
    $("unitsHead").textContent = `Your achievement units (${S.units.length})`;
    $("unitsOut").innerHTML = S.units.map((u) => `
      <div class="unit ${u.isFailure ? "fail" : ""}">
        <b>${esc(u.title)}</b> ${u.isFailure ? '<span class="pill hot">failure story — gold</span>' : ""}
        <small>${esc(u.context)}</small>
        <p>${esc(u.action)} → ${esc(u.result)}</p>
        <p class="metric">${u.metric ? "📈 " + esc(u.metric) : '<span class="nometric">no metric in source — none invented</span>'}</p>
        <div class="chips">${u.competencies.map((c) => `<span class="pill">${esc(label(c))}</span>`).join("")}</div>
        <details><summary>provenance</summary><blockquote>${esc(u.rawEvidence)}</blockquote></details>
      </div>`).join("");
  }

  function renderHeatmap() {
    $("heatmapCard").hidden = false;
    const weight = Object.fromEntries(
      S.target.requiredCompetencies.map((rc) => [rc.competency, rc.weight]));
    const evidence = Object.fromEntries(
      S.target.requiredCompetencies.map((rc) => [rc.competency, rc.evidence]));
    const unitById = Object.fromEntries(S.units.map((u) => [u.id, u]));
    const cells = [...S.cells].sort((a, b) => (weight[b.competency] || 0) - (weight[a.competency] || 0));
    $("heatmapOut").innerHTML = `<table class="hm">
      <tr><th>competency</th><th>weight</th><th>coverage</th><th>your move</th></tr>
      ${cells.map((c) => {
        const u = c.bestUnitId ? unitById[c.bestUnitId] : null;
        const move = c.strength === "red"
          ? `<span class="gap">${esc(c.gapAction || "")}</span>`
          : `<button class="btn small" data-comp="${esc(c.competency)}">${S.stories[c.competency] ? "View story" : "Draft story"}</button>
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
  }

  async function story(comp, btn) {
    if (S.stories[comp]) { renderStory(comp); return; }
    btn.disabled = true; btn.textContent = "Drafting…";
    x.track("story_requested", { competency: comp });
    try {
      const cell = S.cells.find((c) => c.competency === comp);
      const tagged = S.units.filter((u) => u.competencies.includes(comp)).map((u) => u.id);
      const unitIds = tagged.length ? tagged : (cell && cell.bestUnitId ? [cell.bestUnitId] : []);
      const d = await api("story", {
        competency: comp,
        spine: $("spine").value.trim(),
        units: S.units,
        unitIds,
      });
      S.stories[comp] = d.story;
      renderStory(comp);
      btn.textContent = "View story";
      x.track("story_built", { competency: comp, flags: d.story.unverifiedClaims.length });
    } catch (e) {
      btn.textContent = "Draft story";
      msg("exportMsg", e.message, true);
    }
    btn.disabled = false;
  }

  function renderStory(comp) {
    const st = S.stories[comp];
    $("storyCard").hidden = false;
    $("storyHead").textContent = "Story — " + label(comp);
    const tabs = [["thirtySec", "30 seconds"], ["twoMin", "2 minutes"], ["deepDive", "Deep dive"]];
    $("storyOut").innerHTML = `
      <p class="hint">Spine: ${esc(st.spineTag)}</p>
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
    $("storyCard").scrollIntoView({ behavior: "smooth" });
  }

  // --- Export: one markdown prep pack the user keeps -------------------------
  $("exportBtn").onclick = () => {
    if (!S.target) { msg("exportMsg", "Build the heatmap first.", true); return; }
    const t = S.target;
    const unitById = Object.fromEntries(S.units.map((u) => [u.id, u]));
    const weight = Object.fromEntries(
      t.requiredCompetencies.map((rc) => [rc.competency, rc.weight]));
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
      told.forEach(([comp, st]) => {
        L.push(`### ${label(comp)}`);
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
    L.push("\n## Appendix — achievement units (with provenance)\n");
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
