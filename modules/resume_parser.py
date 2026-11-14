"""Resume file validation and text extraction (PDF via pypdf, DOCX via python-docx)."""
import zipfile
from pathlib import Path

try:  # pypdf is the maintained successor of PyPDF2; accept either.
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    from PyPDF2 import PdfReader  # type: ignore

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from .nlp_processor import clean_text


class UploadValidationError(ValueError):
    """The uploaded file is not acceptable (type, size, signature)."""


class ResumeParseError(ValueError):
    """The file is acceptable but its text could not be extracted."""


def get_extension(filename):
    return Path(filename or "").suffix.lower().lstrip(".")


def validate_upload(filename, data, allowed_extensions=("pdf", "docx"), max_size=5 * 1024 * 1024):
    """Check extension, size and file signature. Returns the normalised extension."""
    ext = get_extension(filename)
    if not filename:
        raise UploadValidationError("No file selected.")
    if ext not in allowed_extensions:
        allowed = ", ".join(e.upper() for e in sorted(allowed_extensions))
        raise UploadValidationError(f"Unsupported file type '.{ext or '?'}'. Allowed: {allowed}.")
    if not data:
        raise UploadValidationError("The file is empty (0 bytes).")
    if len(data) > max_size:
        raise UploadValidationError(f"File is too large ({len(data) / 1024 / 1024:.1f} MB). Limit is {max_size // 1024 // 1024} MB.")
    if ext == "pdf" and b"%PDF-" not in data[:1024]:
        raise UploadValidationError("The file does not look like a real PDF (bad signature).")
    if ext == "docx" and not data.startswith(b"PK\x03\x04"):
        raise UploadValidationError("The file does not look like a real DOCX (bad signature).")
    return ext


def extract_text_from_pdf(path):
    """Return (text, page_count). Raises ResumeParseError for corrupt/encrypted files."""
    try:
        reader = PdfReader(str(path), strict=False)
        if getattr(reader, "is_encrypted", False):
            try:
                if not reader.decrypt(""):
                    raise ResumeParseError("The PDF is password-protected.")
            except ResumeParseError:
                raise
            except Exception as exc:
                raise ResumeParseError("The PDF is encrypted and cannot be read.") from exc
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # one bad page should not kill the whole resume
                pages.append("")
        return "\n".join(pages), len(reader.pages)
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError("The PDF is corrupted or unreadable.") from exc


def _iter_docx_blocks(document):
    """Yield paragraphs and table rows in document order."""
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield Paragraph(child, document).text
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                seen, cells = set(), []
                for cell in row.cells:
                    if id(cell._tc) in seen:  # merged cells repeat
                        continue
                    seen.add(id(cell._tc))
                    cells.append(cell.text.strip())
                yield " | ".join(c for c in cells if c)


def extract_text_from_docx(path):
    try:
        document = docx.Document(str(path))
        return "\n".join(_iter_docx_blocks(document))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ResumeParseError("The DOCX file is corrupted or not a valid Word document.") from exc
    except Exception as exc:
        raise ResumeParseError("The DOCX file could not be read.") from exc


def extract_text(path, ext=None, min_chars=50):
    """Extract and clean text. Raises ResumeParseError if nothing usable is found."""
    ext = (ext or get_extension(str(path))).lower()
    if ext == "pdf":
        raw, _pages = extract_text_from_pdf(path)
    elif ext == "docx":
        raw = extract_text_from_docx(path)
    else:
        raise ResumeParseError(f"Unsupported file type '.{ext}'.")
    text = clean_text(raw)
    if len(text) < min_chars:
        raise ResumeParseError(
            "No readable text found. The document is empty or a scanned image "
            "(OCR is not supported - upload a text-based PDF or DOCX)."
        )
    return text
