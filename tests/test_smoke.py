"""Offline smoke tests — validate wiring without hitting the Anthropic API.

Run with:  python -m pytest -q     (or: python tests/test_smoke.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep import prompts, rubric  # noqa: E402
from pmcaseprep.case_loader import default_case_path, list_cases, load_case  # noqa: E402
from pmcaseprep.grader import weighted_result  # noqa: E402
from pmcaseprep.models import (  # noqa: E402
    Case,
    DimensionScore,
    ScoreCard,
)


def test_cases_load_and_validate():
    cases = list_cases()
    assert cases, "expected at least one case in cases/"
    for path in cases:
        case = load_case(path)
        assert case.id and case.prompt and case.type


def test_default_case_is_ai_pm():
    case = load_case(default_case_path())
    assert isinstance(case, Case)
    assert case.hidden_facts  # interviewer needs facts to answer clarifications


def test_rubric_weights_normalize():
    for archetype in ("ai-pm", "growth", "consumer", "unknown-archetype"):
        w = rubric.weights_for(archetype)
        assert abs(sum(w.values()) - 1.0) < 1e-6
        assert set(w) == set(rubric.DIMENSION_KEYS)


def test_gate_caps_band_at_no_hire():
    # A single sub-bar dimension must gate the outcome even with high others.
    assert rubric.band_for(weighted_avg=3.9, min_dimension=2) == "no_hire"
    assert rubric.band_for(weighted_avg=3.9, min_dimension=3) == "strong_hire"


def test_prompts_omit_ideal_answer_from_interviewer():
    case = load_case(default_case_path())
    system = prompts.build_interviewer_system(case)
    # The interviewer must not be handed the model answer.
    for note in case.ideal_answer_notes:
        assert note not in system
    # ...but it must have the hidden facts to answer clarifications.
    assert any(v in system for v in case.hidden_facts.values())


def test_vision_builds_image_blocks(tmp_path=None):
    import base64

    from pmcaseprep import vision

    # 1x1 transparent PNG
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    p = Path(__file__).resolve().parent / "_tmp_pixel.png"
    p.write_bytes(png)
    try:
        blocks = vision.image_content(p, "my 2x2")
        assert blocks[0]["type"] == "image"
        assert blocks[0]["source"]["media_type"] == "image/png"
        assert blocks[1] == {"type": "text", "text": "my 2x2"}
    finally:
        p.unlink()


def test_transcribe_reports_missing_key(monkeypatch=None):
    import os

    from pmcaseprep import transcribe

    saved = os.environ.pop("DEEPGRAM_API_KEY", None)
    try:
        assert transcribe.voice_configured() is False
        try:
            transcribe.transcribe("does-not-matter.wav")
            assert False, "expected TranscriptionError without a key"
        except transcribe.TranscriptionError:
            pass
    finally:
        if saved is not None:
            os.environ["DEEPGRAM_API_KEY"] = saved


def test_delivery_metrics():
    from pmcaseprep.delivery import DeliveryTracker, Word, turn_metrics

    # 4 words over 2.0s -> 120 wpm; one 1.0s pause; one hard filler ("um").
    words = [
        Word("So", 0.0, 0.3),
        Word("um", 0.4, 0.6),
        Word("retention", 1.6, 2.0),  # 1.0s gap before this word = a pause
        Word("dropped", 2.0, 2.0),
    ]
    m = turn_metrics(words)
    assert m["words"] == 4
    assert m["core_fillers"] == 1  # "um"
    assert m["soft_fillers"] == 1  # "So"
    assert m["pause_count"] == 1
    assert m["longest_pause_s"] >= 1.0

    tracker = DeliveryTracker()
    snap = tracker.add_turn(words)
    assert snap["words"] == 4
    assert snap["filler_rate_per_100"] == 50.0  # 2 fillers / 4 words * 100
    assert "wpm" in tracker.summary_text().lower() or "words" in tracker.summary_text().lower()


def test_web_app_imports():
    # Skip cleanly if web/runtime deps aren't installed in this environment.
    try:
        from pmcaseprep.web import app as webapp
    except ImportError as exc:
        print(f"  (skipped test_web_app_imports — missing dep: {exc.name})")
        return
    assert webapp.app is not None
    assert (webapp.STATIC_DIR / "index.html").exists()
    for f in ("index.html", "app.js", "worklet.js", "styles.css"):
        assert (webapp.STATIC_DIR / f).exists(), f"missing static file {f}"


def _card_with_scores(scores: dict[str, int]) -> ScoreCard:
    return ScoreCard(
        dimension_scores=[
            DimensionScore(dimension=k, score=v, justification="x")
            for k, v in scores.items()
        ],
        category_checklist=[],
        red_flags=[],
        top_improvement="x",
        overall_band="hire",
        summary="y",
    )


def test_skill_graph_projection():
    from pmcaseprep.skill_graph import SkillGraph

    g = SkillGraph(":memory:")
    proj = g.projection()
    assert proj["sessions"] == 0 and proj["to_hire"] is None

    # Three cases improving ~0.25/case: 2.0 -> 2.25 -> 2.5. Hire bar is 2.75.
    for i, s in enumerate(([2, 2, 2, 2, 2, 2], [2, 2, 2, 2, 3, 2], [3, 2, 3, 2, 3, 2])):
        card = _card_with_scores(dict(zip(rubric.DIMENSION_KEYS, s)))
        g.record(f"s{i}", "case", "ai-pm", card, "no_hire")
    proj = g.projection()
    assert proj["sessions"] == 3
    assert proj["slope_per_case"] > 0
    # Least-squares fit: level 2.47 at the latest case, +0.25/case.
    assert proj["to_hire"] == 2  # ceil((2.75 - 2.47) / 0.25)
    assert proj["to_strong_hire"] == 5  # ceil((3.5 - 2.47) / 0.25)

    # Flat scores -> no dishonest extrapolation.
    g2 = SkillGraph(":memory:")
    for i in range(3):
        card = _card_with_scores({k: 2 for k in rubric.DIMENSION_KEYS})
        g2.record(f"s{i}", "case", "ai-pm", card, "no_hire")
    proj2 = g2.projection()
    assert proj2["to_hire"] is None and "flat" in proj2["note"]
    g.close()
    g2.close()


def test_skill_graph_user_isolation_and_login():
    import os
    import tempfile

    from pmcaseprep.skill_graph import SkillGraph

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "t.db")
        a = SkillGraph(db, "uid-a")
        b = SkillGraph(db, "uid-b")
        card = _card_with_scores({k: 3 for k in rubric.DIMENSION_KEYS})
        a.record("s1", "case", "ai-pm", card, "hire")
        # One visitor's scores must never leak into another's graph.
        assert a.sessions_count() == 1
        assert b.sessions_count() == 0
        assert b.projection()["sessions"] == 0
        # Email linking: save on device A, restore from device B.
        a.link_email("p@example.com", "uid-a")
        assert b.uid_for_email("p@example.com") == "uid-a"
        assert a.email_for_uid("uid-a") == "p@example.com"
        a.close()
        b.close()


def test_full_session_record_is_stored():
    """A graded case persists everything — scorecard, transcript, delivery —
    keyed to the user, so it's all there once they attach an email."""
    from pmcaseprep.skill_graph import SkillGraph

    g = SkillGraph(":memory:", "uid-a")
    card = _card_with_scores({k: 3 for k in rubric.DIMENSION_KEYS})
    g.record(
        "s1",
        "case-x",
        "ai-pm",
        card,
        "hire",
        weighted=3.0,
        transcript="Interviewer: hi\nCandidate: my structure is...",
        delivery={"snapshot": {"wpm": 130}, "summary": "steady pace"},
    )
    hist = g.history()
    assert len(hist) == 1
    assert hist[0]["case_id"] == "case-x" and hist[0]["weighted"] == 3.0

    rec = g.session_record("s1")
    assert rec is not None
    assert rec["transcript"].startswith("Interviewer: hi")
    assert rec["delivery"]["snapshot"]["wpm"] == 130
    assert rec["card"]["dimension_scores"][0]["score"] == 3
    assert rec["band"] == "hire"

    # Another user must not be able to read it.
    other = SkillGraph(":memory:", "uid-b")
    assert other.session_record("s1") is None
    other.close()
    g.close()


