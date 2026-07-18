// Referral Paths v2 — the closeness engine. Everything in SOLO mode runs IN
// the browser: LinkedIn's full archive ZIP, phone-contact vCards, Google
// Contacts CSVs, and Instagram/Facebook export ZIPs are all parsed locally and
// cross-referenced into one relationship-strength model. Nothing is uploaded.
//
// PODS are the one explicit exception, and the only server touch: a member
// opts in to share (1) their own work-history companies and (2) one row per
// connection — SHA-256(profile URL) + that connection's company. Names never
// leave the browser; the server rejects anything that isn't hash-shaped.
//
// Analytics stay anonymous throughout: counts and clicks, never names,
// companies, or emails.

const { track } = PMCP.experiment("referrals");
const $ = (id) => document.getElementById(id);
const esc = PMCP.esc;

// --- tiny utils ---------------------------------------------------------------

function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

// Letters-only lowercase key: "Párth  Dixit-2" -> "parthdixit". The join key
// for cross-source name matching (phone/FB names vs LinkedIn names).
function normName(s) {
  return String(s || "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[^a-z]/g, "");
}

// Both name orders — exports disagree on "First Last" vs "Last First".
function nameKeys(name) {
  const parts = String(name || "").trim().split(/\s+/);
  const a = normName(parts.join(""));
  const b = parts.length > 1 ? normName(parts.slice(1).join("") + parts[0]) : "";
  return b && b !== a ? [a, b] : [a];
}

// Canonical profile-URL key: identical across every member's export for the
// same person — which is exactly what makes it the pods join key.
function normUrl(u) {
  return String(u || "").trim().toLowerCase()
    .replace(/^https?:\/\/(www\.)?/, "").split("?")[0].replace(/\/+$/, "");
}

function normCo(s) { return String(s || "").trim().toLowerCase().replace(/\s+/g, " ").slice(0, 80); }

function yearOf(s) { const m = String(s || "").match(/\d{4}/); return m ? +m[0] : 0; }

function parseWhen(s) {
  // "2024-01-15 10:23:45 UTC" (messages) or "18 Jul 2020" (connections)
  const raw = String(s || "").trim();
  if (!raw) return null;
  const m = raw.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) UTC$/);
  const d = m ? new Date(`${m[1]}T${m[2]}Z`) : new Date(raw);
  return isNaN(d) ? null : d;
}

// Meta exports escape UTF-8 bytes as if they were latin-1 ("Ã©" soup) — undo it.
function fixMoji(s) {
  if (!s || !/[\xc2-\xf4]/.test(s)) return s;
  try { return decodeURIComponent(escape(s)); } catch { return s; }
}

async function sha256hex(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

// --- CSV parsing ----------------------------------------------------------------
// LinkedIn CSVs can carry a "Notes:" preamble, quoted fields with embedded
// commas/newlines, and (messages.csv) tens of MB of content. Full parser.

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

// Find the header row (preambles above it are skipped) and return objects
// keyed by lowercase header. `required` = cells that identify this table.
function findTable(rows, required) {
  const hi = rows.findIndex((r) => {
    const cells = r.map((c) => c.trim().toLowerCase());
    return required.every((n) => cells.includes(n));
  });
  if (hi === -1) return null;
  const head = rows[hi].map((h) => h.trim().toLowerCase());
  return rows.slice(hi + 1).map((r) => {
    const o = {};
    head.forEach((h, i) => { if (h) o[h] = (r[i] || "").trim(); });
    return o;
  });
}

// --- ZIP reading (no libraries) ---------------------------------------------------
// LinkedIn / Instagram / Facebook archives are plain ZIPs; entries are either
// stored or DEFLATEd, and DecompressionStream("deflate-raw") inflates the
// latter natively. ~60 lines beats shipping a dependency.

async function readZip(file) {
  const buf = new Uint8Array(await file.arrayBuffer());
  const dv = new DataView(buf.buffer);
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65558); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("not a ZIP file");
  const count = dv.getUint16(eocd + 10, true);
  let off = dv.getUint32(eocd + 16, true);
  const td = new TextDecoder();
  const entries = [];
  for (let i = 0; i < count; i++) {
    if (off + 46 > buf.length || dv.getUint32(off, true) !== 0x02014b50) break;
    const method = dv.getUint16(off + 10, true);
    const csize = dv.getUint32(off + 20, true);
    const usize = dv.getUint32(off + 24, true);
    const nlen = dv.getUint16(off + 28, true);
    const xlen = dv.getUint16(off + 30, true);
    const clen = dv.getUint16(off + 32, true);
    const lho = dv.getUint32(off + 42, true);
    entries.push({ name: td.decode(buf.subarray(off + 46, off + 46 + nlen)), method, csize, usize, lho });
    off += 46 + nlen + xlen + clen;
  }
  async function text(ent) {
    if (ent.usize === 0xffffffff) throw new Error("ZIP64 entry — unzip manually and drop the files");
    const lh = ent.lho;
    if (dv.getUint32(lh, true) !== 0x04034b50) throw new Error("corrupt ZIP entry");
    const nlen = dv.getUint16(lh + 26, true);
    const xlen = dv.getUint16(lh + 28, true);
    const start = lh + 30 + nlen + xlen;
    const data = buf.subarray(start, start + ent.csize);
    let bytes;
    if (ent.method === 0) bytes = data;
    else if (ent.method === 8) {
      const ds = new DecompressionStream("deflate-raw");
      bytes = new Uint8Array(await new Response(new Blob([data]).stream().pipeThrough(ds)).arrayBuffer());
    } else throw new Error("unsupported compression");
    return new TextDecoder("utf-8").decode(bytes);
  }
  return { entries, text };
}

// --- State -----------------------------------------------------------------------

const S = {
  people: [],            // unified person records (LinkedIn connections as spine)
  byUrl: new Map(),      // urlKey  -> person
  byName: new Map(),     // nameKey -> person (both name orders registered)
  byEmail: new Map(),    // email   -> person
  external: [],          // close contacts with NO LinkedIn match (phone/IG/FB)
  extByKey: new Map(),
  me: { name: "", urls: new Set() },
  edu: [],               // {school, y0, y1}
  positions: [],         // {company, co, title, y0, y1, current}
  sources: new Map(),    // sourceKey -> {label, detail}
};

const SRC_BADGE = { phone: "📱", ig: "📸", fb: "👥" };

