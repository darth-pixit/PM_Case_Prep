"""FastAPI backend.

One WebSocket per session ties together:
  * always-on mic audio (from the browser) -> Deepgram streaming -> word timings,
  * a text box (typed input) that feeds the SAME conversation,
  * the Interviewer, Grader (rubric + delivery fusion), and SkillGraph.

Design choices that matter for the interview feel and stability:
  * Voice runs on its own supervised channel (`Voice`) with KeepAlive + auto
    reconnect. A Deepgram hiccup never tears down the session — text keeps working.
  * Spoken fragments are COALESCED: we only hand a turn to the interviewer after a
    real pause (SILENCE_S), so thinking-out-loud doesn't trigger a reply per
    sentence. The interviewer is also prompted to stay silent by default and emits
    "(listening)" when it should say nothing — we suppress that.
  * Delivery metrics accumulate silently and surface only in the final scorecard.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlsplit

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import anthropic
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles

from ..case_loader import (
    arena_case_by_id,
    arena_catalog,
    default_case_path,
    load_case,
)
from ..delivery import FILLERS_CORE, DeliveryTracker, Word
from ..grader import grade, weighted_result
from ..interviewer import Interviewer
from ..models import Case
from ..recruiter_kb import recruiter_guide, recruiter_system_prompt
from ..resources import resources_for
from ..skill_graph import SkillGraph
from . import auth
from .deepgram_live import DG_URL, FLUX_ACTIVE, FLUX_URL, NOVA_URL, DeepgramLive

# Two model tiers: the interviewer runs on a FAST model (conversational turns,
# snappy replies); the grader runs on the deepest model (one careful call at
# the end). PMCP_MODEL overrides both; the specific vars override per-role.
_MODEL_OVERRIDE = os.environ.get("PMCP_MODEL")
INTERVIEWER_MODEL = os.environ.get(
    "PMCP_INTERVIEWER_MODEL", _MODEL_OVERRIDE or "claude-sonnet-5"
)
GRADER_MODEL = os.environ.get("PMCP_GRADER_MODEL", _MODEL_OVERRIDE or "claude-opus-4-8")
# Turn-taking. With Flux (the default STT), turn boundaries come from Deepgram's
# SEMANTIC end-of-turn model and we commit immediately — no timer. With nova-3
# we fall back to a single DEBOUNCED pause timer: the turn commits only after
# PAUSE_S of true silence since your last words, and any speech RE-ARMS it, so a
# whole answer (with internal thinking pauses) is one turn and it never fires
# mid-thought. One clock, not the old two-timer split that interrupted people.
PAUSE_S = float(os.environ.get("PMCP_SILENCE_S", "2.5"))
# Utterances below this Deepgram confidence are treated as noise (keyboard
# clatter, coughs, background voices) and never become turns.
MIN_CONFIDENCE = float(os.environ.get("PMCP_MIN_CONFIDENCE", "0.6"))
# Product analytics (PostHog). The project key is publishable by design — it can
# only ingest events, never read them — so serving it to the browser is safe.
POSTHOG_KEY = os.environ.get("PMCP_POSTHOG_KEY", "")
POSTHOG_HOST = os.environ.get("PMCP_POSTHOG_HOST", "https://us.i.posthog.com")
DB_PATH = os.environ.get("PMCP_DB", "skill_graph.db")
UID_COOKIE = "pmcp_uid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 730  # two years
STATIC_DIR = Path(__file__).resolve().parent / "static"
HINT_PROMPT = (
    "[The candidate asks for a hint. Give ONE graduated nudge for where they are "
    "right now — a question or a pointer to the missing dimension. Do not solve it.]"
)

# --- Abuse guards -------------------------------------------------------------
# Every /ws session drives PAID calls (Claude per turn + a Deepgram stream), so
# the socket is gated: same-origin browsers carrying the visitor cookie only,
# hourly open-rate and concurrent-session caps per IP / per visitor / global,
# and in-session ceilings on turns, duration, idle time, and text size. Limits
# are in-process state — fine for the single-instance deploy; use a shared
# store if this ever scales out.
MAX_SESSIONS = int(os.environ.get("PMCP_MAX_SESSIONS", "25"))
MAX_SESSIONS_PER_IP = int(os.environ.get("PMCP_MAX_SESSIONS_PER_IP", "4"))
MAX_SESSIONS_PER_UID = int(os.environ.get("PMCP_MAX_SESSIONS_PER_UID", "2"))
WS_HOURLY_PER_IP = int(os.environ.get("PMCP_WS_HOURLY_PER_IP", "30"))
LOGIN_HOURLY_PER_IP = int(os.environ.get("PMCP_LOGIN_HOURLY_PER_IP", "10"))
MAX_TURNS = int(os.environ.get("PMCP_MAX_TURNS", "80"))  # model calls per session
MAX_SESSION_S = 60 * int(os.environ.get("PMCP_MAX_SESSION_MIN", "90"))
IDLE_S = 60 * int(os.environ.get("PMCP_IDLE_MIN", "15"))
MAX_TEXT_CHARS = int(os.environ.get("PMCP_MAX_TEXT_CHARS", "8000"))
# Recruiter copilot (its own experiment, its own dials): each reply is one paid
# model call, so it gets per-IP rate limits and hard caps on history and size.
RECRUITER_MODEL = os.environ.get(
    "PMCP_RECRUITER_MODEL", _MODEL_OVERRIDE or "claude-sonnet-5"
)
RECRUITER_HOURLY_PER_IP = int(os.environ.get("PMCP_RECRUITER_HOURLY_PER_IP", "40"))
RECRUITER_MAX_HISTORY = 30  # messages of context kept per request
RECRUITER_MAX_CHARS = 6000  # per-message input cap
AUTH_HOURLY_PER_IP = int(os.environ.get("PMCP_AUTH_HOURLY_PER_IP", "20"))


class SlidingLimit:
    """Sliding-window rate limiter: at most `limit` hits per `window_s` per key."""

    def __init__(self, limit: int, window_s: float, now_fn: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_s
        self._now = now_fn
        self._hits: dict[str, deque] = {}

    def allow(self, key: str) -> bool:
        now = self._now()
        if len(self._hits) > 4096:  # keep memory bounded under key churn
            self._hits = {k: v for k, v in self._hits.items() if v}
        dq = self._hits.setdefault(key, deque())
        while dq and now - dq[0] > self.window:
            dq.popleft()
        if len(dq) >= self.limit:
            return False
        dq.append(now)
        return True


class Gauge:
    """Concurrent-session counts by key (inc/dec must be paired)."""

    def __init__(self):
        self._n: dict[str, int] = {}

    def get(self, key: str) -> int:
        return self._n.get(key, 0)

    def inc(self, key: str) -> None:
        self._n[key] = self._n.get(key, 0) + 1

    def dec(self, key: str) -> None:
        left = self._n.get(key, 0) - 1
        if left > 0:
            self._n[key] = left
        else:
            self._n.pop(key, None)


WS_OPENS = SlidingLimit(WS_HOURLY_PER_IP, 3600)
LOGIN_ATTEMPTS = SlidingLimit(LOGIN_HOURLY_PER_IP, 3600)
AUTH_ATTEMPTS = SlidingLimit(AUTH_HOURLY_PER_IP, 3600)
# Per-EMAIL brakes, independent of IP: a code request sends a real email to a
# real inbox (bombing + Resend quota burn), and capping verifies per address
# stops the reset-the-attempt-counter-with-a-fresh-code guessing loop.
CODE_REQUESTS_PER_EMAIL = SlidingLimit(3, 3600)
VERIFIES_PER_EMAIL = SlidingLimit(10, 3600)
RECRUITER_CALLS = SlidingLimit(RECRUITER_HOURLY_PER_IP, 3600)
ACTIVE = Gauge()


def _client_ip(conn) -> str:
    """Real client IP for rate-limit keys. Behind Render's proxy the socket
    peer is the proxy, so read X-Forwarded-For — but take the LAST hop, not
    the first: the last entry is written by the trusted proxy in front of us,
    while the first is whatever the client typed into the header. Keying
    limits on the first hop would let anyone reset their own limit per
    request with a forged header. Falls back to the socket peer for local dev."""
    xff = conn.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return conn.client.host if conn.client else "unknown"


def _same_origin(conn) -> bool:
    """Browsers always send Origin on WebSocket handshakes — reject ones from
    foreign pages (drive-by embedding). Non-browser clients omit Origin and
    fall through to the cookie + rate-limit gates instead."""
    origin = conn.headers.get("origin")
    if not origin:
        return True
    return urlsplit(origin).netloc == conn.headers.get("host", "")


# /docs, /redoc and /openapi.json are free recon (endpoints, models, stack) —
# off in production. Flip on locally by running with PMCP_DEV_DOCS=1.
_DOCS = {} if os.environ.get("PMCP_DEV_DOCS") else {
    "docs_url": None, "redoc_url": None, "openapi_url": None
}
app = FastAPI(title="PM Case Prep", **_DOCS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


_SENTINEL_RE = re.compile(r"\(\s*listening\.?\s*\)", re.IGNORECASE)


def _visible_reply(reply: str) -> str:
    """What the candidate should actually SEE. Empty string = stay silent.

    The model is told a silent turn is exactly "(listening)". But if it wraps a
    real answer around the sentinel, swallowing everything would drop an answer
    the model believes it delivered — the candidate then hears "as I said…"
    about words that never reached the screen. So: strip the sentinel, and if
    substantial text remains, show that text; only near-empty remainders are
    true silence."""
    if not reply:
        return ""
    if _SENTINEL_RE.search(reply):
        remainder = " ".join(_SENTINEL_RE.sub(" ", reply).split())
        return remainder if len(remainder) >= 60 else ""
    if "".join(c for c in reply.lower() if c.isalpha()) in ("", "listening"):
        return ""
    return reply.strip()


def _flux_words(evt: dict) -> list[Word]:
    """Build Word objects from a Flux EndOfTurn event.

    Flux returns word text + confidence but (unlike nova-3) NO per-word
    start/end times — only a turn-level audio window. So when timing is absent,
    spread the words evenly across [audio_window_start, audio_window_end]. That
    keeps words-per-minute honest (total duration is real); per-word pause
    detection is necessarily coarser on Flux, which we accept for its far
    better turn-taking."""
    raw = [w for w in (evt.get("words") or []) if isinstance(w, dict)]
    tokens = [w.get("word", "") for w in raw]
    if raw and all(("start" in w and "end" in w) for w in raw):
        return [Word(w["word"], float(w["start"] or 0), float(w["end"] or 0)) for w in raw]
    if not tokens:
        tokens = (evt.get("transcript") or "").split()
    start = float(evt.get("audio_window_start") or 0)
    end = float(evt.get("audio_window_end") or 0)
    n = len(tokens)
    if n == 0:
        return []
    step = (end - start) / n if end > start else 0.0
    return [Word(t, start + i * step, start + (i + 1) * step) for i, t in enumerate(tokens)]


# Pure disfluencies — an utterance made only of these is a murmur, not a turn.
_MURMURS = FILLERS_CORE | {"mm", "mhm", "hm", "huh"}


def _is_noise(text: str, confidence: float) -> bool:
    """Keyboard taps, coughs, murmurs, and cross-talk show up as short
    low-confidence fragments or bare fillers. They must never become turns —
    each junk turn is a model call that blocks the queue and can trip a
    spurious reply."""
    words = [w.lower() for w in re.findall(r"[a-zA-Z']+", text)]
    real = [w for w in words if len(w) >= 2 and w not in _MURMURS]
    return confidence < MIN_CONFIDENCE or not real


@app.get("/")
async def index(request: Request) -> FileResponse:
    """Serve the app and give every visitor a stable anonymous identity, so
    their skill graph is theirs alone even before they log in."""
    resp = FileResponse(STATIC_DIR / "index.html")
    if not request.cookies.get(UID_COOKIE):
        resp.set_cookie(
            UID_COOKIE, uuid.uuid4().hex, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
    return resp


def _auth_flags() -> dict:
    """Which login doors exist on this deploy — served by /config AND /api/me
    so the room page and the login widget can never disagree."""
    return {
        "google_client_id": auth.GOOGLE_CLIENT_ID,
        "email_login": auth.email_enabled()
        or bool(os.environ.get("PMCP_DEV_DOCS") and not os.environ.get("RENDER")),
    }


@app.get("/config")
async def config(request: Request) -> JSONResponse:
    """Public, browser-safe config. No secrets — the PostHog key is publishable
    and the Google client id is public by design (it's in every login page)."""
    return JSONResponse(
        {
            "posthog_key": POSTHOG_KEY,
            "posthog_host": POSTHOG_HOST,
            "email": _email_for_request(request),
            **_auth_flags(),
        }
    )


@app.post("/api/login")
async def login(request: Request) -> JSONResponse:
    """The tutor scorecard's "save my progress" box (legacy, no verification).

    New email -> links this browser's uid to it. But a KNOWN email now refuses
    to switch uids: handing over a stored account on a bare typed email would
    let anyone claim anyone, and since the arena/recruiter gates trust an
    email-linked cookie, that would also unlock the paid features as the
    victim. Restoring an existing account requires the PROVEN doors
    (/api/auth/google or the emailed code)."""
    if not LOGIN_ATTEMPTS.allow(_client_ip(request)):
        return JSONResponse(
            {"ok": False, "error": "too many attempts — try again later"}, status_code=429
        )
    try:
        data = await request.json()
        assert isinstance(data, dict)  # "hi" / [1] are valid JSON, not requests
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=400)
    email = str(data.get("email") or "").strip().lower()
    if not auth.valid_email(email):
        return JSONResponse({"ok": False, "error": "invalid email"}, status_code=400)

    uid = request.cookies.get(UID_COOKIE) or uuid.uuid4().hex
    g = SkillGraph(DB_PATH, uid)
    try:
        existing = g.uid_for_email(email)
        if existing and existing != uid:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "That email already has saved progress. To restore "
                    "it, sign in on the Arena page (Google or a code we email "
                    "you) — your history follows automatically.",
                },
                status_code=409,
            )
        g.link_email(email, uid)
        sessions = g.sessions_count()
    finally:
        g.close()

    resp = JSONResponse(
        {"ok": True, "email": email, "restored": False, "sessions": sessions}
    )
    resp.set_cookie(UID_COOKIE, uid, max_age=COOKIE_MAX_AGE, samesite="lax")
    return resp


