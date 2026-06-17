"""Repository ingestion: GitHub clone OR ZIP extract, with .gitignore-like filters."""
from __future__ import annotations

import logging
import re
import shutil
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

IGNORE_DIRS = {
    "node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__",
    ".next", ".nuxt", ".cache", "coverage", "target", "out", ".idea", ".vscode",
    "bin", "obj", "vendor", ".pytest_cache", ".mypy_cache",
}

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".tar",
    ".gz", ".bz2", ".7z", ".exe", ".dll", ".so", ".dylib", ".class", ".jar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".mov", ".avi", ".wav",
    ".pyc", ".pyo", ".o", ".a", ".lib", ".whl",
}

MAX_FILE_BYTES = 400_000  # skip very large source files


def _is_safe_member(member_name: str) -> bool:
    return not (member_name.startswith("/") or ".." in Path(member_name).parts)


def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if not _is_safe_member(member.filename):
                continue
            zf.extract(member, dest)
    # Detect a single top-level directory (typical GitHub zip layout) and surface it.
    entries = [p for p in dest.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return dest


_GITHUB_URL = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)(?P<owner>[\w.\-]+)/(?P<repo>[\w.\-]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> Optional[tuple]:
    m = _GITHUB_URL.match(url.strip())
    if not m:
        return None
    return m.group("owner"), m.group("repo")


def clone_github(url: str, dest: Path) -> Path:
    from git import Repo  # type: ignore
    dest.mkdir(parents=True, exist_ok=True)
    logger.info("Cloning %s into %s", url, dest)
    Repo.clone_from(url, dest, depth=1, multi_options=["--single-branch"])
    return dest


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & IGNORE_DIRS:
            continue
        if path.suffix.lower() in BINARY_EXT:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def list_files(root: Path) -> List[Path]:
    return list(iter_source_files(root))


def safe_cleanup(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