function addSource(key, label, detail) {
  S.sources.set(key, { label, detail: detail || "" });
  renderSources();
}

function newPerson(fields) {
  return Object.assign({
    first: "", last: "", url: "", urlKey: "", email: "", company: "",
    position: "", on: null, srcs: new Set(), igClose: false,
    msgs: null,            // {n, sent, recv, last, theyInitiated, referral}
    recReceived: false, recGiven: false, invitedMe: false, inviteNote: false,
    endorsed: 0, score: 0, chips: [],
  }, fields);
}

function registerPerson(p) {
  p.name = `${p.first} ${p.last}`.trim();
  p.urlKey = normUrl(p.url);
  if (p.urlKey && S.byUrl.has(p.urlKey)) return S.byUrl.get(p.urlKey); // re-drop dedupe
  const keys = nameKeys(p.name);
  if (!p.urlKey && keys[0] && S.byName.has(keys[0])) {
    const prev = S.byName.get(keys[0]);
    if (normCo(prev.company) === normCo(p.company)) return prev;
  }
  S.people.push(p);
  if (p.urlKey) S.byUrl.set(p.urlKey, p);
  for (const k of keys) if (k && !S.byName.has(k)) S.byName.set(k, p);
  if (p.email) S.byEmail.set(p.email.toLowerCase(), p);
  return p;
}

function findByNameish(name) {
  for (const k of nameKeys(name)) {
    if (k && k.length >= 5 && S.byName.has(k)) return S.byName.get(k);
  }
  return null;
}

// --- LinkedIn archive ingestion -----------------------------------------------------

function ingestConnections(objs) {
  let n = 0;
  for (const r of objs) {
    const first = r["first name"] || "", last = r["last name"] || "";
    if (!first && !last) continue;
    registerPerson(newPerson({
      first, last,
      url: r["url"] || "",
      email: (r["email address"] || "").toLowerCase(),
      company: r["company"] || "",
      position: r["position"] || "",
      on: parseWhen(r["connected on"]),
    })).srcs.add("li");
    n++;
  }
  addSource("li", `LinkedIn connections`, `${S.people.filter((p) => p.srcs.has("li")).length.toLocaleString()} people`);
  track("csv_imported", { connections: n }); // count only — no content
}

function ingestProfile(objs) {
  const r = objs[0];
  if (r) S.me.name = `${r["first name"] || ""} ${r["last name"] || ""}`.trim();
}

function ingestEducation(objs) {
  for (const r of objs) {
    const school = r["school name"] || "";
    if (!school) continue;
    S.edu.push({ school, y0: yearOf(r["start date"]), y1: yearOf(r["end date"]) });
  }
  if (S.edu.length) {
    const y0 = Math.min(...S.edu.map((e) => e.y0).filter(Boolean));
    const y1 = Math.max(...S.edu.map((e) => e.y1).filter(Boolean));
    addSource("edu", "Education", S.edu.map((e) => e.school).join(", ") + (y0 && y1 !== -Infinity ? ` (${y0}–${y1})` : ""));
  }
}

function ingestPositions(objs) {
  for (const r of objs) {
    const company = r["company name"] || "";
    if (!company) continue;
    S.positions.push({
      company, co: normCo(company), title: r["title"] || "",
      y0: yearOf(r["started on"]), y1: yearOf(r["finished on"]),
      current: !(r["finished on"] || "").trim(),
    });
  }
  S.positions.sort((a, b) => b.y0 - a.y0);
  if (S.positions.length) {
    addSource("pos", "Work history", S.positions.map((p) => p.company).join(", "));
  }
}

const REF_RE = /\b(refer\w*|opening|opportunit\w*|resume|résumé|cv|jd|job|jobs|hiring|recruit\w*|vacanc\w*|interview\w*)\b/i;

function ingestMessages(objs) {
  // Group into conversations; keep only real folders.
  const convos = new Map();
  for (const m of objs) {
    const id = m["conversation id"];
    if (!id || !(m["content"] || "").trim()) continue;
    const folder = (m["folder"] || "INBOX").toUpperCase();
    if (folder !== "INBOX" && folder !== "ARCHIVE") continue;
    (convos.get(id) || convos.set(id, []).get(id)).push(m);
  }
  // Who am I? The sender URL that appears in the most conversations is me.
  const seenIn = new Map();
  for (const msgs of convos.values()) {
    for (const u of new Set(msgs.map((m) => normUrl(m["sender profile url"])).filter(Boolean))) {
      seenIn.set(u, (seenIn.get(u) || 0) + 1);
    }
  }
  let meUrl = "", best = 0;
  for (const [u, n] of seenIn) if (n > best) { best = n; meUrl = u; }
  if (meUrl) S.me.urls.add(meUrl);
  const meNameKey = normName(S.me.name);
  const isMine = (m) => {
    const u = normUrl(m["sender profile url"]);
    if (u) return S.me.urls.has(u);
    return !!meNameKey && normName(m["from"]) === meNameKey;
  };

  let threads = 0, matched = 0;
  for (const msgs of convos.values()) {
    // 1:1 threads only — group chats aren't a closeness signal per person.
    const partners = new Map(); // urlKey -> display name
    for (const m of msgs) {
      const su = normUrl(m["sender profile url"]);
      if (su && !S.me.urls.has(su)) partners.set(su, m["from"] || partners.get(su) || "");
      for (const ru of String(m["recipient profile urls"] || "").split(/[;,]/)) {
        const rk = normUrl(ru);
        if (rk && !S.me.urls.has(rk) && !partners.has(rk)) partners.set(rk, "");
      }
    }
    if (partners.size !== 1) continue;
    threads++;
    const [purl, pname] = partners.entries().next().value;
    msgs.sort((a, b) => (parseWhen(a["date"]) || 0) - (parseWhen(b["date"]) || 0));
    let sent = 0, recv = 0, referral = false, last = null;
    for (const m of msgs) {
      if (isMine(m)) sent++; else recv++;
      if (!referral && REF_RE.test(m["content"] || "")) referral = true;
      const d = parseWhen(m["date"]);
      if (d && (!last || d > last)) last = d;
    }
    const p = S.byUrl.get(purl) || (pname ? findByNameish(pname) : null);
    if (!p) continue; // messaged non-connections are out of scope (for now)
    matched++;
    const prev = p.msgs || { n: 0, sent: 0, recv: 0, last: null, theyInitiated: false, referral: false };
    p.msgs = {
      n: prev.n + sent + recv,
      sent: prev.sent + sent,
      recv: prev.recv + recv,
      last: prev.last && prev.last > last ? prev.last : last,
      theyInitiated: prev.theyInitiated || (msgs.length > 0 && !isMine(msgs[0])),
      referral: prev.referral || referral,
    };
  }
  addSource("msg", "LinkedIn messages", `${threads.toLocaleString()} 1:1 threads · ${matched.toLocaleString()} matched to connections`);
}