# --- Shared auth (all experiments) --------------------------------------------
# One login, two passwordless doors: a verified Google ID token, or a one-time
# emailed code. Both land in _finish_login, which links the verified email to
# the visitor's uid exactly like /api/login — but here the email is PROVEN,
# so an arena/recruiter account can't be claimed by typing someone's address.

def _finish_login(request: Request, email: str) -> JSONResponse:
    anon_uid = request.cookies.get(UID_COOKIE) or uuid.uuid4().hex
    uid = anon_uid
    g = SkillGraph(DB_PATH, uid)
    try:
        existing = g.uid_for_email(email)
        restored = bool(existing and existing != uid)
        if restored:
            uid = existing
        else:
            g.link_email(email, uid)
        g2 = SkillGraph(DB_PATH, uid)
        if restored:
            g2.merge_from(anon_uid)
        sessions = g2.sessions_count()
        g2.close()
    finally:
        g.close()
    resp = JSONResponse(
        {"ok": True, "email": email, "restored": restored, "sessions": sessions}
    )
    resp.set_cookie(UID_COOKIE, uid, max_age=COOKIE_MAX_AGE, samesite="lax")
    return resp


def _email_for_request(request: Request) -> str | None:
    uid = request.cookies.get(UID_COOKIE)
    if not uid:
        return None
    g = SkillGraph(DB_PATH, uid)
    try:
        return g.email_for_uid(uid)
    finally:
        g.close()


