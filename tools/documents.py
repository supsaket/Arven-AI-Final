"""Document intelligence — extract text from real document files.

Supported: .txt, .md, .json, .py, .log (plain text) ; .docx (python-docx) ;
.xlsx (openpyxl) ; .pdf (PyMuPDF/fitz). Handles missing files and actually
returns extracted content backed by installed libraries.
"""

from pathlib import Path

from core.paths import normalize_path
from tools.files import _resolve as _resolve_base
from core.logging import logger

_SUPPORTED_TEXT = {".txt", ".md", ".json", ".py", ".log", ".csv", ".yaml", ".yml", ".xml", ".html"}


def _extract_pdf(path):
    try:
        import fitz  # PyMuPDF
    except Exception:
        raise RuntimeError("PyMuPDF (fitz) is not installed.")
    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


def _extract_docx(path):
    try:
        import docx
    except Exception:
        raise RuntimeError("python-docx is not installed.")
    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _extract_xlsx(path):
    try:
        import openpyxl
    except Exception:
        raise RuntimeError("openpyxl is not installed.")
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    parts = []
    for sheet in wb.worksheets:
        parts.append(f"== {sheet.title} ==")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= 200:
                parts.append("... (truncated)")
                break
            parts.append(" | ".join("" if cell is None else str(cell) for cell in row))
    wb.close()
    return "\n".join(parts)


def _extract(path):
    suffix = path.suffix.lower()
    if suffix in _SUPPORTED_TEXT:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".xlsx":
        return _extract_xlsx(path)
    raise ValueError(f"Unsupported document type '{suffix or 'none'}'. Supported: "
                     f"{sorted(_SUPPORTED_TEXT)} + .pdf/.docx/.xlsx")


def read_document(path, max_chars=5000, **kwargs):
    """Read and extract text from a file."""
    try:
        target = _resolve_base(path)
    except Exception as exc:
        return {"success": False, "action": "read_document", "message": str(exc)}
    if not target.exists() or not target.is_file():
        return {"success": False, "action": "read_document",
                "message": f"Could not find {path}."}
    try:
        content = _extract(target)
        truncated = len(content) > int(max_chars)
        content = content[: int(max_chars)]
        logger.info("document.read", f"read {target.name} ({len(content)} chars)")
        data = {
            "success": True,
            "action": "read_document",
            "path": str(target),
            "filename": target.name,
            "suffix": target.suffix,
            "content": content,
            "content_length": len(content),
            "truncated": truncated,
            "message": f"Read {target.name}.",  # _extract may raise
        }
        return data
    except (ValueError, RuntimeError, OSError) as exc:
        return {"success": False, "action": "read_document", "message": str(exc)}
    except Exception as exc:
        return {"success": False, "action": "read_document", "message": f"read_document error: {exc}"}


def list_documents(path="", **kwargs):
    try:
        directory = _resolve_base(path or "")
    except Exception as exc:
        return {"success": False, "action": "list_documents", "message": str(exc)}
    if not directory.exists():
        return {"success": False, "action": "list_documents",
                "message": f"Could not find {path or 'current directory'}."}
    docs = []
    for candidate in directory.iterdir():
        if candidate.is_file() and candidate.suffix.lower() in (
                _SUPPORTED_TEXT | {".pdf", ".docx", ".xlsx"}):
            docs.append({"name": candidate.name, "suffix": candidate.suffix,
                         "size": candidate.stat().st_size})
    docs.sort(key=lambda d: d["name"].lower())
    return {"success": True, "action": "list_documents", "path": str(directory),
            "documents": docs, "count": len(docs),
            "message": f"Found {len(docs)} documents."}


TOOLS = [
    {"name": "read_document", "function": read_document, "category": "Document",
     "backend": "fitz+docx+openpyxl", "risk": "low",
     "parameters": [{"name": "path", "required": True, "hint": "str"},
                    {"name": "max_chars", "required": False, "hint": "int"}]},
    {"name": "list_documents", "function": list_documents, "category": "Document",
     "backend": "local", "risk": "safe",
     "parameters": [{"name": "path", "required": False, "hint": "str"}]},
]