function ingestInvitations(objs) {
  let n = 0;
  for (const r of objs) {
    if ((r["direction"] || "").toUpperCase() !== "INCOMING") continue;
    const p = S.byUrl.get(normUrl(r["inviterprofileurl"] || r["inviter profile url"] || ""))
      || findByNameish(r["from"] || "");
    if (!p) continue;
    p.invitedMe = true;
    if ((r["message"] || "").trim()) p.inviteNote = true;
    n++;
  }
  if (n) addSource("inv", "Invitations", `${n.toLocaleString()} people invited YOU`);
}

function ingestRecommendations(objs, given) {
  let n = 0;
  for (const r of objs) {
    if ((r["status"] || "").toLowerCase() === "rejected") continue;
    const p = findByNameish(`${r["first name"] || ""} ${r["last name"] || ""}`);
    if (!p) continue;
    if (given) p.recGiven = true; else p.recReceived = true;
    n++;
  }
  if (n) addSource(given ? "recg" : "recr",
    given ? "Recommendations you wrote" : "Recommendations you received",
    `${n} matched`);
}

function ingestEndorsements(objs) {
  const counts = new Map();
  for (const r of objs) {
    const key = normUrl(r["endorser public url"] || "")
      || nameKeys(`${r["endorser first name"] || ""} ${r["endorser last name"] || ""}`)[0];
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
  }
  let n = 0;
  for (const [key, c] of counts) {
    const p = S.byUrl.get(key) || S.byName.get(key);
    if (p) { p.endorsed = Math.max(p.endorsed, c); n++; }
  }
  if (n) addSource("end", "Endorsements", `${n} endorsers matched`);
}

// --- External sources (phone / Google / Instagram / Facebook) ------------------------

function matchExternal(entry, src, externOk) {
  // entry: {name, emails?, org?, close?}
  let p = null;
  for (const em of entry.emails || []) p = p || S.byEmail.get(String(em).toLowerCase());
  if (!p) p = findByNameish(entry.name);
  if (p) {
    p.srcs.add(src);
    if (entry.close) p.igClose = true;
    return true;
  }
  if (!externOk || S.external.length >= 5000) return false;
  const k = nameKeys(entry.name)[0];
  if (!k || k.length < 3) return false;
  const meKey = normName(S.me.name);
  if (meKey && k === meKey) return false; // don't list yourself
  let e = S.extByKey.get(k);
  if (!e) {
    e = { name: entry.name, org: entry.org || "", emails: entry.emails || [], srcs: new Set(), close: false };
    S.extByKey.set(k, e);
    S.external.push(e);
  }
  e.srcs.add(src);
  if (entry.close) e.close = true;
  if (!e.org && entry.org) e.org = entry.org;
  return false;
}

function ingestVcf(text) {
  const cards = text.split(/BEGIN:VCARD/i).slice(1);
  let n = 0, matched = 0;
  for (const c of cards) {
    const fn = (c.match(/^FN[^:]*:(.+)$/mi) || [])[1];
    const nn = (c.match(/^N[^:]*:(.+)$/mi) || [])[1];
    let name = (fn || "").trim();
    if (!name && nn) {
      const parts = nn.split(";");
      name = `${parts[1] || ""} ${parts[0] || ""}`.trim();
    }
    if (!name) continue;
    const emails = [...c.matchAll(/^EMAIL[^:]*:(.+)$/gmi)].map((m) => m[1].trim());
    const org = ((c.match(/^ORG[^:]*:(.+)$/mi) || [])[1] || "").split(";")[0].trim();
    n++;
    if (matchExternal({ name, emails, org }, "phone", true)) matched++;
  }
  if (!n) throw new Error("no contacts found in that vCard");
  addSource("phone", "Phone contacts", `${n.toLocaleString()} contacts · ${matched.toLocaleString()} matched on LinkedIn`);
  track("source_loaded", { kind: "phone", count: n, matched });
}

function ingestGoogleCsv(objs) {
  let n = 0, matched = 0;
  for (const r of objs) {
    const name = r["name"]
      || `${r["first name"] || r["given name"] || ""} ${r["last name"] || r["family name"] || ""}`.trim();
    if (!name) continue;
    const emails = Object.keys(r).filter((k) => /e-mail.*value/.test(k)).map((k) => r[k]).filter(Boolean);
    const org = r["organization name"] || r["organization 1 - name"] || "";
    n++;
    if (matchExternal({ name, emails, org }, "phone", true)) matched++;
  }
  addSource("gc", "Google Contacts", `${n.toLocaleString()} contacts · ${matched.toLocaleString()} matched on LinkedIn`);
  track("source_loaded", { kind: "google_contacts", count: n, matched });
}

// Meta exports: harvest every {string_list_data:[{value}]} (IG lists) and every
// array of {name} objects (FB friends). Usernames match only when their letters
// equal a connection's name letters; DM display names match like real names.
function collectMeta(obj, out) {
  if (Array.isArray(obj)) { obj.forEach((x) => collectMeta(x, out)); return; }
  if (!obj || typeof obj !== "object") return;
  if (Array.isArray(obj.string_list_data)) {
    for (const s of obj.string_list_data) if (s && s.value) out.usernames.push(fixMoji(String(s.value)));
    return;
  }
  for (const [k, v] of Object.entries(obj)) {
    if (/friend/i.test(k) && Array.isArray(v) && v.every((x) => x && typeof x === "object" && x.name)) {
      for (const f of v) out.names.push(fixMoji(String(f.name)));
    } else collectMeta(v, out);
  }
}

const igDmNames = new Map(); // nameKey -> {name, threads} — resolved in finishMetaDms
const fbDmNames = new Map();