@app.get("/api/me")
async def me(request: Request) -> JSONResponse:
    return JSONResponse({"email": _email_for_request(request), **_auth_flags()})


@app.post("/api/auth/google")
async def auth_google(request: Request) -> JSONResponse:
    if not AUTH_ATTEMPTS.allow(_client_ip(request)):
        return JSONResponse(
            {"ok": False, "error": "too many attempts — try again later"}, status_code=429
        )
    try:
        data = await request.json()
        assert isinstance(data, dict)  # "hi" / [1] are valid JSON, not requests
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=400)
    email = await asyncio.to_thread(
        auth.verify_google_token, str(data.get("credential") or "")
    )
    if not email:
        # Only point to the email door when it actually exists on this deploy.
        # A Google-only deploy renders no email field, so "try the email code
        # instead" would send the user to a door that isn't there — mirror what
        # the login widget actually shows (same _auth_flags the frontend reads).
        hint = " — try the email code instead" if _auth_flags()["email_login"] else ""
        return JSONResponse(
            {"ok": False, "error": f"Google sign-in failed{hint}"},
            status_code=401,
        )
    return _finish_login(request, email)


@app.post("/api/auth/email/request")
async def auth_email_request(request: Request) -> JSONResponse:
    if not AUTH_ATTEMPTS.allow(_client_ip(request)):
        return JSONResponse(
            {"ok": False, "error": "too many attempts — try again later"}, status_code=429
        )
    try:
        data = await request.json()
        assert isinstance(data, dict)  # "hi" / [1] are valid JSON, not requests
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=400)
    email = str(data.get("email") or "").strip().lower()
    if not auth.valid_email(email):
        return JSONResponse({"ok": False, "error": "invalid email"}, status_code=400)
    if not CODE_REQUESTS_PER_EMAIL.allow(email):
        # Independent of IP: stops inbox-bombing a victim from many addresses.
        return JSONResponse(
            {"ok": False, "error": "a code was already sent — check your inbox"},
            status_code=429,
        )
    codes = auth.AuthCodes(DB_PATH)
    try:
        code = codes.issue(email)
    finally:
        codes.close()
    if auth.email_enabled():
        sent = await asyncio.to_thread(auth.send_code_email, email, code)
        if not sent:
            return JSONResponse(
                {"ok": False, "error": "couldn't send the email — try again"},
                status_code=502,
            )
        return JSONResponse({"ok": True})
    if os.environ.get("PMCP_DEV_DOCS") and not os.environ.get("RENDER"):
        # Local dev without a Resend key: hand the code back so the flow is
        # testable end-to-end. Two independent guards keep it out of prod:
        # the dev flag must be ON and we must NOT be on Render (which sets
        # RENDER=true on every service) — so a stray PMCP_DEV_DOCS on the
        # deployed instance can't turn login codes into an open door.
        return JSONResponse({"ok": True, "dev_code": code})
    return JSONResponse(
        {"ok": False, "error": "email login isn't configured on this deploy"},
        status_code=503,
    )


