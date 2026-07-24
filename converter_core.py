"""
converter_core.py
------------------
Conversion engine for ToMd. Pure logic, no GUI code here, so it can be
tested/reused independently of any front-end.

Supported inputs (all -> Markdown, written next to the source file):

  * .msg                     Outlook email  -> body + attachment SHA-256 table
  * .pdf                     PDF            -> one section per page
  * .docx                    Word document  -> headings, lists, tables, bold/italic
  * .rtf                     Rich text      -> plain text
  * .html/.htm               Web page       -> Markdown (via markdownify)
  * .txt/.text/.log          Plain text     -> passed through
  * .odt/.doc/.epub/...       via pandoc, if the `pandoc` binary is installed

Each converter returns a ConversionResult so callers can report progress.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
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
    kind: str                     # "msg", "pdf", "docx", ...
    pages_or_attachments: int = 0  # kept for backwards compatibility
    detail: str = ""              # human-readable summary, e.g. "12 page(s)"


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


def _write_output(path: Path, text: str) -> Path:
    """Write `text` to a sibling .md file, refusing to clobber the source."""
    out_path = path.with_suffix(".md")
    if out_path.resolve() == path.resolve():
        raise ConversionError(
            "Refusing to overwrite the source file (it is already .md)."
        )
    if not text.endswith("\n"):
        text += "\n"
    out_path.write_text(text, encoding="utf-8")
    return out_path


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

        out_path = _write_output(path, "\n".join(lines))
        n = len(attachments_info)
        return ConversionResult(path, out_path, "msg", n, f"{n} attachment(s)")
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

        out_path = _write_output(path, "\n".join(lines))
        return ConversionResult(path, out_path, "pdf", doc.page_count, f"{doc.page_count} page(s)")
    finally:
        doc.close()


# --------------------------------------------------------------------------
# .docx -> .md
# --------------------------------------------------------------------------

def _docx_runs_to_md(paragraph) -> str:
    """Render a paragraph's runs, applying bold/italic as Markdown."""
    parts = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        if run.bold and run.italic:
            text = f"***{text}***"
        elif run.bold:
            text = f"**{text}**"
        elif run.italic:
            text = f"*{text}*"
        parts.append(text)
    return "".join(parts) if parts else paragraph.text


def _docx_table_to_md(table) -> list[str]:
    rows = table.rows
    if not rows:
        return []

    def cell_text(cell) -> str:
        return cell.text.strip().replace("\n", " ").replace("|", "\\|")

    header = [cell_text(c) for c in rows[0].cells]
    out = ["| " + " | ".join(header) + " |",
           "| " + " | ".join("---" for _ in header) + " |"]
    for row in rows[1:]:
        out.append("| " + " | ".join(cell_text(c) for c in row.cells) + " |")
    return out


def convert_docx(path: Path, log: ProgressCB = None) -> ConversionResult:
    try:
        import docx
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as e:
        raise ConversionError(
            "Missing dependency 'python-docx'. Install with:\n"
            "  pip3 install python-docx"
        ) from e

    if log:
        log(f"Opening {path.name} …")

    document = docx.Document(str(path))

    def iter_blocks(parent):
        """Yield Paragraph and Table objects in true document order."""
        for child in parent.element.body.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                yield Table(child, parent)

    lines = [f"# {path.stem}", ""]
    blocks = 0
    for block in iter_blocks(document):
        if isinstance(block, Paragraph):
            blocks += 1
            style = (block.style.name if block.style else "") or ""
            style = style.lower()
            text = _docx_runs_to_md(block).strip()
            if not text:
                lines.append("")
                continue
            if style.startswith("heading"):
                m = re.search(r"(\d+)", style)
                level = min(int(m.group(1)), 6) if m else 2
                lines.append("#" * level + " " + text)
            elif style.startswith("title"):
                lines.append("# " + text)
            elif "list" in style:
                lines.append("- " + text)
            else:
                lines.append(text)
            lines.append("")
        else:  # Table
            lines.extend(_docx_table_to_md(block))
            lines.append("")

    out_path = _write_output(path, "\n".join(lines).rstrip() + "\n")
    return ConversionResult(path, out_path, "docx", blocks, f"{blocks} block(s)")


# --------------------------------------------------------------------------
# .rtf -> .md
# --------------------------------------------------------------------------

