"""
Document loaders: turn a file on disk into a list of (page_number, text)
pairs, regardless of format. Adding a new format later just means adding
a new function here and one line in `load_document`.
"""
from pypdf import PdfReader
import docx


def load_pdf(file_path: str) -> list[tuple[int, str]]:
    reader = PdfReader(file_path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((i, text))
    return pages


def load_txt(file_path: str) -> list[tuple[int, str]]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    # Plain text files have no real "pages" — we treat the whole file as page 1.
    return [(1, text)] if text.strip() else []


def load_docx(file_path: str) -> list[tuple[int, str]]:
    document = docx.Document(file_path)
    text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    # python-docx doesn't expose page numbers (Word paginates at render time,
    # not in the file format), so DOCX chunks are stored with page_number=None.
    return [(None, text)] if text.strip() else []


def load_document(file_path: str, file_type: str) -> list[tuple[int, str]]:
    loaders = {"pdf": load_pdf, "txt": load_txt, "docx": load_docx}
    if file_type not in loaders:
        raise ValueError(f"Unsupported file type: {file_type}")
    return loaders[file_type](file_path)