@app.post("/api/auth/email/verify")
async def auth_email_verify(request: Request) -> JSONResponse:
    if not AUTH_ATTEMPTS.allow(_client_ip(request)):
        return JSONResponse(
            {"ok": False, "error": "too many attempts — try again later"}, status_code=429
        )
    try:
        data = await request.json()
        assert isinstance(data, dict)  # "hi" / [1] are valid JSON, not requests
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=400)
    email = str(data.get("email") or "").strip().lower()
    code = str(data.get("code") or "").strip()
    if not auth.valid_email(email) or not code:
        return JSONResponse({"ok": False, "error": "invalid email or code"}, status_code=400)
    if not VERIFIES_PER_EMAIL.allow(email):
        # Without this, requesting a fresh code resets the per-code attempt
        # counter — capping verifies per ADDRESS closes that guessing loop.
        return JSONResponse(
            {"ok": False, "error": "too many attempts for this email — wait a bit"},
            status_code=429,
        )
    codes = auth.AuthCodes(DB_PATH)
    try:
        ok = codes.verify(email, code)
    finally:
        codes.close()
    if not ok:
        return JSONResponse(
            {"ok": False, "error": "wrong or expired code — request a new one"},
            status_code=401,
        )
    return _finish_login(request, email)


# --- Experiment pages -----------------------------------------------------------
# Each experiment is its own page with its own analytics namespace, but they all
# share this one deploy, one domain, and one login. Keeping them at separate
# paths keeps funnels, heatmaps, and experience changes cleanly separable.

