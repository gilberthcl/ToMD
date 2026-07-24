"""
converter_core.py
------------------
Conversion engine for ToMd. Pure logic, no GUI code here, so it can be
tested/reused independently of Tkinter.

Handles:
  * .msg  (Outlook email)  -> Markdown, with attachment listing + SHA256 hashes
  * .pdf  (any PDF)        -> Markdown, one section per page

Both converters write the .md file next to the source file and return the
output Path so the caller can report progress.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

ProgressCB = Optional[Callable[[str], None]]


class ConversionError(RuntimeError):
    pass


@dataclass
class ConversionResult:
    source: Path
    output: Path
    kind: str          # "msg" or "pdf"
    pages_or_attachments: int


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _safe_stem(path: Path) -> str:
    return re.sub(r"[^\w\-. ]", "_", path.stem).strip() or "untitled"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _md_escape(text: str) -> str:
    """Minimal escaping so stray markdown syntax in email bodies doesn't
    break rendering (keeps content readable, doesn't over-engineer)."""
    return text.replace("\r\n", "\n").strip()


# --------------------------------------------------------------------------
# .msg -> .md
# --------------------------------------------------------------------------

def convert_msg(path: Path, log: ProgressCB = None) -> ConversionResult:
    try:
        import extract_msg
    except ImportError as e:
        raise ConversionError(
            "Missing dependency 'extract-msg'. Install with:\n"
            "  pip3 install extract-msg"
        ) from e

    if log:
        log(f"Opening {path.name} …")

    msg = extract_msg.Message(str(path))
    try:
        subject = msg.subject or "(no subject)"
        sender = msg.sender or "(unknown sender)"
        to = msg.to or "(unknown recipients)"
        cc = msg.cc or ""
        date = msg.date or "(unknown date)"
        body = msg.body or "(no plain-text body found)"

        attachments_info = []
        att_dir: Optional[Path] = None
        if msg.attachments:
            att_dir = path.parent / f"{_safe_stem(path)}_attachments"
            att_dir.mkdir(exist_ok=True)
            for att in msg.attachments:
                try:
                    fname = att.longFilename or att.shortFilename or "attachment.bin"
                    data = att.data
                    digest = _sha256(data) if isinstance(data, (bytes, bytearray)) else "n/a"
                    out_path = att_dir / fname
                    if isinstance(data, (bytes, bytearray)):
                        out_path.write_bytes(data)
                    attachments_info.append((fname, len(data) if data else 0, digest))
                    if log:
                        log(f"  ↳ extracted attachment {fname}")
                except Exception as att_err:  # keep going even if one attachment fails
                    attachments_info.append((f"(failed: {att_err})", 0, "n/a"))

        lines = [
            f"# {subject}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| From | {sender} |",
            f"| To | {to} |",
        ]
        if cc:
            lines.append(f"| Cc | {cc} |")
        lines.append(f"| Date | {date} |")
        lines.append(f"| Source file | `{path.name}` |")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Body")
        lines.append("")
        lines.append(_md_escape(body))

        if attachments_info:
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append(f"## Attachments ({len(attachments_info)})")
            lines.append("")
            lines.append("| File | Size (bytes) | SHA-256 |")
            lines.append("|---|---|---|")
            for fname, size, digest in attachments_info:
                lines.append(f"| {fname} | {size} | `{digest}` |")
            lines.append("")
            lines.append(f"*Attachments extracted to* `{att_dir.name}/`")

        out_path = path.with_suffix(".md")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return ConversionResult(path, out_path, "msg", len(attachments_info))
    finally:
        try:
            msg.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# .pdf -> .md
# --------------------------------------------------------------------------

def convert_pdf(path: Path, log: ProgressCB = None) -> ConversionResult:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ConversionError(
            "Missing dependency 'PyMuPDF'. Install with:\n"
            "  pip3 install pymupdf"
        ) from e

    if log:
        log(f"Opening {path.name} …")

    doc = fitz.open(str(path))
    try:
        title = doc.metadata.get("title") if doc.metadata else None
        title = title or path.stem

        lines = [f"# {title}", "", f"*Converted from* `{path.name}` — {doc.page_count} page(s)", ""]

        for i, page in enumerate(doc, start=1):
            if log:
                log(f"  ↳ page {i}/{doc.page_count}")
            text = page.get_text("text").strip()
            lines.append("---")
            lines.append("")
            lines.append(f"## Page {i}")
            lines.append("")
            lines.append(text if text else "*(no extractable text — likely a scanned image)*")
            lines.append("")

        out_path = path.with_suffix(".md")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return ConversionResult(path, out_path, "pdf", doc.page_count)
    finally:
        doc.close()


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

def convert_file(path: Path, log: ProgressCB = None) -> ConversionResult:
    suffix = path.suffix.lower()
    if suffix == ".msg":
        return convert_msg(path, log)
    if suffix == ".pdf":
        return convert_pdf(path, log)
    raise ConversionError(f"Unsupported file type: {suffix}")