def test_login_restore_merges_anonymous_cases():
    """Finish a case anonymously, then log in with a PREVIOUSLY saved email:
    the anonymous case must follow the person into their account, not orphan."""
    import os
    import tempfile

    from pmcaseprep.skill_graph import SkillGraph

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "t.db")
        card = _card_with_scores({k: 3 for k in rubric.DIMENSION_KEYS})

        # Long ago on another device: uid-old did a case and saved their email.
        old = SkillGraph(db, "uid-old")
        old.record("s1", "case", "ai-pm", card, "hire")
        old.link_email("p@example.com", "uid-old")

        # Today, anonymously on this phone: uid-anon does a case…
        anon = SkillGraph(db, "uid-anon")
        anon.record("s2", "case2", "ai-pm", card, "hire")
        # …then enters that same email. Login restores uid-old and merges.
        old.merge_from("uid-anon")

        assert old.sessions_count() == 2  # both cases are theirs now
        assert {h["session_id"] for h in old.history()} == {"s1", "s2"}
        assert anon.sessions_count() == 0  # nothing left behind
        # Merging into yourself is a no-op, never data loss.
        old.merge_from("uid-old")
        assert old.sessions_count() == 2
        old.close()
        anon.close()


def test_resources_selection():
    from pmcaseprep.resources import RESOURCES, resources_for

    case = load_case(default_case_path())
    # Every tag a case declares must exist in the curated map.
    for tag in case.resource_tags:
        assert tag in RESOURCES, f"case tags unknown resource key {tag}"
    scores = dict.fromkeys(rubric.DIMENSION_KEYS, 4)
    scores["structure"] = 2
    scores["communication"] = 3
    picked = resources_for(_card_with_scores(scores), case)
    if RESOURCES:  # once links are curated, weak dims must get them
        assert "structure" in picked["dimensions"]
        assert len(picked["dimensions"].get("communication", [])) <= 1
        assert picked["case"], "case resource_tags should yield links"
        for links in list(picked["dimensions"].values()) + [picked["case"]]:
            for r in links:
                assert r["url"].startswith("https://")
    # A perfect run shows no dimension links.
    perfect = resources_for(_card_with_scores(dict.fromkeys(rubric.DIMENSION_KEYS, 4)), case)
    assert perfect["dimensions"] == {}