def _page(name: str, request: Request) -> FileResponse:
    resp = FileResponse(STATIC_DIR / name)
    if not request.cookies.get(UID_COOKIE):
        resp.set_cookie(
            UID_COOKIE, uuid.uuid4().hex, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
    return resp


@app.get("/arena")
async def arena_page(request: Request) -> FileResponse:
    return _page("arena.html", request)


@app.get("/recruiter")
async def recruiter_page(request: Request) -> FileResponse:
    return _page("recruiter.html", request)


@app.get("/referrals")
async def referrals_page(request: Request) -> FileResponse:
    return _page("referrals.html", request)


_CASE_ID_RE = re.compile(r"^[a-z0-9-]{1,80}$")


@app.get("/arena/room", response_model=None)
async def arena_room(request: Request, case: str = "") -> HTMLResponse | RedirectResponse:
    """The interview room, arena flavor: same static room page, but with the
    experiment + case id injected so analytics stay in the arena namespace and
    the WebSocket opens the chosen case. Login-gated — the arena asks for the
    account up front, so a bare/foreign uid goes back to the picker."""
    if not _CASE_ID_RE.match(case) or arena_case_by_id(case) is None:
        return RedirectResponse("/arena")
    if _email_for_request(request) is None:
        return RedirectResponse("/arena?login=1")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    # The room page carries an explicit injection marker; matching on it (not
    # on script-tag syntax) means an innocent index.html edit can't silently
    # turn arena sessions into default-tutor sessions.
    marker = "<!-- PMCP_INJECT"
    if marker not in html:
        raise RuntimeError("index.html lost its PMCP_INJECT marker")
    inject = (
        f'<script>window.PMCP_EXPERIMENT="arena";window.PMCP_CASE_ID="{case}";</script>'
    )
    html = html.replace(marker, inject + "\n  " + marker, 1)
    return HTMLResponse(html)


@app.get("/api/arena/catalog")
async def api_arena_catalog(request: Request) -> JSONResponse:
    """Categories, cases (public metadata only), and which ones THIS user has
    completed — so the picker can show progress ticks per category."""
    done: list[str] = []
    uid = request.cookies.get(UID_COOKIE)
    if uid:
        g = SkillGraph(DB_PATH, uid)
        try:
            done = sorted({h["case_id"] for h in g.history()})
        finally:
            g.close()
    return JSONResponse({"categories": arena_catalog(), "completed": done})


@app.post("/api/recruiter/chat")
async def recruiter_chat(request: Request) -> JSONResponse:
    """The recruiter copilot: one careful model call per message, grounded in
    the researched interview-landscape knowledge base. Login required (each
    call costs real money) and rate-limited per IP."""
    if _email_for_request(request) is None:
        return JSONResponse(
            {"ok": False, "error": "sign in first"}, status_code=401
        )
    if not RECRUITER_CALLS.allow(_client_ip(request)):
        return JSONResponse(
            {"ok": False, "error": "you're sending messages very fast — take a breath"},
            status_code=429,
        )
    try:
        data = await request.json()
        assert isinstance(data, dict)  # "hi" / [1] are valid JSON, not requests
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=400)
    raw = data.get("messages")
    if not isinstance(raw, list) or not raw:
        return JSONResponse({"ok": False, "error": "no messages"}, status_code=400)
    messages = []
    for m in raw[-RECRUITER_MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue  # a malformed item is a 400 below, never a 500 here
        role = m.get("role")
        text = str(m.get("text") or "").strip()[:RECRUITER_MAX_CHARS]
        if role in ("user", "assistant") and text:
            messages.append({"role": role, "content": text})
    # The Messages API requires the FIRST turn to be the user and rejects
    # consecutive same-role turns — both shapes appear naturally once the
    # history window trims mid-conversation, so normalize instead of 502ing.
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    merged: list[dict] = []
    for m in messages:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n" + m["content"]
        else:
            merged.append(m)
    messages = merged
    if not messages or messages[-1]["role"] != "user":
        return JSONResponse({"ok": False, "error": "no user message"}, status_code=400)

    client = anthropic.Anthropic()

    def call() -> str:
        resp = client.messages.create(
            model=RECRUITER_MODEL,
            max_tokens=2500,
            system=[
                {
                    "type": "text",
                    "text": recruiter_system_prompt(),
                    # Stable prefix reused across every recruiter on the site.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    try:
        reply = await asyncio.to_thread(call)
    except Exception as exc:  # noqa: BLE001
        # Log the real error server-side; the client gets a generic message —
        # raw SDK exceptions leak model/config details worth nothing to users.
        print(f"recruiter chat model error: {exc!r}", flush=True)
        return JSONResponse(
            {"ok": False, "error": "the copilot hit a snag — try that again"},
            status_code=502,
        )
    return JSONResponse({"ok": True, "reply": reply})


@app.get("/api/recruiter/guide")
async def api_recruiter_guide() -> JSONResponse:
    """The static field guide (question archetypes, concepts in plain english,
    learning links) — browsable without login; only the chat costs money."""
    return JSONResponse(recruiter_guide())


_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<text y=".9em" font-size="90">🎯</text></svg>'
)


@app.get("/favicon.ico")
async def favicon() -> Response:
    """Browsers request this on every page automatically — a real answer beats
    a 404 in every console."""
    return Response(_FAVICON, media_type="image/svg+xml")


@app.get("/health")
async def health() -> JSONResponse:
    """Deliberately bare — the verbose version (models, which keys exist, active
    STT) is recon material. Run with PMCP_DEV_DOCS=1 locally to get it back."""
    if not os.environ.get("PMCP_DEV_DOCS"):
        return JSONResponse({"ok": True})
    return JSONResponse(
        {
            "ok": True,
            "voice": bool(os.environ.get("DEEPGRAM_API_KEY")),
            "stt": "flux" if FLUX_ACTIVE else "nova-3",
            "anthropic_key": bool(
                os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            ),
            "interviewer_model": INTERVIEWER_MODEL,
            "grader_model": GRADER_MODEL,
        }
    )


class Voice:
    """Supervised Deepgram streaming channel. Auto-reconnects while audio is
    flowing, goes DORMANT (closed, waiting, silent) when it isn't — a muted or
    permission-less session must not churn reconnects or hold a paid stream.
    Never raises into the session (voice can drop without killing text).

    KeepAlive is sent on nova-3 ONLY: Flux rejects it as an unparsable client
    message (its protocol allows just CloseStream/Configure). Flux doesn't
    need it anyway — while the mic is on, the browser streams continuously
    (silence-gated frames included), and when audio stops we go dormant
    instead of holding the stream open."""

    # No audio for this long = the mic is off/blocked/muted -> dormant.
    IDLE_AUDIO_S = 5.0

    def __init__(
        self,
        api_key: str,
        handle_event: Callable[[dict], Awaitable[None]],
        notify: Callable[[str], Awaitable[None]],
    ):
        self._key = api_key
        self._handle = handle_event
        self._notify = notify
        self._dg: DeepgramLive | None = None
        self._task: asyncio.Task | None = None
        self._closed = False
        self._url = DG_URL
        self._last_audio = 0.0
        self._audio_evt = asyncio.Event()

    async def start(self) -> None:
        self._last_audio = asyncio.get_event_loop().time()
        self._task = asyncio.create_task(self._supervise())

    def _audio_flowing(self) -> bool:
        return asyncio.get_event_loop().time() - self._last_audio <= self.IDLE_AUDIO_S

    async def _say(self, msg: str) -> None:
        try:
            await self._notify(msg)
        except Exception:  # noqa: BLE001
            pass

    async def _supervise(self) -> None:
        backoff = 1.0
        fast_fails = 0  # consecutive near-instant drops (bad model/params)
        while not self._closed:
            if not self._audio_flowing():
                # Dormant: nothing to transcribe. Wait for send() to wake us —
                # no reconnect spam, no paid stream held open.
                self._audio_evt.clear()
                try:
                    await self._audio_evt.wait()
                except asyncio.CancelledError:
                    break
                if self._closed:
                    break
            keeper = None
            started = asyncio.get_event_loop().time()
            try:
                self._dg = DeepgramLive(self._key, self._url)
                await self._dg.__aenter__()
                backoff = 1.0
                await self._say("voice connected")  # client clears any banner
                if self._url == NOVA_URL:
                    keeper = asyncio.create_task(self._keepalive())
                async for evt in self._dg.events():
                    fast_fails = 0
                    await self._handle(evt)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001 - any drop -> reconnect below
                pass
            finally:
                if keeper is not None:
                    keeper.cancel()
                if self._dg is not None:
                    try:
                        await self._dg.__aexit__()
                    except Exception:  # noqa: BLE001
                        pass
                self._dg = None
            if self._closed:
                break
            # Experimental Flux model failing on connect? Fall back to nova-3
            # rather than looping — voice must keep working no matter what.
            if self._url == FLUX_URL and asyncio.get_event_loop().time() - started < 5.0:
                fast_fails += 1
                if fast_fails >= 2:
                    self._url = NOVA_URL
                    await self._say("voice: flux unavailable — using standard model")
            # Only announce a reconnect the candidate would feel — mid-speech.
            # A drop with no audio flowing just parks us dormant, silently.
            if self._audio_flowing():
                await self._say("voice reconnecting…")
                await asyncio.sleep(min(backoff, 5.0))
                backoff *= 2

    async def _keepalive(self) -> None:
        # nova-3 only (Flux rejects KeepAlive): holds the stream open through
        # long thinking pauses while the mic is muted. One failed send must
        # NOT kill the loop — skip the tick and keep beating.
        while not self._closed:
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                return
            dg = self._dg
            if dg is not None:
                try:
                    await dg.keepalive()
                except Exception:  # noqa: BLE001 - supervisor reconnects; keep ticking
                    pass

    async def send(self, data: bytes) -> None:
        self._last_audio = asyncio.get_event_loop().time()
        self._audio_evt.set()  # wakes a dormant supervisor
        dg = self._dg
        if self._closed or dg is None:
            return
        try:
            await dg.send_audio(data)
        except Exception:  # noqa: BLE001 - supervisor will reconnect
            pass

    async def stop(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
        if self._dg is not None:
            try:
                await self._dg.__aexit__()
            except Exception:  # noqa: BLE001
                pass


@app.websocket("/ws")
async def session_ws(ws: WebSocket) -> None:
    """Gate, then run. Accepting this socket means spending real money (model
    turns + an STT stream) on whoever is on the other end — so nobody gets a
    session without a same-origin page, a visitor cookie, and headroom in the
    per-IP / per-visitor / global caps."""
    ip = _client_ip(ws)
    uid = ws.cookies.get(UID_COOKIE)
    await ws.accept()

    async def reject(reason: str) -> None:
        try:
            await ws.send_json({"type": "error", "text": reason})
            await ws.close(code=1008)
        except Exception:  # noqa: BLE001
            pass

    if not _same_origin(ws):
        await reject("cross-origin connection refused")
        return
    if not uid:
        await reject("no session — reload the page")
        return
    if not WS_OPENS.allow(ip):
        await reject("too many new interviews from your network — try again later")
        return
    # Arena sessions name their case (?case=<id>) and require a signed-in user —
    # the page gates too, but the socket must hold on its own against scripts.
    case: Case | None = None
    case_id = ws.query_params.get("case") or ""
    if case_id:
        case = arena_case_by_id(case_id) if _CASE_ID_RE.match(case_id) else None
        if case is None:
            await reject("unknown case — pick one from the arena")
            return
        if _email_for_request(ws) is None:  # ws carries cookies just like a Request
            await reject("sign in on the arena page to start a case")
            return
    if (
        ACTIVE.get("all") >= MAX_SESSIONS
        or ACTIVE.get(f"ip:{ip}") >= MAX_SESSIONS_PER_IP
        or ACTIVE.get(f"uid:{uid}") >= MAX_SESSIONS_PER_UID
    ):
        await reject("the interviewer is at capacity — try again in a few minutes")
        return

    keys = ("all", f"ip:{ip}", f"uid:{uid}")
    for k in keys:
        ACTIVE.inc(k)
    try:
        await _run_session(ws, uid, case)
    finally:
        for k in keys:
            ACTIVE.dec(k)


async def _run_session(ws: WebSocket, uid: str, case: Case | None = None) -> None:
    case = case or load_case(default_case_path())
    client = anthropic.Anthropic()
    interviewer = Interviewer(client, case, INTERVIEWER_MODEL)
    tracker = DeliveryTracker()
    # Scope every score to this visitor's cookie identity — on a public host,
    # skill graphs must never mix across users.
    graph = SkillGraph(DB_PATH, uid)
    session_id = uuid.uuid4().hex[:8]
    voice_on = bool(os.environ.get("DEEPGRAM_API_KEY"))

    await ws.send_json(
        {
            "type": "case",
            "title": case.title,
            "prompt": case.prompt,
            "interviewer_name": case.interviewer_name,
            "archetype": case.archetype,
            "case_type": case.type,
            "voice": voice_on,
        }
    )
    await ws.send_json({"type": "state", "state": "listening"})

    turn_queue: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    current_words: list[Word] = []  # words accumulated for the in-progress turn
    current_conf: list[float] = []  # Deepgram confidence per finalized chunk
    commit_task: asyncio.Task | None = None

    async def send_json(payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001
            pass

    # --- turn commit ---------------------------------------------------------
    # ONE clock. commit_pending() hands the accumulated turn to the interviewer.
    # nova-3 arms a debounce (re-armed by any speech) so it fires only after a
    # real pause; Flux calls it directly from its semantic end-of-turn.

    async def commit_pending() -> None:
        nonlocal current_words, current_conf, commit_task
        if commit_task is not None and not commit_task.done():
            commit_task.cancel()
        commit_task = None
        words, confs = current_words, current_conf
        current_words, current_conf = [], []
        if not words:
            return
        text = " ".join(w.text for w in words).strip()
        if not text or _is_noise(text, max(confs) if confs else 0.0):
            return  # background noise — no metrics, no turn, no reply
        tracker.add_turn(words)  # metrics only — not shown live
        await turn_queue.put({"source": "voice", "text": text})

    async def _debounced_commit() -> None:
        try:
            await asyncio.sleep(PAUSE_S)
        except asyncio.CancelledError:
            return
        await commit_pending()

    def arm_commit() -> None:
        """(Re)start the pause countdown. Called on every bit of speech, so the
        turn commits only once you've genuinely stopped for PAUSE_S."""
        nonlocal commit_task
        if commit_task is not None and not commit_task.done():
            commit_task.cancel()
        commit_task = asyncio.create_task(_debounced_commit())

    async def handle_dg(evt: dict) -> None:
        nonlocal current_words, current_conf
        etype = evt.get("type")
        if etype == "Results":
            # nova-3 path: accumulate words; the pause timer decides the turn.
            alt = evt.get("channel", {}).get("alternatives", [{}])[0]
            transcript = alt.get("transcript", "")
            conf = float(alt.get("confidence") or 0.0)
            if len(transcript.strip()) >= 3 and conf >= 0.45:
                await send_json({"type": "listening"})  # pulse indicator
                arm_commit()  # still talking → push the commit later
            if evt.get("is_final") and transcript:
                current_conf.append(conf)
                for w in alt.get("words", []):
                    current_words.append(
                        Word(w.get("word", ""), float(w.get("start", 0)), float(w.get("end", 0)))
                    )
                arm_commit()
        elif etype == "TurnInfo":
            # Flux path: the model tells us when the turn is semantically over —
            # commit immediately, no timer. This is the whole point of Flux.
            event = evt.get("event", "")
            transcript = (evt.get("transcript") or "").strip()
            if transcript and event in ("Update", "StartOfTurn", "EagerEndOfTurn"):
                await send_json({"type": "listening"})
            if event == "EndOfTurn" and transcript:
                current_words.extend(_flux_words(evt))
                current_conf.append(float(evt.get("end_of_turn_confidence") or 1.0))
                await commit_pending()

    # --- grading + interviewer worker ----------------------------------------

    graded = False

    async def do_grade() -> None:
        # Idempotent: the done button, the turn cap, the session clock, and the
        # interviewer concluding can all race — exactly one Opus call happens.
        nonlocal graded
        if graded:
            return
        graded = True
        if voice is not None:
            await voice.stop()  # interview is over — stop paying for STT
        await send_json({"type": "state", "state": "grading"})
        delivery_summary = tracker.summary_text()
        try:
            card = await asyncio.to_thread(
                grade,
                client,
                case,
                interviewer.transcript(),
                interviewer.observations_text(),
                GRADER_MODEL,
                delivery_summary,
            )
        except Exception as exc:  # noqa: BLE001
            await send_json({"type": "error", "text": f"Grading failed: {exc}"})
            return
        weighted, _min_dim, band = weighted_result(case, card)
        graph.record(
            session_id,
            case.id,
            case.archetype,
            card,
            band,
            weighted=round(weighted, 2),
            transcript=interviewer.transcript(),
            delivery={
                "snapshot": tracker.snapshot(),
                "summary": delivery_summary,
            },
        )
        await send_json(
            {
                "type": "scorecard",
                "band": band,
                "weighted": round(weighted, 2),
                "card": card.model_dump(),
                "delivery": tracker.snapshot(),
                "delivery_summary": delivery_summary,
                "skill_graph": graph.render_summary(),
                "trajectory": graph.projection(),
                "resources": resources_for(card, case),
            }
        )

    async def interviewer_worker() -> None:
        # Turns can arrive faster than the model answers. Consecutive queued
        # turns are MERGED into one model call — so asking twice while a reply
        # is in flight yields one good answer, not a serial backlog of calls.
        pending: deque = deque()
        turns = 0
        while not stop.is_set():
            if not pending:
                pending.append(await turn_queue.get())
            while True:
                try:
                    pending.append(turn_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            item = pending.popleft()
            if item.get("cmd") == "__stop__":
                break
            if item.get("cmd") == "done":
                await do_grade()
                stop.set()
                break
            if item.get("cmd") == "hint":
                text = HINT_PROMPT
            else:
                texts = [item.get("text", "")]
                while pending and "cmd" not in pending[0]:
                    texts.append(pending.popleft().get("text", ""))
                text = "\n".join(t for t in texts if t.strip())
            if not text.strip():
                continue
            if turns >= MAX_TURNS:
                # Spend ceiling: a real interview is ~15-30 turns; anything
                # near the cap is a runaway (or a script). Grade and finish.
                await send_json(
                    {"type": "status", "text": "turn limit reached — grading now"}
                )
                await do_grade()
                stop.set()
                break
            turns += 1
            await send_json({"type": "state", "state": "responding"})
            try:
                reply = await asyncio.to_thread(interviewer.respond_content, text)
            except Exception as exc:  # noqa: BLE001
                await send_json({"type": "error", "text": f"Model error: {exc}"})
                await send_json({"type": "state", "state": "listening"})
                continue
            shown = _visible_reply(reply)
            # The model's memory must match the candidate's screen, always.
            interviewer.align_shown(shown or "(listening)")
            if shown:
                await send_json({"type": "reply", "text": shown})
            if interviewer.concluded:
                await do_grade()
                stop.set()
                break
            await send_json({"type": "state", "state": "listening"})

    worker = asyncio.create_task(interviewer_worker())
    voice = None
    try:
        # Session clock: a hard duration cap (bounds STT + model spend even if
        # someone parks a tab or scripts the socket) and an idle cap (voice
        # streams audio continuously, so true silence on the wire means the
        # tab is gone). Hitting either grades what exists — a real candidate
        # still gets their scorecard — then one grace window to deliver it.
        loop = asyncio.get_event_loop()
        deadline = loop.time() + MAX_SESSION_S
        closing = False
        while not stop.is_set():
            remaining = deadline - loop.time()
            if remaining <= 0:
                if closing:
                    break  # grace window elapsed too — close out
                closing = True
                deadline = loop.time() + 300  # grace: grade + deliver scorecard
                if voice is not None:
                    await voice.stop()
                await send_json(
                    {"type": "status", "text": "session limit reached — grading now"}
                )
                await commit_pending()
                await turn_queue.put({"cmd": "done"})
                continue
            try:
                msg = await asyncio.wait_for(
                    ws.receive(), timeout=min(remaining, IDLE_S)
                )
            except asyncio.TimeoutError:
                deadline = loop.time()  # idle — wind down via the limit path
                continue
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                # Drop empty frames: a zero-byte binary message is Deepgram's
                # end-of-stream signal and would close the voice connection.
                if msg["bytes"]:
                    # Lazy: the paid STT stream opens on the FIRST audio bytes.
                    # A session that never grants the mic never touches Deepgram
                    # (and never shows voice status noise).
                    if voice is None and voice_on:
                        voice = Voice(
                            os.environ["DEEPGRAM_API_KEY"],
                            handle_dg,
                            lambda text: send_json({"type": "status", "text": text}),
                        )
                        await voice.start()
                    if voice is not None:
                        await voice.send(msg["bytes"])  # never raises
            elif msg.get("text") is not None:
                data = json.loads(msg["text"])
                mtype = data.get("type")
                if mtype == "text" and data.get("text", "").strip():
                    await commit_pending()  # commit any pending spoken thoughts first
                    await turn_queue.put(
                        # Length-capped: unbounded pasted text is unbounded tokens.
                        {"source": "text", "text": data["text"].strip()[:MAX_TEXT_CHARS]}
                    )
                elif mtype == "hint":
                    await turn_queue.put({"cmd": "hint"})
                elif mtype == "done":
                    await commit_pending()
                    await turn_queue.put({"cmd": "done"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        await send_json({"type": "error", "text": str(exc)})
    finally:
        stop.set()
        if commit_task is not None:
            commit_task.cancel()
        if voice is not None:
            await voice.stop()
        await turn_queue.put({"cmd": "__stop__"})
        await asyncio.gather(worker, return_exceptions=True)
        graph.close()