function ingestMetaJson(path, text, hint) {
  let obj;
  try { obj = JSON.parse(text); } catch { return; }
  const p = path.toLowerCase();
  const src = (hint === "ig" || hint === "fb") ? hint
    : (p.includes("instagram") || /follow|close_friends/.test(p)) ? "ig" : "fb";
  if (/message_1\.json$|message_\d+\.json$/.test(p) && obj && Array.isArray(obj.participants)) {
    if (obj.participants.length !== 2) return; // group chats: not a closeness signal
    const bag = src === "ig" ? igDmNames : fbDmNames;
    for (const part of obj.participants) {
      const name = fixMoji(String(part.name || ""));
      const k = nameKeys(name)[0];
      if (!k) continue;
      const e = bag.get(k) || { name, threads: 0 };
      e.threads++;
      bag.set(k, e);
    }
    return;
  }
  const out = { usernames: [], names: [] };
  collectMeta(obj, out);
  const close = /close_friends/.test(p);
  let matched = 0;
  for (const u of out.usernames) {
    // Usernames ("parth.dixit92") match by letters only, and only confidently.
    const k = String(u).toLowerCase().replace(/[^a-z]/g, "");
    if (k.length >= 5 && S.byName.has(k)) {
      const person = S.byName.get(k);
      person.srcs.add(src);
      if (close) person.igClose = true;
      matched++;
    }
  }
  for (const name of out.names) if (matchExternal({ name }, src, true)) matched++;
  if (out.usernames.length || out.names.length) {
    const key = close ? "igclose" : src + ":" + (p.split("/").pop() || "list");
    addSource(key,
      close ? "Instagram close friends" : (src === "ig" ? "Instagram" : "Facebook") + " · " + (p.split("/").pop() || "").replace(".json", ""),
      `${(out.usernames.length + out.names.length).toLocaleString()} entries · ${matched.toLocaleString()} matched`);
  }
}

function finishMetaDms() {
  for (const [bag, src] of [[igDmNames, "ig"], [fbDmNames, "fb"]]) {
    if (!bag.size) continue;
    // IG/FB keep ONE thread per person, so a name showing up in 3+ threads is
    // the account owner echoed into every conversation — drop it.
    let n = 0, matched = 0;
    for (const e of bag.values()) {
      if (bag.size >= 3 && e.threads >= 3) continue;
      n++;
      if (matchExternal({ name: e.name }, src, true)) matched++;
    }
    if (n) addSource(src + "dm", (src === "ig" ? "Instagram" : "Facebook") + " DMs",
      `${n.toLocaleString()} people you message · ${matched.toLocaleString()} matched`);
    bag.clear();
  }
}

// --- File routing ----------------------------------------------------------------

function routeCsvText(fileName, text, fromZip) {
  const rows = parseCsv(text);
  if (!rows.length) return false;
  const t = (req) => findTable(rows, req);
  let objs;
  if ((objs = t(["conversation id", "content"]))) return ingestMessages(objs), true;
  if ((objs = t(["first name", "last name", "connected on"]))) return ingestConnections(objs), true;
  if ((objs = t(["school name"]))) return ingestEducation(objs), true;
  if ((objs = t(["company name", "started on"]))) return ingestPositions(objs), true;
  if ((objs = t(["direction", "sent at"]))) return ingestInvitations(objs), true;
  if ((objs = t(["first name", "job title", "text"])))
    return ingestRecommendations(objs, /given/i.test(fileName)), true;
  if ((objs = t(["endorser first name"]))) return ingestEndorsements(objs), true;
  if ((objs = t(["first name", "last name", "headline"]))) return ingestProfile(objs), true;
  if ((objs = t(["e-mail 1 - value"])) || (objs = t(["given name", "family name"])))
    return ingestGoogleCsv(objs), true;
  if (!fromZip) throw new Error("didn't recognize this CSV — is it from a LinkedIn/Google export?");
  return false; // archives carry many CSVs we don't need — skip quietly
}

async function routeZip(file) {
  if (typeof DecompressionStream === "undefined") {
    throw new Error("this browser can't unzip locally — unzip the archive yourself and drop the CSV/JSON files in");
  }
  const zip = await readZip(file);
  const names = zip.entries.map((e) => e.name.toLowerCase()).join("\n");
  const hint = /connections\.csv|messages\.csv|positions\.csv/.test(names) ? "li"
    : /followers_and_following|your_instagram_activity/.test(names) ? "ig"
    : /your_facebook_activity|your_friends\.json|friends_and_followers/.test(names) ? "fb" : "";
  let used = 0;
  for (const ent of zip.entries) {
    const n = ent.name.toLowerCase();
    if (ent.usize > 250 * 1024 * 1024) continue; // media blobs, not data
    try {
      if (n.endsWith(".csv")) { if (routeCsvText(n, await zip.text(ent), true)) used++; }
      else if (n.endsWith(".json") && hint !== "li"
        && /following|followers|close_friends|friends|message_\d+/.test(n)) {
        ingestMetaJson(ent.name, await zip.text(ent), hint); used++;
      }
    } catch (e) { console.warn("skip", ent.name, e); }
  }
  finishMetaDms();
  if (!used) throw new Error("no recognizable export files inside that ZIP");
  track("archive_loaded", { platform: hint || "unknown", files: used }); // counts only
}

async function routeFile(f) {
  const n = f.name.toLowerCase();
  if (n.endsWith(".zip")) return routeZip(f);
  if (n.endsWith(".vcf") || n.endsWith(".vcard")) return ingestVcf(await f.text());
  if (n.endsWith(".json")) { ingestMetaJson(f.name, await f.text(), ""); finishMetaDms(); return; }
  return routeCsvText(n, await f.text(), false);
}

async function handleFiles(files) {
  $("dropMsg").innerHTML = "<b>Crunching locally…</b> nothing is being uploaded.";
  await new Promise((r) => setTimeout(r, 30)); // let the message paint
  const errs = [];
  for (const f of files) {
    try { await routeFile(f); }
    catch (e) { errs.push(`${f.name}: ${e.message || "couldn't read"}`); track("file_failed", {}); }
  }
  computeScores();
  renderSources();
  const okLine = S.people.length
    ? `<b>✓ ${S.people.length.toLocaleString()} people mapped</b> — nothing left your browser. Drop more files anytime.`
    : "<b>Loaded.</b> Add your LinkedIn export to anchor the map — everything else cross-references against it.";
  $("dropMsg").innerHTML = okLine + (errs.length ? `<br><small>⚠ ${esc(errs.join(" · "))}</small>` : "");
  if (S.people.length) {
    $("aboutYou").hidden = false;
    prefillAboutYou();
  }
  $("file").value = ""; // same file can be re-dropped after a fix
  refreshPodShare();
}