def test_flux_word_timing_synthesis():
    """Flux omits per-word timestamps; we synthesize them from the turn window
    so words-per-minute stays meaningful."""
    try:
        from pmcaseprep.web.app import _flux_words
    except ImportError as exc:
        print(f"  (skipped test_flux_word_timing_synthesis — missing dep: {exc.name})")
        return
    # No per-word timing, only a 3s window over 6 words -> ~120 wpm.
    evt = {
        "audio_window_start": 10.0,
        "audio_window_end": 13.0,
        "words": [{"word": w, "confidence": 0.9} for w in "one two three four five six".split()],
    }
    words = _flux_words(evt)
    assert len(words) == 6
    assert abs((words[-1].end - words[0].start) - 3.0) < 1e-6
    from pmcaseprep.delivery import turn_metrics
    assert abs(turn_metrics(words)["wpm"] - 120.0) < 1.0
    # Real per-word timing is honored when present.
    evt2 = {"words": [{"word": "hi", "start": 0.0, "end": 0.5, "confidence": 0.9}]}
    assert _flux_words(evt2)[0].end == 0.5


def test_interviewer_memory_matches_screen():
    """After align_shown, the model's memory (and the grader's transcript) must
    contain exactly what the candidate saw — never suppressed narration."""
    from types import SimpleNamespace

    from pmcaseprep.interviewer import Interviewer

    case = load_case(default_case_path())
    responses = [
        SimpleNamespace(
            stop_reason="tool_use",
            content=[
                SimpleNamespace(type="text", text="They're structuring well — noting it."),
                SimpleNamespace(
                    type="tool_use",
                    name="log_observation",
                    id="t1",
                    input={"dimension": "structure", "note": "tree", "polarity": "positive"},
                ),
            ],
        ),
        SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="Private narration. (listening)")],
        ),
    ]

    class FakeMessages:
        @staticmethod
        def create(**kw):
            return responses.pop(0)

    class FakeClient:
        messages = FakeMessages()

    iv = Interviewer(FakeClient(), case, "test-model")
    iv.respond("thinking out loud about the funnel")
    iv.align_shown("(listening)")
    t = iv.transcript()
    assert "structuring well" not in t and "narration" not in t.lower()
    assert "(listening)" in t
    assert len(iv.observations) == 1  # tool effects survive the rewrite


def test_visible_reply_salvage():
    try:
        from pmcaseprep.web.app import _visible_reply
    except ImportError as exc:
        print(f"  (skipped test_visible_reply_salvage — missing dep: {exc.name})")
        return
    assert _visible_reply("(listening)") == ""
    assert _visible_reply("Noted. (listening)") == ""  # short remainder = narration
    answer = "The spike started three days ago and is concentrated in the email use case on v4.2."
    assert _visible_reply(answer + " (listening)") == answer  # real answer salvaged
    assert _visible_reply("Sure — what would you like to know?") == "Sure — what would you like to know?"


def test_empty_audio_never_reaches_deepgram():
    """A zero-byte binary frame is Deepgram's end-of-stream signal. A client
    bug once flooded the socket with empty frames, killing the voice channel
    in a reconnect loop — empties must be dropped, never forwarded."""
    import asyncio

    try:
        from pmcaseprep.web.deepgram_live import DeepgramLive
    except ImportError as exc:
        print(f"  (skipped test_empty_audio_never_reaches_deepgram — missing dep: {exc.name})")
        return

    class FakeWs:
        def __init__(self):
            self.sent = []

        async def send(self, data):
            self.sent.append(data)

    dg = DeepgramLive("key")
    dg.ws = FakeWs()
    asyncio.run(dg.send_audio(b""))  # end-of-stream signal — must be dropped
    asyncio.run(dg.send_audio(b"\x01\x02"))  # real audio — must pass
    assert dg.ws.sent == [b"\x01\x02"]


