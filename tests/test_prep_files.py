"""CV / JD file attach: extraction and the thinking config that guards the
engine's token budget. Offline by design — no Anthropic calls, no network.

Two things are tested here that used to be untested and both broke the live
build:

1. `_thinking_for` — leaving `thinking` unset means "adaptive" on Claude 5
   models, which spends `max_tokens` on reasoning and truncates the JSON.
2. Upload extraction — the paths a real CV takes (PDF, DOCX, text) plus the
   refusals that have to name a fix rather than just fail.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep.prep_engine import PrepTruncated, _parse, _thinking_for  # noqa: E402
from pmcaseprep.prep_files import (  # noqa: E402
    MAX_UPLOAD_BYTES,
    UnsupportedFile,
    extract_text,
)

CV_TEXT = (
    "Acme Corp, Product Manager, 2021-2024.\n"
    "Led the checkout revamp with a team of 6 engineers; cut drop-off by 18%.\n"
    "Killed the loyalty-points launch after 2 sprints when retention went flat.\n"
)


# --- The thinking config ------------------------------------------------------


@pytest.mark.parametrize(
    "model", ["claude-sonnet-5", "claude-opus-5", "claude-opus-4-8", "claude-sonnet-4-6"]
)
def test_thinking_is_never_left_to_default(model):
    """The bug that took /prep-ds down: omitting `thinking` means ADAPTIVE on
    Claude 5 models, and `max_tokens` covers thinking + JSON together, so a
    long CV truncates mid-object. Every structured call must say what it wants.
    """
    assert _thinking_for(model) == {"type": "disabled"}


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-5"])
def test_adaptive_is_opt_in_and_explicit(model):
    assert _thinking_for(model, adaptive=True) == {"type": "adaptive"}


@pytest.mark.parametrize("model", ["claude-fable-5", "claude-mythos-5"])
def test_fable_and_mythos_omit_thinking_entirely(model):
    """Thinking is always on for these and an explicit {"type": "disabled"}
    is a 400 — so the field has to be left off, not set to disabled."""
    assert _thinking_for(model) is None
    assert _thinking_for(model, adaptive=True) is None


class _Resp:
    def __init__(self, stop_reason, parsed_output="ok"):
        self.stop_reason = stop_reason
        self.parsed_output = parsed_output


class _Messages:
    def __init__(self, stop_reason):
        self._stop_reason = stop_reason
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return _Resp(self._stop_reason)


class _Client:
    def __init__(self, stop_reason="end_turn"):
        self.messages = _Messages(stop_reason)


class _Schema:
    pass


def test_parse_sends_thinking_and_returns_parsed_output():
    client = _Client()
    out = _parse(
        client,
        model="claude-sonnet-5",
        prompt="p",
        output_format=_Schema,
        max_tokens=16000,
    )
    assert out == "ok"
    assert client.messages.kwargs["thinking"] == {"type": "disabled"}
    assert client.messages.kwargs["max_tokens"] == 16000


def test_parse_omits_thinking_for_fable():
    client = _Client()
    _parse(client, model="claude-fable-5", prompt="p", output_format=_Schema, max_tokens=8000)
    assert "thinking" not in client.messages.kwargs


def test_parse_refuses_a_truncated_answer():
    """A half-read CV must not be returned as if it were the whole thing."""
    client = _Client(stop_reason="max_tokens")
    with pytest.raises(PrepTruncated):
        _parse(
            client, model="claude-sonnet-5", prompt="p", output_format=_Schema, max_tokens=100
        )


# --- Plain text ---------------------------------------------------------------


def test_plain_text_roundtrips():
    out = extract_text("cv.txt", CV_TEXT.encode("utf-8"))
    assert "checkout revamp" in out
    assert "18%" in out


def test_markdown_keeps_one_bullet_per_line():
    md = b"# CV\n\n- Shipped A\n- Shipped B\n- Shipped C\n\nMore detail here to clear the floor.\n"
    out = extract_text("cv.md", md)
    assert out.count("\n- ") == 3  # the extractor prompt reads one bullet per line
    assert "Shipped C" in out


def test_whitespace_is_tidied_but_paragraphs_survive():
    messy = b"Line one\r\n\r\n\r\n\r\nLine two    with     runs\r\nand a third line here ok\n"
    out = extract_text("cv.txt", messy)
    assert "\n\n\n" not in out
    assert "runs" in out and "Line two with runs" in out
    assert "\n\n" in out  # the paragraph break is still a paragraph break


# --- DOCX ---------------------------------------------------------------------


def _docx_bytes(paragraphs, table_rows=None):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    if table_rows:
        table = document.add_table(rows=0, cols=len(table_rows[0]))
        for row in table_rows:
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = value
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def test_docx_paragraphs():
    data = _docx_bytes(CV_TEXT.strip().split("\n"))
    out = extract_text("cv.docx", data)
    assert "checkout revamp" in out
    assert "loyalty-points" in out


def test_docx_reads_table_layout_cvs():
    """Plenty of CVs are an invisible two-column table. Skipping tables would
    return the name and nothing else."""
    data = _docx_bytes(
        ["Jane Roe — Product Manager"],
        [["2021-2024", "Led checkout revamp; cut drop-off 18% with a team of six"]],
    )
    out = extract_text("cv.docx", data)
    assert "Jane Roe" in out
    assert "drop-off 18%" in out


def test_corrupt_docx_names_the_fix():
    bogus = io.BytesIO()
    with zipfile.ZipFile(bogus, "w") as z:
        z.writestr("not-a-document.txt", "nope")
    with pytest.raises(UnsupportedFile) as e:
        extract_text("cv.docx", bogus.getvalue())
    assert "paste" in str(e.value).lower() or "re-save" in str(e.value).lower()


# --- PDF ----------------------------------------------------------------------


def _pdf_bytes(lines):
    """A minimal one-page PDF with a real text layer, built by hand so the
    test needs no PDF-writing dependency."""
    pytest.importorskip("pypdf")
    stream_lines = "\n".join(f"({ln}) Tj 0 -16 Td" for ln in lines)
    content = f"BT /F1 12 Tf 40 750 Td\n{stream_lines}\nET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref,
    )
    return bytes(out)


def test_pdf_with_a_text_layer():
    data = _pdf_bytes(
        [
            "Acme Corp, Product Manager, 2021-2024",
            "Led the checkout revamp; cut drop-off by 18 percent",
            "Killed the loyalty launch after two sprints",
        ]
    )
    out = extract_text("cv.pdf", data)
    assert "checkout revamp" in out
    assert "Acme Corp" in out


def test_scanned_pdf_says_it_is_a_scan():
    """A photographed CV has no text layer. Say that, rather than handing the
    engine an empty string and failing three screens later."""
    data = _pdf_bytes([])
    with pytest.raises(UnsupportedFile) as e:
        extract_text("scan.pdf", data)
    assert "scan" in str(e.value).lower()


def test_unreadable_pdf_names_the_fix():
    with pytest.raises(UnsupportedFile) as e:
        extract_text("cv.pdf", b"%PDF-1.4\nthis is not really a pdf at all")
    assert "paste" in str(e.value).lower()


# --- Refusals -----------------------------------------------------------------


def test_empty_file():
    with pytest.raises(UnsupportedFile, match="empty"):
        extract_text("cv.pdf", b"")


def test_oversized_file():
    with pytest.raises(UnsupportedFile, match="5MB"):
        extract_text("cv.pdf", b"x" * (MAX_UPLOAD_BYTES + 1))


def test_legacy_doc_points_at_docx():
    with pytest.raises(UnsupportedFile, match="docx"):
        extract_text("cv.doc", b"\xd0\xcf\x11\xe0" + b"x" * 500)


def test_pages_export_hint():
    with pytest.raises(UnsupportedFile, match="PDF or DOCX"):
        extract_text("cv.pages", b"x" * 500)


def test_unknown_extension_lists_what_works():
    with pytest.raises(UnsupportedFile, match="PDF"):
        extract_text("cv.xyz", b"x" * 500)


def test_no_extension_is_refused_not_guessed():
    with pytest.raises(UnsupportedFile):
        extract_text("cv", CV_TEXT.encode())


def test_a_short_text_file_is_not_mistaken_for_a_scan():
    with pytest.raises(UnsupportedFile, match="couldn't find any text"):
        extract_text("cv.txt", b"hi")


# --- The endpoint -------------------------------------------------------------


def _client(tmp_path, monkeypatch):
    try:
        from fastapi.testclient import TestClient

        from pmcaseprep.web import app as webapp
    except ImportError:
        return None, None
    monkeypatch.setattr(webapp, "DB_PATH", str(tmp_path / "web.db"))
    monkeypatch.setattr(webapp, "PREP_DB", str(tmp_path / "prep.db"))
    monkeypatch.setenv("PMCP_DEV_DOCS", "1")  # dev email door for tests
    # The rate limiters are module-level singletons, so their counters are
    # shared by every test in the suite — three code requests per email and
    # twenty auth attempts per IP are enough to starve later tests of a dev
    # code depending on run order. Give this test its own fresh limiters.
    limit = type(webapp.CODE_REQUESTS_PER_EMAIL)
    for name in (
        "CODE_REQUESTS_PER_EMAIL",
        "VERIFIES_PER_EMAIL",
        "AUTH_ATTEMPTS",
        "LOGIN_ATTEMPTS",
        "PREP_BANK_CALLS",
    ):
        monkeypatch.setattr(webapp, name, limit(10_000, 3600))
    return TestClient(webapp.app), webapp


def _login(client, email):
    client.get("/prep")  # uid cookie
    d = client.post("/api/auth/email/request", json={"email": email}).json()
    assert "dev_code" in d, f"dev login door did not open: {d}"
    client.post("/api/auth/email/verify", json={"email": email, "code": d["dev_code"]})


def test_upload_requires_login(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    client.get("/prep")
    r = client.post(
        "/api/prep/upload", files={"file": ("cv.txt", CV_TEXT.encode(), "text/plain")}
    )
    assert r.status_code == 401


def test_upload_returns_text_for_the_paste_box(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    _login(client, "parth@example.com")
    r = client.post(
        "/api/prep/upload", files={"file": ("cv.txt", CV_TEXT.encode(), "text/plain")}
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "checkout revamp" in d["text"]
    assert d["chars"] == len(d["text"])
    assert d["truncated"] is False


def test_upload_clips_to_the_paste_box_cap_and_says_so(tmp_path, monkeypatch):
    client, webapp = _client(tmp_path, monkeypatch)
    if client is None:
        return
    _login(client, "parth@example.com")
    long_cv = ("Shipped a thing that mattered at Acme Corp. " * 4000).encode()
    r = client.post(
        "/api/prep/upload", files={"file": ("cv.txt", long_cv, "text/plain")}
    )
    d = r.json()
    assert d["ok"] is True
    assert d["chars"] == webapp.PREP_MAX_CHARS
    assert d["truncated"] is True  # never silently drop the tail


def test_upload_rejects_unreadable_file_with_a_fix(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    _login(client, "parth@example.com")
    r = client.post(
        "/api/prep/upload",
        files={"file": ("portfolio.key", b"x" * 500, "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "PDF" in r.json()["error"]


def test_upload_costs_no_model_call(tmp_path, monkeypatch):
    """Attaching a file must not spend a build. If this ever starts routing
    through the engine, the anthropic client would be constructed here."""
    client, webapp = _client(tmp_path, monkeypatch)
    if client is None:
        return
    _login(client, "parth@example.com")

    def _boom(*a, **k):
        raise AssertionError("upload must not make a model call")

    monkeypatch.setattr(webapp.anthropic, "Anthropic", _boom)
    r = client.post(
        "/api/prep/upload", files={"file": ("jd.txt", CV_TEXT.encode(), "text/plain")}
    )
    assert r.json()["ok"] is True
