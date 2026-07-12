// Case Arena — category picker for the multi-case experiment.
// Flow: sign in (Google or email code) -> pick a track -> pick a case ->
// /arena/room?case=<id> runs the same interview room as the tutor, but tagged
// with the arena experiment so analytics stay separate.

const { track } = PMCP.experiment("arena");
const $ = (id) => document.getElementById(id);
const esc = PMCP.esc;

let catalog = null;
let completed = new Set();

async function loadCatalog() {
  const r = await fetch("/api/arena/catalog");
  const d = await r.json();
  catalog = d.categories || [];
  completed = new Set(d.completed || []);
}

function renderCats() {
  $("cats").hidden = false;
  $("caseList").hidden = true;
  $("catGrid").innerHTML = catalog.map((c, i) => {
    const done = c.cases.filter((k) => completed.has(k.id)).length;
    return `<button class="cat-card" data-i="${i}">
      <span class="ico">${esc(c.icon || "📦")}</span>
      <h3>${esc(c.name)}</h3>
      <p>${esc(c.blurb || "")}</p>
      <div class="prog">${done ? `<span class="done">${done} done</span> · ` : ""}${c.cases.length} cases</div>
    </button>`;
  }).join("");
  $("catGrid").querySelectorAll(".cat-card").forEach((b) => {
    b.onclick = () => {
      const cat = catalog[+b.dataset.i];
      track("category_opened", { category: cat.key });
      renderCases(cat);
    };
  });
}

function renderCases(cat) {
  $("cats").hidden = true;
  $("caseList").hidden = false;
  $("clTitle").textContent = `${cat.icon || ""} ${cat.name}`.trim();
  $("clBlurb").textContent = cat.blurb || "";
  $("clRows").innerHTML = cat.cases.map((k) => `
    <div class="case-row">
      <span class="tick">${completed.has(k.id) ? "✓" : ""}</span>
      <span class="body"><b>${esc(k.title)}</b><small>${esc(k.teaser || "")}</small></span>
      <span class="meta">${esc(k.type)} · ~${k.minutes} min</span>
      <button class="btn small" data-case="${esc(k.id)}">${completed.has(k.id) ? "Redo" : "Start"}</button>
    </div>`).join("");
  $("clRows").querySelectorAll("button[data-case]").forEach((b) => {
    b.onclick = () => {
      track("case_opened", { case_id: b.dataset.case, category: cat.key });
      location.href = "/arena/room?case=" + encodeURIComponent(b.dataset.case);
    };
  });
  $("backToCats").onclick = () => renderCats();
}

async function enter(email) {
  $("whoami").textContent = email;
  $("gateCard").hidden = true;
  await loadCatalog();
  if (!catalog.length) {
    $("cats").hidden = false;
    $("catGrid").innerHTML = `<div class="card">The case bank is being stocked — check back shortly.</div>`;
    return;
  }
  renderCats();
}

track("viewed", { login_hint: location.search.includes("login=1") });
PMCP.mountAuth($("authMount"), {
  reason: "One account, three reasons: your scores and skill graph follow you " +
          "across devices, finished cases stay yours, and new cases unlock as they drop.",
  onLogin: (email, d) => {
    if (!d || !d.already) track("signed_in", { restored: !!(d && d.restored) });
    enter(email);
  },
});