def test_rate_limit_and_gauge():
    """The /ws + /api/login abuse guards: sliding-window limits actually
    expire, and concurrent-session gauges pair inc/dec cleanly."""
    try:
        from pmcaseprep.web.app import Gauge, SlidingLimit
    except ImportError as exc:
        print(f"  (skipped test_rate_limit_and_gauge — missing dep: {exc.name})")
        return

    t = [0.0]
    lim = SlidingLimit(2, 60, now_fn=lambda: t[0])
    assert lim.allow("ip1") and lim.allow("ip1")
    assert not lim.allow("ip1")  # third hit inside the window is refused
    assert lim.allow("ip2")  # other keys unaffected
    t[0] = 61.0
    assert lim.allow("ip1")  # window slid — allowed again

    g = Gauge()
    assert g.get("k") == 0
    g.inc("k")
    g.inc("k")
    assert g.get("k") == 2
    g.dec("k")
    g.dec("k")
    assert g.get("k") == 0
    g.dec("k")  # over-dec must not go negative
    assert g.get("k") == 0


def test_ws_gate_helpers():
    """Origin allow-list and proxy-aware client IP extraction."""
    from types import SimpleNamespace

    try:
        from pmcaseprep.web.app import _client_ip, _same_origin
    except ImportError as exc:
        print(f"  (skipped test_ws_gate_helpers — missing dep: {exc.name})")
        return

    def conn(headers, host="1.2.3.4"):
        return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))

    site = "pm-prep.onrender.com"
    assert _same_origin(conn({"origin": f"https://{site}", "host": site}))
    assert not _same_origin(conn({"origin": "https://evil.example", "host": site}))
    assert _same_origin(conn({"host": site}))  # non-browser: no Origin header

    assert _client_ip(conn({"x-forwarded-for": "9.9.9.9, 10.0.0.1"})) == "9.9.9.9"
    assert _client_ip(conn({})) == "1.2.3.4"  # local dev: socket peer


def test_voice_supervisor_dormant_not_spamming():
    """A Deepgram drop while NO audio flows must park the channel silently —
    no 'voice reconnecting…' churn (the stuck-banner bug) and no new
    connections — then fresh audio wakes it and announces 'voice connected'.
    Also: Flux must never get KeepAlive (its protocol rejects it)."""
    import asyncio

    try:
        from pmcaseprep.web import app as webapp
    except ImportError as exc:
        print(f"  (skipped test_voice_supervisor_dormant_not_spamming — missing dep: {exc.name})")
        return

    class FakeDG:
        instances = 0
        keepalives = 0

        def __init__(self, key, url):
            FakeDG.instances += 1
            self.url = url

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def keepalive(self):
            FakeDG.keepalives += 1

        async def send_audio(self, data):
            pass

        async def events(self):
            return
            yield {}  # noqa — makes this an async generator that ends at once

    async def run():
        notes = []

        async def notify(t):
            notes.append(t)

        async def handle(evt):
            pass

        v = webapp.Voice("key", handle, notify)
        v.IDLE_AUDIO_S = 0.05
        orig = webapp.DeepgramLive
        webapp.DeepgramLive = FakeDG
        try:
            await v.start()
            v._last_audio = -1e9  # pretend no audio ever flowed -> dormant
            await asyncio.sleep(0.2)
            assert FakeDG.instances == 0  # lazy channel never dialed Deepgram
            assert notes == []  # and said nothing

            await v.send(b"\x01")  # audio arrives -> wake, connect, then drop
            await asyncio.sleep(1.4)  # covers connect + drop + one backoff
            base = FakeDG.instances
            assert base >= 1
            assert notes.count("voice connected") == 1
            spam = notes.count("voice reconnecting…")

            await asyncio.sleep(0.5)  # audio stopped -> must be dormant again
            assert FakeDG.instances == base  # no reconnect churn
            assert notes.count("voice reconnecting…") == spam  # no banner spam

            await v.send(b"\x01")  # speaking again -> reconnect + clear signal
            await asyncio.sleep(0.3)
            assert FakeDG.instances > base
            assert notes.count("voice connected") >= 2
        finally:
            await v.stop()
            webapp.DeepgramLive = orig

    asyncio.run(run())


def test_weighted_result_is_deterministic():
    case = load_case(default_case_path())
    card = ScoreCard(
        dimension_scores=[
            DimensionScore(dimension=k, score=3, justification="ok")
            for k in rubric.DIMENSION_KEYS
        ],
        category_checklist=[],
        red_flags=[],
        top_improvement="x",
        overall_band="hire",
        summary="y",
    )
    weighted, min_dim, band = weighted_result(case, card)
    assert min_dim == 3
    assert round(weighted, 2) == 3.0
    assert band == "hire"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nAll smoke tests passed.")