function renderSources() {
  const el = $("srcBoard");
  if (!S.sources.size) { el.innerHTML = ""; return; }
  el.innerHTML = [...S.sources.values()].map((s) =>
    `<span class="pill on" title="${esc(s.detail)}">${esc(s.label)}${s.detail ? ` · ${esc(s.detail)}` : ""}</span>`).join(" ");
}

function prefillAboutYou() {
  if (S.positions.length && !$("myCompanies").value.trim()) {
    $("myCompanies").value = [...new Set(S.positions.map((p) => p.company))].join(", ");
  }
  if (S.edu.length && !$("collegeYears").value.trim()) {
    const y0 = Math.min(...S.edu.map((e) => e.y0).filter(Boolean));
    const y1 = Math.max(...S.edu.map((e) => e.y1).filter(Boolean));
    if (y0 && isFinite(y1)) $("collegeYears").value = `${y0}-${y1}`;
  }
  const auto = [];
  if (S.positions.length) auto.push("work history");
  if (S.edu.length) auto.push(`college (${esc(S.edu[0].school)})`);
  $("autoNote").innerHTML = auto.length
    ? `✓ Auto-filled from your export: ${auto.join(" + ")} — edit anything that's off.` : "";
}

// --- Closeness scoring ---------------------------------------------------------------

const DAY = 24 * 3600 * 1000;
const DOOR_RE = /recruit|talent|sourcing|people ops|human resources|\bhr\b|hiring/i;
const SENIOR_RE = /\bhead\b|director|\bvp\b|vice president|chief|founder|principal/i;

function computeScores() {
  for (const p of S.people) {
    let s = 0;
    const chips = [];
    if (p.msgs) {
      s += 2 + Math.min(3, Math.log2(1 + p.msgs.n));
      if (p.msgs.sent >= 2 && p.msgs.recv >= 2) s += 2;
      const age = p.msgs.last ? (Date.now() - p.msgs.last.getTime()) / DAY : Infinity;
      if (age < 180) s += 2; else if (age < 730) s += 1;
      if (p.msgs.theyInitiated) s += 0.5;
      if (p.msgs.referral) { s += 1; chips.push("💬 talked jobs/referrals before"); }
      chips.push(`✉️ ${p.msgs.n} DMs${p.msgs.last ? " · last " + p.msgs.last.getFullYear() : ""}`);
    }
    if (p.recReceived) { s += 4; chips.push("🤝 recommended you"); }
    if (p.recGiven) { s += 3; chips.push("🎁 you vouched for them"); }
    if (p.invitedMe) { s += p.inviteNote ? 1 : 0.5; chips.push("➕ they invited you"); }
    if (p.endorsed) { s += Math.min(1.5, 0.5 * p.endorsed); chips.push(`👍 endorsed you ×${p.endorsed}`); }
    if (p.srcs.has("phone")) { s += 3; chips.push("📱 in your contacts"); }
    if (p.srcs.has("ig")) { s += p.igClose ? 3 : 2; chips.push(p.igClose ? "📸 IG close friend" : "📸 Instagram"); }
    if (p.srcs.has("fb")) { s += 2; chips.push("👥 Facebook"); }
    if (p.email) s += 1;
    if (p.on && Date.now() - p.on.getTime() > 3 * 365 * DAY) s += 0.5;
    p.score = s;
    p.chips = chips;
    p.door = DOOR_RE.test(p.position) || SENIOR_RE.test(p.position);
  }
}

// --- Grouping -------------------------------------------------------------------------

const YEAR_RE = /(\d{4})\s*[-–to ]+\s*(\d{4})/;

function buildGroups() {
  const target = $("targetCompany").value.trim().toLowerCase();
  const myCos = $("myCompanies").value.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  const ym = $("collegeYears").value.match(YEAR_RE);
  const [y0, y1] = ym ? [+ym[1], +ym[2]] : [0, 0];
  const currentCos = S.positions.filter((p) => p.current).map((p) => p.co);
  const curCo = currentCos[0] || myCos[0] || "";
  const schools = S.edu.map((e) => e.school).join(", ");

  const eduMail = (p) => /\.edu(\.[a-z]{2})?$|\.ac\.[a-z]{2}$|@alumni\./i.test(p.email);
  const inCollege = (p) => (y1 && p.on && !isNaN(p.on) &&
    p.on.getFullYear() >= y0 && p.on.getFullYear() <= y1 + 1) || eduMail(p);

  const used = new Set();
  const take = (pred) => {
    const out = [];
    S.people.forEach((p, i) => { if (!used.has(i) && pred(p)) { used.add(i); out.push(p); } });
    out.sort((a, b) => b.score - a.score);
    return out;
  };

  const groups = [];
  if (target) {
    const g = take((p) => p.company.toLowerCase().includes(target));
    g.sort((a, b) => (b.door - a.door) || (b.score - a.score)); // doors first
    groups.push({
      title: `At ${cap(target)} — your way in`, icon: "🎯", kind: "referral", people: g,
      why: "They work at your target company right now. Recruiters, talent folks and senior people (⚡) are the fastest doors — most companies pay them a bonus for referring you.",
    });
  }
  groups.push({
    title: "They owe you one", icon: "🔁", kind: "reconnect",
    people: take((p) => p.recGiven),
    why: "You wrote them a recommendation — you've already vouched for them publicly. Reciprocity is the strongest ask there is.",
  });
  groups.push({
    title: "Referral talk already happened", icon: "💬", kind: "warm",
    people: take((p) => p.msgs && p.msgs.referral),
    why: "Your LinkedIn DMs with them already mention jobs, referrals, or interviews — the ice is pre-broken. Pick the thread back up.",
  });
  groups.push({
    title: "Inner circle", icon: "⭐", kind: "warm",
    people: take((p) => p.score >= 6 || p.srcs.size >= 2),
    why: "Highest relationship-strength in your whole network: real conversations, recommendations, and people who show up in your phone/Instagram/Facebook too — not just LinkedIn.",
  });
  if (curCo) {
    groups.push({
      title: `Your team & company (${cap(curCo)})`, icon: "🏢", kind: "referral",
      people: take((p) => p.company && p.company.toLowerCase().includes(curCo)),
      why: "They work where you work — the warmest possible referral, often with a bonus for them.",
    });
  }
  const pastCos = [...new Set([...S.positions.filter((p) => !p.current).map((p) => p.co), ...myCos.slice(1)])]
    .filter((c) => c && c !== curCo);
  if (pastCos.length) {
    groups.push({
      title: "Past colleagues", icon: "🕰️", kind: "reconnect",
      people: take((p) => pastCos.some((c) => p.company.toLowerCase().includes(c))),
      why: "You shipped things together once — a two-line “remember me?” reopens the door.",
    });
  }
  if (y1 || S.edu.length) {
    groups.push({
      title: "College-era connections", icon: "🎓", kind: "batchmate",
      people: take(inCollege),
      why: (schools ? `From your ${esc(schools)} years: ` : "") +
        `connected ${y0 || "?"}–${(y1 || 0) + 1} or carrying a college email domain — most are batchmates and department friends.`,
    });
  }
  if (S.external.length) {
    const ext = S.external.slice().sort((a, b) => (b.close - a.close) || (b.srcs.size - a.srcs.size));
    groups.push({
      title: "Close, but not on your LinkedIn", icon: "📱", kind: "friend",
      external: ext,
      why: "From your phone / Instagram / Facebook with no LinkedIn match. They can't refer you directly here — but they know people who can. Ask them who they know.",
    });
  }
  groups.push({
    title: "Everyone else", icon: "🌐", kind: "referral",
    people: take(() => true),
    why: "Search by company or role — the person one search away is often the one who refers you.",
    searchable: true,
  });
  return groups;
}

