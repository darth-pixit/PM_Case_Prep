// Referral Paths — everything runs IN the browser. The LinkedIn export is
// parsed locally, grouped by honest heuristics, and never sent anywhere.
// The only thing that leaves the page is anonymous analytics (counts, clicks),
// never names, companies, or emails.

const { track } = PMCP.experiment("referrals");
const $ = (id) => document.getElementById(id);
const esc = PMCP.esc;

// --- CSV parsing ------------------------------------------------------------
// LinkedIn's Connections.csv starts with a "Notes:" preamble before the real
// header row, and fields can be quoted with embedded commas/newlines. This is
// a small full CSV parser, then we scan for the header row.

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQ = false;
      } else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.some((f) => f.trim() !== "")) rows.push(row);
      row = [];
    } else field += c;
  }
  row.push(field);
  if (row.some((f) => f.trim() !== "")) rows.push(row);
  return rows;
}

function toPeople(rows) {
  // Find the header row ("First Name", ...) — everything above is preamble.
  const hi = rows.findIndex((r) => r[0] && r[0].trim().toLowerCase() === "first name");
  if (hi === -1) return null;
  const head = rows[hi].map((h) => h.trim().toLowerCase());
  const col = (name) => head.indexOf(name);
  const [cFirst, cLast, cUrl, cEmail, cCompany, cPos, cOn] = [
    col("first name"), col("last name"), col("url"), col("email address"),
    col("company"), col("position"), col("connected on"),
  ];
  return rows.slice(hi + 1).map((r) => ({
    first: (r[cFirst] || "").trim(),
    last: (r[cLast] || "").trim(),
    url: (r[cUrl] || "").trim(),
    email: cEmail >= 0 ? (r[cEmail] || "").trim() : "",
    company: (r[cCompany] || "").trim(),
    position: (r[cPos] || "").trim(),
    on: cOn >= 0 ? new Date((r[cOn] || "").trim()) : null,
  })).filter((p) => p.first || p.last);
}

// --- Import ------------------------------------------------------------------

let people = [];

function handleFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    const rows = parseCsv(String(reader.result));
    const parsed = rows && toPeople(rows);
    if (!parsed || !parsed.length) {
      $("drop").innerHTML = "<b>That didn't look like a LinkedIn Connections.csv.</b> " +
        "Make sure you unzipped the archive and dropped <i>Connections.csv</i> itself.";
      track("csv_failed", {});
      return;
    }
    people = parsed;
    track("csv_imported", { connections: people.length }); // count only — no content
    $("drop").innerHTML = `<b>✓ ${people.length.toLocaleString()} connections loaded</b> — nothing left your browser.`;
    $("aboutYou").hidden = false;
    $("myCompanies").focus();
  };
  reader.readAsText(file);
}

