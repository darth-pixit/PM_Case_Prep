// Shared plumbing for the experiment pages (/arena, /recruiter, /referrals).
// Two jobs, one file:
//  * ANALYTICS with hard separation: every page declares its experiment name;
//    it's registered as a PostHog super property AND prefixed onto event names,
//    so each experiment's funnel/dashboards never bleed into another's.
//  * ONE LOGIN for the whole deploy: a mountable widget with two passwordless
//    doors — Google Sign-In and an emailed one-time code. No passwords exist,
//    so there is nothing to forget or reset.
//
// Usage:  const x = PMCP.experiment("arena");  x.track("case_opened", {...});
//         PMCP.mountAuth(el, { reason: "…", onLogin: (email) => {...} });

window.PMCP = (() => {
  let phReady = false;
  const phQueue = [];
  let pendingIdentify = null; // login can finish before array.js loads
  let expName = "unknown";
  let cfgPromise = null;

  const config = () => {
    if (!cfgPromise) cfgPromise = fetch("/config").then((r) => r.json()).catch(() => ({}));
    return cfgPromise;
  };

  function experiment(name) {
    expName = name;
    config().then((cfg) => {
      if (!cfg.posthog_key) return;
      const assets = cfg.posthog_host.replace(".i.posthog.com", "-assets.i.posthog.com");
      const s = document.createElement("script");
      s.src = assets + "/static/array.js";
      s.onload = () => {
        window.posthog.init(cfg.posthog_key, {
          api_host: cfg.posthog_host,
          defaults: "2025-05-24",
          person_profiles: "always",
        });
        // The super property rides on EVERY event (pageviews + autocapture
        // included) — dashboards filter on it to keep experiments separate.
        window.posthog.register({ experiment: name });
        phReady = true;
        if (pendingIdentify) { window.posthog.identify(pendingIdentify); pendingIdentify = null; }
        phQueue.splice(0).forEach(([n, p]) => window.posthog.capture(n, p));
      };
      document.head.appendChild(s);
    });
    return { track };
  }

  function track(event, props) {
    const name = expName + "_" + event;
    if (phReady) window.posthog.capture(name, props || {});
    else phQueue.push([name, props || {}]);
  }

  function identify(email) {
    if (!email) return;
    if (phReady) window.posthog.identify(email);
    else pendingIdentify = email; // replayed the moment PostHog loads
  }

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // --- Auth widget ----------------------------------------------------------

  async function whoami() {
    try { return await (await fetch("/api/me")).json(); } catch { return {}; }
  }

  // Renders the two-door login into `el`. Calls onLogin(email) once signed in
  // (including when the visitor already was). Never throws.
  async function mountAuth(el, opts) {
    const { reason = "", onLogin = () => {} } = opts || {};
    const me = await whoami();
    if (me.email) {
      identify(me.email); // returning visitors count as this person too
      onLogin(me.email, { already: true });
      return;
    }

    el.innerHTML = `
      <div class="auth-box">
        ${reason ? `<p class="auth-reason">${reason}</p>` : ""}
        <div class="auth-google" id="authGoogle"></div>
        ${me.google_client_id && me.email_login ? `<div class="auth-or"><span>or</span></div>` : ""}
        ${me.email_login ? `
        <div class="auth-email" id="authEmailStep1">
          <input id="authEmail" type="email" inputmode="email" autocomplete="email"
                 placeholder="you@email.com" />
          <button id="authSend" class="btn">Email me a code</button>
        </div>
        <div class="auth-email" id="authEmailStep2" hidden>
          <input id="authCode" type="text" inputmode="numeric" autocomplete="one-time-code"
                 maxlength="6" placeholder="6-digit code" />
          <button id="authVerify" class="btn">Sign in</button>
        </div>` : ""}
        <small id="authMsg" class="auth-msg"></small>
        <small class="auth-fine">No password — ever. We only use your email to save
        your progress across devices.</small>
      </div>`;

    const msg = (t, bad) => {
      const m = el.querySelector("#authMsg");
      m.textContent = t; m.classList.toggle("bad", !!bad);
    };

    const finish = (d, how) => {
      track("login", { how, restored: !!d.restored });
      identify(d.email);
      onLogin(d.email, d);
    };

    // Door 1: Google. The GSI script renders the official button; its callback
    // hands us a signed ID token which the server verifies against Google.
    if (me.google_client_id) {
      const g = document.createElement("script");
      g.src = "https://accounts.google.com/gsi/client";
      g.async = true;
      g.onload = () => {
        try {
          window.google.accounts.id.initialize({
            client_id: me.google_client_id,
            callback: async (resp) => {
              try {
                const r = await fetch("/api/auth/google", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ credential: resp.credential }),
                });
                const d = await r.json();
                if (d.ok) finish(d, "google");
                else msg(d.error || "Google sign-in failed", true);
              } catch { msg("Network problem — try again.", true); }
            },
          });
          window.google.accounts.id.renderButton(el.querySelector("#authGoogle"), {
            theme: "filled_black", size: "large", width: 280, text: "continue_with",
          });
        } catch { /* GSI unavailable (blocked script) — email door still works */ }
      };
      document.head.appendChild(g);
    }

    // Door 2: emailed one-time code.
    if (me.email_login) {
      const email = () => el.querySelector("#authEmail").value.trim().toLowerCase();
      el.querySelector("#authSend").onclick = async () => {
        if (!email().includes("@")) { msg("Enter your email first.", true); return; }
        el.querySelector("#authSend").disabled = true;
        try {
          const r = await fetch("/api/auth/email/request", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email() }),
          });
          const d = await r.json();
          if (d.ok) {
            el.querySelector("#authEmailStep2").hidden = false;
            msg(d.dev_code ? `Dev mode — your code is ${d.dev_code}` : "Code sent — check your inbox (and spam).");
            if (d.dev_code) el.querySelector("#authCode").value = d.dev_code;
            el.querySelector("#authCode").focus();
          } else msg(d.error || "Couldn't send the code.", true);
        } catch { msg("Network problem — try again.", true); }
        el.querySelector("#authSend").disabled = false;
      };
      el.querySelector("#authVerify").onclick = async () => {
        const code = el.querySelector("#authCode").value.trim();
        if (code.length < 6) { msg("Enter the 6-digit code.", true); return; }
        el.querySelector("#authVerify").disabled = true;
        try {
          const r = await fetch("/api/auth/email/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email(), code }),
          });
          const d = await r.json();
          if (d.ok) finish(d, "email_code");
          else { msg(d.error || "Wrong code.", true); el.querySelector("#authVerify").disabled = false; }
        } catch {
          msg("Network problem — try again.", true);
          el.querySelector("#authVerify").disabled = false;
        }
      };
      el.querySelector("#authCode").addEventListener("keydown", (e) => {
        if (e.key === "Enter") el.querySelector("#authVerify").click();
      });
      el.querySelector("#authEmail").addEventListener("keydown", (e) => {
        if (e.key === "Enter") el.querySelector("#authSend").click();
      });
    }

    if (!me.google_client_id && !me.email_login) {
      msg("Login isn't configured on this deploy yet — set PMCP_GOOGLE_CLIENT_ID and/or PMCP_RESEND_KEY.", true);
    }
  }

  return { experiment, track, identify, mountAuth, whoami, esc };
})();