// --- Asks ----------------------------------------------------------------------------

function askFor(p, kind) {
  const first = p.first || String(p.name || "").split(" ")[0] || "there";
  const where = p.company ? ` at ${p.company}` : "";
  if (kind === "referral") {
    return `Hi ${first}! Hope you've been well 😊 I'm exploring PM roles${where ? ` and saw you're ${p.position || "working"}${where}` : ""} — if there's an opening that fits, would you be open to referring me? I'll send a short blurb + resume so it's zero work for you. Totally fine if it's not a good time!`;
  }
  if (kind === "warm") {
    return `Hey ${first}! Picking up our old thread 😄 I'm actively looking at PM roles right now — if anything's open${where} (or anywhere you'd vouch), I'd love a referral or a pointer. Blurb + resume ready so it's zero work for you!`;
  }
  if (kind === "reconnect") {
    return `Hey ${first}, it's been a while — hope things are great${where}! I'm exploring PM roles at the moment. If your company's hiring (or you know someone who is), would you be up for referring me or making an intro? Happy to send a short blurb + resume.`;
  }
  if (kind === "batchmate") {
    return `Hey ${first}! Long time since college 😄 I'm on the PM job hunt right now — if ${p.company || "your company"} has openings or you know a team that's hiring, a referral or intro would mean a lot. I'll send a blurb + resume, zero work for you!`;
  }
  // friend (not on LinkedIn)
  return `Hey ${first}! Quick one — I'm job-hunting for PM roles. You always know people 😄 anyone in your circle at companies hiring PMs who'd be up for a referral intro? Happy to send you a two-line blurb to forward.`;
}

// --- Rendering -----------------------------------------------------------------------

function srcBadges(p) {
  return [...p.srcs].filter((s) => SRC_BADGE[s]).map((s) => SRC_BADGE[s]).join("");
}