$("drop").onclick = () => $("file").click();
$("file").onchange = () => $("file").files[0] && handleFile($("file").files[0]);
["dragover", "dragleave", "drop"].forEach((ev) =>
  $("drop").addEventListener(ev, (e) => {
    e.preventDefault();
    $("drop").classList.toggle("over", ev === "dragover");
    if (ev === "drop" && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  }));

// --- Grouping ------------------------------------------------------------------
// Honest heuristics only, each explained in its group header:
//  * company match  -> teammates / past colleagues (the export has Company)
//  * Connected On inside your college years -> likely campus-era people
//  * shared email + old connection -> people who let you see their email (a
//    LinkedIn setting most people only allow for people they actually know)

const YEAR_RE = /(\d{4})\s*[-–to ]+\s*(\d{4})/;

function buildGroups() {
  const target = $("targetCompany").value.trim().toLowerCase();
  const myCos = $("myCompanies").value.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  const ym = $("collegeYears").value.match(YEAR_RE);
  const [y0, y1] = ym ? [+ym[1], +ym[2]] : [0, 0];

  const matchCo = (p) => myCos.find((c) => p.company.toLowerCase().includes(c));
  // Alumni email domains (.edu, .ac.in, alumni.*) are a strong college signal
  // even when the connection date is ambiguous.
  const eduMail = (p) => /\.edu(\.[a-z]{2})?$|\.ac\.[a-z]{2}$|@alumni\./i.test(p.email);
  const inCollege = (p) => (y1 && p.on && !isNaN(p.on) &&
    p.on.getFullYear() >= y0 && p.on.getFullYear() <= y1 + 1) || eduMail(p);
  const oldTie = (p) => p.on && !isNaN(p.on) &&
    (Date.now() - p.on.getTime()) > 3 * 365 * 24 * 3600 * 1000;

  const used = new Set();
  const take = (pred) => {
    const out = people.filter((p, i) => !used.has(i) && pred(p, i));
    people.forEach((p, i) => { if (out.includes(p)) used.add(i); });
    return out;
  };

  const groups = [];
  // The bucket that gets people hired: 1st-degree connections at the company
  // you're applying to. Always first, never swallowed by other groups.
  if (target) {
    groups.push({
      title: `At ${cap(target)} — your way in`, icon: "🎯",
      people: take((p) => p.company.toLowerCase().includes(target)),
      why: "They work at your target company right now. One warm message beats a hundred cold applications — most companies even pay them a bonus for referring you.",
    });
  }
  if (myCos.length) {
    const current = take((p) => p.company && p.company.toLowerCase().includes(myCos[0]));
    groups.push({
      title: `Your team & company (${cap(myCos[0])})`, icon: "🏢", people: current,
      why: "They work where you work — the warmest possible referral, often with a bonus for them.",
    });
    if (myCos.length > 1) {
      groups.push({
        title: "Past colleagues", icon: "🕰️", people: take((p) => !!matchCo(p)),
        why: "You shipped things together once — a two-line “remember me?” reopens the door.",
      });
    }
  }
  if (y1) {
    groups.push({
      title: "College-era connections", icon: "🎓", people: take(inCollege),
      why: `You connected with them between ${y0} and ${y1 + 1} — most people from that window are batchmates and department friends. (LinkedIn's export doesn't include education, so this is inferred from the connection date.)`,
    });
  }
  groups.push({
    title: "Likely close ties", icon: "⭐",
    people: take((p) => p.email && oldTie(p)),
    why: "They've known you 3+ years AND let you see their email address — a LinkedIn setting most people reserve for people they actually know.",
  });
  groups.push({
    title: "Everyone else", icon: "🌐",
    people: people.filter((_, i) => !used.has(i)),
    why: "Search by company or role — the person one search away is often the one who refers you.",
    searchable: true,
  });
  return groups;
}

function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

function askTemplate(p) {
  const where = p.company ? ` at ${p.company}` : "";
  return `Hi ${p.first}! Hope you've been well 😊 I'm exploring PM roles${where ? ` and saw you're ${p.position || "working"}${where}` : ""} — if there's an opening that fits, would you be open to referring me? I'll send a short blurb + resume so it's zero work for you. Totally fine if it's not a good time!`;
}

function personRow(p, gi) {
  const name = `${p.first} ${p.last}`.trim();
  const link = p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(name)}</a>` : esc(name);
  const sub = [p.position, p.company].filter(Boolean).join(" · ");
  const when = p.on && !isNaN(p.on) ? `connected ${p.on.getFullYear()}` : "";
  return `<div class="person">
    <span><b>${link}</b><br><small>${esc(sub || "—")}${when ? ` · ${when}` : ""}</small></span>
    <span class="act">
      ${p.email ? `<a class="btn small ghost" href="mailto:${esc(p.email)}?subject=${encodeURIComponent("Quick favor — referral?")}&body=${encodeURIComponent(askTemplate(p))}">Email</a> ` : ""}
      <button class="btn small ghost copy-ask" data-g="${gi}" data-ask="${esc(askTemplate(p))}">Copy ask</button>
    </span>
  </div>`;
}

function renderGroups() {
  const groups = buildGroups();
  track("groups_built", {
    groups: groups.map((g) => ({ title: g.title, count: g.people.length })),
  });
  $("groups").hidden = false;
  $("groups").innerHTML = `<div class="card"><h2>3 · Your referral paths</h2>` +
    groups.map((g, gi) => `
      <details class="fold" ${g.people.length && gi === 0 ? "open" : ""}>
        <summary>${g.icon} ${esc(g.title)} <span class="count">${g.people.length}</span></summary>
        <div class="fold-body">
          <p class="hint">${esc(g.why)}</p>
          ${g.searchable ? `<input type="text" class="grp-search" data-g="${gi}" placeholder="Filter by name, company, or role…" style="margin:0.4rem 0" />` : ""}
          <div class="grp-list" data-g="${gi}">
            ${g.people.slice(0, g.searchable ? 25 : 200).map((p) => personRow(p, gi)).join("") || "<p class='hint'>Nobody matched this bucket.</p>"}
          </div>
        </div>
      </details>`).join("") +
    `</div>`;

  $("groups").querySelectorAll(".copy-ask").forEach((b) => {
    b.onclick = async () => {
      try { await navigator.clipboard.writeText(b.dataset.ask); b.textContent = "✓ Copied"; }
      catch { b.textContent = "Copy failed"; }
      track("ask_copied", { group: +b.dataset.g }); // group index only — no content
      setTimeout(() => { b.textContent = "Copy ask"; }, 1600);
    };
  });
  $("groups").querySelectorAll(".grp-search").forEach((inp) => {
    inp.oninput = () => {
      const q = inp.value.toLowerCase();
      const g = groups[+inp.dataset.g]; // same array the fold was rendered from
      const hits = g.people.filter((p) =>
        `${p.first} ${p.last} ${p.company} ${p.position}`.toLowerCase().includes(q)).slice(0, 50);
      inp.closest(".fold-body").querySelector(".grp-list").innerHTML =
        hits.map((p) => personRow(p, +inp.dataset.g)).join("") || "<p class='hint'>No matches.</p>";
    };
  });
}

$("groupBtn").onclick = renderGroups;

// --- Future connectors (demand test) ------------------------------------------
// Each card is honest about what's technically possible. The "I'd use this"
// click is the experiment: it tells us which connector to actually build.

const CONNECTORS = [
  {
    name: "Google Contacts", icon: "📇", status: "buildable now",
    what: "One Google popup (you're already signing in with Google here) reads your saved contacts — names, emails, companies. Great for the 'close friends' bucket LinkedIn misses.",
  },
  {
    name: "Gmail frequency signals", icon: "✉️", status: "possible, but heavy",
    what: "Who you actually email is the best closeness signal there is. But Gmail metadata is a Google 'restricted' scope — apps need an annual paid security audit to use it — so this only makes sense once enough people want it.",
  },
  {
    name: "Phone contacts upload", icon: "📱", status: "buildable now",
    what: "Export contacts from your phone (one tap on iOS/Android) and drop the file here, same as the LinkedIn CSV — parsed locally, never uploaded.",
  },
  {
    name: "College alumni directory", icon: "🎓", status: "manual for now",
    what: "University portals block automated access, but LinkedIn's own alumni tool (linkedin.com/school/your-school/people) filters your school's alumni by company and field — find them there, then match the names in your export here. Alumni email domains (.edu, .ac.in) already boost the college bucket above.",
  },
  {
    name: "Slack workspace directory", icon: "💬", status: "buildable, per-workspace",
    what: "Your workplace Slack knows your real team. A user-level connection can read the member roster (name, title) — though some company admins restrict app installs.",
  },
  {
    name: "Facebook friends", icon: "👥", status: "not possible",
    what: "Facebook removed the friends-list API for third-party apps back in 2014-15 (only friends who also installed the same app are visible). No honest app can read your friends list.",
  },
];

$("connectors").innerHTML = CONNECTORS.map((c, i) => `
  <details class="fold">
    <summary>${c.icon} ${esc(c.name)} <span class="count">${esc(c.status)}</span></summary>
    <div class="fold-body">
      <p>${esc(c.what)}</p>
      <button class="btn small ghost want" data-c="${esc(c.name)}">I'd use this →</button>
    </div>
  </details>`).join("");

$("connectors").querySelectorAll(".want").forEach((b) => {
  b.onclick = () => {
    track("connector_interest", { connector: b.dataset.c });
    b.textContent = "✓ Noted — thanks!";
    b.disabled = true;
  };
});

track("viewed", {});