def convert_rtf(path: Path, log: ProgressCB = None) -> ConversionResult:
    try:
        from striprtf.striprtf import rtf_to_text
    except ImportError as e:
        raise ConversionError(
            "Missing dependency 'striprtf'. Install with:\n"
            "  pip3 install striprtf"
        ) from e

    if log:
        log(f"Opening {path.name} …")

    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = rtf_to_text(raw).strip()
    out_path = _write_output(path, f"# {path.stem}\n\n{text}\n")
    words = len(text.split())
    return ConversionResult(path, out_path, "rtf", words, f"{words} word(s)")


# --------------------------------------------------------------------------
# .html/.htm -> .md
# --------------------------------------------------------------------------

def convert_html(path: Path, log: ProgressCB = None) -> ConversionResult:
    if log:
        log(f"Opening {path.name} …")

    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        from markdownify import markdownify as _md
        text = _md(raw, heading_style="ATX")
    except ImportError:
        try:
            from bs4 import BeautifulSoup
            text = BeautifulSoup(raw, "html.parser").get_text("\n")
        except ImportError as e:
            raise ConversionError(
                "Missing dependency for HTML. Install with:\n"
                "  pip3 install markdownify"
            ) from e

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    out_path = _write_output(path, text + "\n")
    return ConversionResult(path, out_path, "html", 0, "converted")


# --------------------------------------------------------------------------
# .txt/.log -> .md  (pass-through)
# --------------------------------------------------------------------------

def convert_txt(path: Path, log: ProgressCB = None) -> ConversionResult:
    if log:
        log(f"Reading {path.name} …")

    text = path.read_text(encoding="utf-8", errors="ignore")
    out_path = _write_output(path, text)
    n_lines = text.count("\n") + 1
    return ConversionResult(path, out_path, "text", n_lines, f"{n_lines} line(s)")


# --------------------------------------------------------------------------
# Anything else -> .md  (via pandoc, if available)
# --------------------------------------------------------------------------

def convert_with_pandoc(path: Path, log: ProgressCB = None) -> ConversionResult:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise ConversionError(
            f"Converting '{path.suffix}' needs pandoc, which isn't installed.\n"
            "  brew install pandoc"
        )

    out_path = path.with_suffix(".md")
    if out_path.resolve() == path.resolve():
        raise ConversionError("Refusing to overwrite the source file.")

    if log:
        log(f"Running pandoc on {path.name} …")

    proc = subprocess.run(
        [pandoc, str(path), "-t", "gfm", "-o", str(out_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ConversionError(
            f"pandoc failed: {proc.stderr.strip() or 'unknown error'}"
        )
    return ConversionResult(path, out_path, "pandoc", 0, "via pandoc")


# --------------------------------------------------------------------------
# Dispatcher + registry
# --------------------------------------------------------------------------

_CONVERTERS: dict[str, Callable[..., ConversionResult]] = {
    ".msg": convert_msg,
    ".pdf": convert_pdf,
    ".docx": convert_docx,
    ".rtf": convert_rtf,
    ".html": convert_html,
    ".htm": convert_html,
    ".txt": convert_txt,
    ".text": convert_txt,
    ".log": convert_txt,
}

# Handled by pandoc when it's installed (best-effort; no bundled library).
PANDOC_EXTENSIONS = {
    ".odt", ".doc", ".epub", ".rst", ".tex", ".org",
    ".fb2", ".docbook", ".textile", ".mediawiki", ".rtfd",
}

# Grouping used by the front-ends to build menus / file-dialog filters.
# Each entry is (label, [bare extensions]).
FILE_GROUPS = [
    ("Documents", ["docx", "rtf", "odt", "html", "htm", "txt"]),
    ("PDFs", ["pdf"]),
    ("Emails", ["msg"]),
]


def all_supported_extensions(include_pandoc: bool = True) -> list[str]:
    """Bare extensions (no dot) for every input type we can handle."""
    exts = {e.lstrip(".") for e in _CONVERTERS}
    if include_pandoc:
        exts |= {e.lstrip(".") for e in PANDOC_EXTENSIONS}
    return sorted(exts)


def convert_file(path: Path, log: ProgressCB = None) -> ConversionResult:
    suffix = path.suffix.lower()
    handler = _CONVERTERS.get(suffix)
    if handler is not None:
        return handler(path, log)
    if suffix in PANDOC_EXTENSIONS:
        return convert_with_pandoc(path, log)
    raise ConversionError(f"Unsupported file type: {suffix}")