function personRow(p, gi, kind) {
  const name = p.name || `${p.first} ${p.last}`.trim();
  const link = p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(name)}</a>` : esc(name);
  const sub = [p.position, p.company].filter(Boolean).join(" · ");
  const when = p.on && !isNaN(p.on) ? `connected ${p.on.getFullYear()}` : "";
  const chips = (p.door ? [`<span class="pill hot">⚡ likely door</span>`] : [])
    .concat((p.chips || []).slice(0, 4).map((c) => `<span class="pill">${esc(c)}</span>`)).join("");
  return `<div class="person">
    <span class="who"><b>${link}</b> ${srcBadges(p)}<br><small>${esc(sub || "—")}${when ? ` · ${when}` : ""}</small>
      ${chips ? `<span class="chips">${chips}</span>` : ""}</span>
    <span class="act">
      ${p.email ? `<a class="btn small ghost" href="mailto:${esc(p.email)}?subject=${encodeURIComponent("Quick favor — referral?")}&body=${encodeURIComponent(askFor(p, kind))}">Email</a> ` : ""}
      <button class="btn small ghost copy-ask" data-g="${gi}" data-ask="${esc(askFor(p, kind))}">Copy ask</button>
    </span>
  </div>`;
}

function externalRow(e, gi) {
  const badges = [...e.srcs].map((s) => SRC_BADGE[s] || "").join("");
  return `<div class="person">
    <span class="who"><b>${esc(e.name)}</b> ${badges}${e.close ? ` <span class="pill hot">📸 close friend</span>` : ""}<br>
      <small>${esc(e.org || "not on your LinkedIn")}</small></span>
    <span class="act">
      ${e.emails && e.emails[0] ? `<a class="btn small ghost" href="mailto:${esc(e.emails[0])}?subject=${encodeURIComponent("Who do you know? 😄")}&body=${encodeURIComponent(askFor({ name: e.name }, "friend"))}">Email</a> ` : ""}
      <button class="btn small ghost copy-ask" data-g="${gi}" data-ask="${esc(askFor({ name: e.name }, "friend"))}">Copy ask</button>
    </span>
  </div>`;
}

function renderGroups() {
  computeScores();
  const groups = buildGroups();
  track("groups_built", {
    groups: groups.map((g) => ({ title: g.title, count: (g.people || g.external || []).length })),
    scored: S.sources.has("msg"),
    sources: [...S.sources.keys()],
  });
  $("groups").hidden = false;
  $("groups").innerHTML = `<div class="card"><h2>3 · Your referral paths</h2>
    <p class="hint">Ranked by relationship strength — DM history, recommendations, invites,
    endorsements, and whether they also show up in your phone/Instagram/Facebook.</p>` +
    groups.map((g, gi) => {
      const list = g.external
        ? g.external.slice(0, 150).map((e) => externalRow(e, gi)).join("")
        : g.people.slice(0, g.searchable ? 25 : 200).map((p) => personRow(p, gi, g.kind)).join("");
      const n = (g.people || g.external || []).length;
      return `
      <details class="fold" ${n && gi === 0 ? "open" : ""}>
        <summary>${g.icon} ${esc(g.title)} <span class="count">${n}</span></summary>
        <div class="fold-body">
          <p class="hint">${g.why}</p>
          ${g.searchable ? `<input type="text" class="grp-search" data-g="${gi}" placeholder="Filter by name, company, or role…" style="margin:0.4rem 0" />` : ""}
          <div class="grp-list" data-g="${gi}">
            ${list || "<p class='hint'>Nobody matched this bucket.</p>"}
          </div>
        </div>
      </details>`;
    }).join("") + `</div>`;

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
      const g = groups[+inp.dataset.g];
      const hits = g.people.filter((p) =>
        `${p.first} ${p.last} ${p.company} ${p.position}`.toLowerCase().includes(q)).slice(0, 50);
      inp.closest(".fold-body").querySelector(".grp-list").innerHTML =
        hits.map((p) => personRow(p, +inp.dataset.g, g.kind)).join("") || "<p class='hint'>No matches.</p>";
      wireCopyButtons(inp.closest(".fold-body"));
    };
  });
  function wireCopyButtons(scope) {
    scope.querySelectorAll(".copy-ask").forEach((b) => {
      b.onclick = async () => {
        try { await navigator.clipboard.writeText(b.dataset.ask); b.textContent = "✓ Copied"; }
        catch { b.textContent = "Copy failed"; }
        track("ask_copied", { group: +b.dataset.g });
        setTimeout(() => { b.textContent = "Copy ask"; }, 1600);
      };
    });
  }
}

// --- Import wiring ---------------------------------------------------------------

$("drop").onclick = () => $("file").click();
$("file").onchange = () => $("file").files.length && handleFiles([...$("file").files]);
["dragover", "dragleave", "drop"].forEach((ev) =>
  $("drop").addEventListener(ev, (e) => {
    e.preventDefault();
    $("drop").classList.toggle("over", ev === "dragover");
    if (ev === "drop" && e.dataTransfer.files.length) handleFiles([...e.dataTransfer.files]);
  }));
$("groupBtn").onclick = renderGroups;

// --- Pods (multiplayer) -------------------------------------------------------------
// The one server-backed feature on this page — see the consent copy in the HTML.

const Pod = { email: null, current: null };

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!d.ok) throw new Error(d.error || "request failed");
  return d;
}

function podMsg(t, bad) {
  const el = $("podMsg");
  el.textContent = t || "";
  el.classList.toggle("bad", !!bad);
}

async function loadPods(selectCode) {
  try {
    const d = await api("/api/pods/mine");
    const pods = d.pods || [];
    $("podTabs").innerHTML = pods.map((p) =>
      `<button class="chip pod-chip ${p.code === selectCode ? "on" : ""}" data-code="${esc(p.code)}">${esc(p.name)} · ${p.members}</button>`).join("")
      || `<span class="hint">No pods yet — create one and send friends the code.</span>`;
    $("podTabs").querySelectorAll(".pod-chip").forEach((b) => {
      b.onclick = () => openPod(b.dataset.code);
    });
    if (selectCode) openPod(selectCode);
    else if (pods.length === 1) openPod(pods[0].code);
  } catch (e) { podMsg(e.message, true); }
}

async function openPod(code) {
  try {
    const d = await api(`/api/pods/summary?code=${encodeURIComponent(code)}`);
    Pod.current = d;
    $("podTabs").querySelectorAll(".pod-chip").forEach((b) =>
      b.classList.toggle("on", b.dataset.code === d.code));
    renderPod();
  } catch (e) { podMsg(e.message, true); }
}

function renderPod() {
  const d = Pod.current;
  if (!d) { $("podView").hidden = true; return; }
  $("podView").hidden = false;
  const allCos = [...new Set(d.members.flatMap((m) => (m.companies || []).map((c) => c.company)))];
  $("podHead").innerHTML = `<b>${esc(d.name)}</b> — invite code
    <span class="pod-code">${esc(d.code)}</span>
    <button class="btn small ghost" id="podCopyCode">Copy invite</button>
    <button class="btn small ghost" id="podLeave">Leave pod</button>`;
  $("podExchange").innerHTML = allCos.length
    ? `<p class="hint">🔁 <b>Referral exchange:</b> between you, this pod can refer directly into
       ${allCos.slice(0, 12).map((c) => `<span class="pill">${esc(cap(c))}</span>`).join(" ")}${allCos.length > 12 ? " +" + (allCos.length - 12) : ""}</p>`
    : `<p class="hint">🔁 Nobody has shared their work history yet — share yours below to start the exchange.</p>`;
  $("podMembers").innerHTML = `<table class="pod-table"><tr><th>member</th><th>can refer into</th><th>network shared</th><th>mutuals with you</th></tr>` +
    d.members.map((m) => `<tr${m.you ? ' class="pod-row-you"' : ""}>
      <td>${esc(m.display)}${m.you ? " (you)" : ""}</td>
      <td>${(m.companies || []).map((c) => esc(cap(c.company)) + (c.current ? " ←now" : "")).join(", ") || "—"}</td>
      <td>${m.shared ? m.connections.toLocaleString() + " connections" : "not yet"}</td>
      <td>${m.you ? "—" : m.mutuals.toLocaleString()}</td>
    </tr>`).join("") + `</table>`;
  $("podCopyCode").onclick = async () => {
    const invite = `Join my job-hunt pod "${d.name}" on PM Case Prep: go to ${location.origin}/referrals, sign in, and enter code ${d.code}. We pool who-can-refer-where — names stay on your device.`;
    try { await navigator.clipboard.writeText(invite); podMsg("Invite copied — paste it in your group chat."); } catch { podMsg("Copy failed", true); }
  };
  $("podLeave").onclick = async () => {
    try { await api("/api/pods/leave", { code: d.code }); Pod.current = null; renderPod(); loadPods(); podMsg("Left the pod (your shared rows were deleted)."); }
    catch (e) { podMsg(e.message, true); }
  };
  refreshPodShare();
}

function refreshPodShare() {
  const btn = $("podShareBtn");
  if (!btn) return;
  const withUrls = S.people.filter((p) => p.urlKey).length;
  const ready = !!Pod.current && withUrls > 0;
  btn.disabled = !ready;
  $("podShareHint").textContent = !Pod.current
    ? "Pick or create a pod first."
    : withUrls === 0
      ? "Load your LinkedIn export above first — there's nothing to share yet."
      : `Ready: ${withUrls.toLocaleString()} connections → irreversible hashes + company names, plus your work history. Names stay here.`;
}

async function sharePod() {
  const d = Pod.current;
  if (!d) return;
  const btn = $("podShareBtn");
  btn.disabled = true;
  btn.textContent = "Hashing locally…";
  try {
    const people = S.people.filter((p) => p.urlKey).slice(0, 30000);
    const rows = [];
    for (let i = 0; i < people.length; i += 500) {
      rows.push(...await Promise.all(people.slice(i, i + 500).map(async (p) => ({
        h: await sha256hex(p.urlKey), c: normCo(p.company),
      }))));
    }
    let companies = S.positions.map((p) => ({ company: p.company, current: p.current }));
    if (!companies.length) {
      companies = $("myCompanies").value.split(",").map((s) => s.trim()).filter(Boolean)
        .map((c, i) => ({ company: c, current: i === 0 }));
    }
    btn.textContent = "Uploading hashes…";
    const res = await api("/api/pods/graph", { code: d.code, companies, connections: rows });
    track("pod_shared", { connections: res.shared, companies: res.companies }); // counts only
    podMsg(`✓ Shared ${res.shared.toLocaleString()} hashed connections across ${res.companies} companies.`);
    openPod(d.code);
  } catch (e) { podMsg(e.message, true); }
  btn.textContent = "Share my network map with this pod";
  refreshPodShare();
}

async function whoSearch() {
  const d = Pod.current;
  const q = $("podWhoInput").value.trim();
  if (!d || q.length < 2) return;
  try {
    const res = await api(`/api/pods/who?code=${encodeURIComponent(d.code)}&company=${encodeURIComponent(q)}`);
    const rows = res.results || [];
    track("pod_who_searched", { results: rows.length }); // counts only — never the company
    $("podWhoOut").innerHTML = rows.length
      ? rows.map((r) => {
        const ask = `Hey ${r.display}! Our pod map says you know ${r.count} ${r.count === 1 ? "person" : "people"} at ${q}. Any chance one of them would be up for a referral intro for me? Happy to send a two-line blurb + resume 🙏`;
        return `<div class="who-row"><b>${esc(r.display)}${r.you ? " (you)" : ""}</b>
          <span>${r.count.toLocaleString()} ${r.count === 1 ? "connection" : "connections"} at “${esc(q)}”</span>
          ${r.you ? `<span class="hint">check your 🎯 bucket above</span>`
            : `<button class="btn small ghost who-ask" data-ask="${esc(ask)}">Copy intro ask</button>`}
        </div>`;
      }).join("")
      : `<p class="hint">Nobody in this pod has shared connections at “${esc(q)}” yet.</p>`;
    $("podWhoOut").querySelectorAll(".who-ask").forEach((b) => {
      b.onclick = async () => {
        try { await navigator.clipboard.writeText(b.dataset.ask); b.textContent = "✓ Copied"; } catch { /* noop */ }
        setTimeout(() => { b.textContent = "Copy intro ask"; }, 1600);
      };
    });
  } catch (e) { podMsg(e.message, true); }
}

function initPods() {
  PMCP.mountAuth($("podAuth"), {
    reason: "Pods need a login so your friends' pods can recognize you.",
    onLogin: (email) => {
      Pod.email = email;
      $("podAuth").innerHTML = `<p class="hint">Signed in as <b>${esc(email)}</b></p>`;
      $("podPanel").hidden = false;
      loadPods();
    },
  });
  $("podCreateBtn").onclick = async () => {
    const name = $("podCreateName").value.trim();
    if (!name) { podMsg("Give the pod a name first.", true); return; }
    try {
      const d = await api("/api/pods", { name });
      track("pod_created", {});
      $("podCreateName").value = "";
      podMsg(`✓ Pod created — invite code ${d.pod.code}. Send it to your friends.`);
      loadPods(d.pod.code);
    } catch (e) { podMsg(e.message, true); }
  };
  $("podJoinBtn").onclick = async () => {
    const code = $("podJoinCode").value.trim().toUpperCase();
    if (code.length < 6) { podMsg("Enter the 6-character code.", true); return; }
    try {
      const d = await api("/api/pods/join", { code });
      track("pod_joined", {});
      $("podJoinCode").value = "";
      podMsg(`✓ Joined “${d.pod.name}”.`);
      loadPods(d.pod.code);
    } catch (e) { podMsg(e.message, true); }
  };
  $("podShareBtn").onclick = sharePod;
  $("podWhoBtn").onclick = whoSearch;
  $("podWhoInput").addEventListener("keydown", (e) => { if (e.key === "Enter") whoSearch(); });
}

initPods();

// --- Future connectors (demand test) ------------------------------------------
// Phone contacts, Instagram, and Facebook graduated into the live importer
// above. What's left is honest about what's technically possible; the
// "I'd use this" click tells us which connector to actually build next.

const CONNECTORS = [
  {
    name: "Google Contacts (one-click sync)", icon: "📇", status: "buildable now",
    what: "You can already drop a Google Contacts export above — this would make it one Google popup instead (you're already signing in with Google here). Great for keeping the 'close friends' layer fresh without re-exporting.",
  },
  {
    name: "Gmail frequency signals", icon: "✉️", status: "possible, but heavy",
    what: "Who you actually email is the best closeness signal there is. But Gmail metadata is a Google 'restricted' scope — apps need an annual paid security audit to use it — so this only makes sense once enough people want it.",
  },
  {
    name: "WhatsApp", icon: "💚", status: "no bulk export exists",
    what: "WhatsApp only exports one chat at a time — there's no honest way to read your whole graph. Your phone contacts file (already supported above) is the closest proxy: your phonebook ≈ your WhatsApp network.",
  },
  {
    name: "College alumni directory", icon: "🎓", status: "manual for now",
    what: "University portals block automated access, but LinkedIn's own alumni tool (linkedin.com/school/your-school/people) filters your school's alumni by company and field — find them there, then match the names in your export here. Your Education.csv already powers the college bucket automatically.",
  },
  {
    name: "Slack workspace directory", icon: "💬", status: "buildable, per-workspace",
    what: "Your workplace Slack knows your real team. A user-level connection can read the member roster (name, title) — though some company admins restrict app installs.",
  },
];

$("connectors").innerHTML = CONNECTORS.map((c) => `
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
