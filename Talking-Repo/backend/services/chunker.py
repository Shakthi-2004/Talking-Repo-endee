"""AST-aware code chunker.

For Python we use the `ast` module to split by classes/functions/methods.
For other languages we use language-aware regex heuristics that capture
class / function / method declarations. We never use fixed-size chunking.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Map suffix -> language label
LANGUAGE_BY_EXT: Dict[str, str] = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java", ".kt": "kotlin", ".go": "go", ".rb": "ruby",
    ".rs": "rust", ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".h": "c",
    ".hpp": "cpp", ".cs": "csharp", ".php": "php", ".swift": "swift",
    ".scala": "scala", ".m": "objc", ".mm": "objc", ".sh": "shell",
    ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".md": "markdown",
    ".sql": "sql", ".html": "html", ".css": "css", ".vue": "vue",
}

CODE_EXTENSIONS = set(LANGUAGE_BY_EXT.keys())
MAX_CHUNK_CHARS = 6000  # safety cap for huge functions


@dataclass
class CodeChunk:
    id: str
    content: str
    file_name: str
    language: str
    chunk_type: str  # class | function | method | module | block
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    extra: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "content": self.content,
            "file_name": self.file_name,
            "language": self.language,
            "chunk_type": self.chunk_type,
            "function_name": self.function_name,
            "class_name": self.class_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            **self.extra,
        }


def detect_language(path: Path) -> str:
    return LANGUAGE_BY_EXT.get(path.suffix.lower(), "text")


def _make_id(repo_id: str, rel_path: str, start: int, end: int, kind: str) -> str:
    safe = rel_path.replace("/", "__").replace(".", "_")
    return f"{repo_id}::{safe}::{kind}::{start}-{end}"


def _slice(lines: List[str], start: int, end: int) -> str:
    return "\n".join(lines[start:end])[:MAX_CHUNK_CHARS]


def _chunk_python(repo_id: str, rel_path: str, source: str) -> List[CodeChunk]:
    chunks: List[CodeChunk] = []
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _chunk_generic(repo_id, rel_path, source, "python")

    module_imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    if module_imports:
        last = module_imports[-1]
        end_line = getattr(last, "end_lineno", last.lineno) or last.lineno
        content = _slice(lines, 0, end_line)
        chunks.append(CodeChunk(
            id=_make_id(repo_id, rel_path, 1, end_line, "module"),
            content=content, file_name=rel_path, language="python",
            chunk_type="module", start_line=1, end_line=end_line,
        ))

    def walk(node, class_name: Optional[str] = None):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = child.lineno - 1
                end = getattr(child, "end_lineno", child.lineno) or child.lineno
                content = _slice(lines, start, end)
                chunks.append(CodeChunk(
                    id=_make_id(repo_id, rel_path, start + 1, end, "fn"),
                    content=content, file_name=rel_path, language="python",
                    chunk_type="method" if class_name else "function",
                    function_name=child.name, class_name=class_name,
                    start_line=start + 1, end_line=end,
                ))
            elif isinstance(child, ast.ClassDef):
                start = child.lineno - 1
                end = getattr(child, "end_lineno", child.lineno) or child.lineno
                content = _slice(lines, start, min(start + 30, end))
                chunks.append(CodeChunk(
                    id=_make_id(repo_id, rel_path, start + 1, end, "cls"),
                    content=content, file_name=rel_path, language="python",
                    chunk_type="class", class_name=child.name,
                    start_line=start + 1, end_line=end,
                ))
                walk(child, class_name=child.name)

    walk(tree)
    if not chunks:
        return _chunk_generic(repo_id, rel_path, source, "python")
    return chunks


_FN_REGEX = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+(?P<f1>[A-Za-z_$][\w$]*)|"
    r"(?:const|let|var)\s+(?P<f2>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>|"
    r"(?P<f3>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{)",
    re.MULTILINE,
)

_CLASS_REGEX = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)", re.MULTILINE)


def _chunk_generic(repo_id: str, rel_path: str, source: str, language: str) -> List[CodeChunk]:
    """Heuristic chunker for JS/TS/Java/Go/etc.

    Splits at top-level class/function declarations. If none found, splits
    by markdown headings / sections of similar logical size (not fixed).
    """
    lines = source.splitlines()
    markers: List[tuple] = []
    for m in _CLASS_REGEX.finditer(source):
        line_no = source[:m.start()].count("\n") + 1
        markers.append((line_no, "class", m.group("name")))
    for m in _FN_REGEX.finditer(source):
        name = m.group("f1") or m.group("f2") or m.group("f3")
        if name:
            line_no = source[:m.start()].count("\n") + 1
            markers.append((line_no, "function", name))
    markers.sort()

    chunks: List[CodeChunk] = []
    if markers:
        boundaries = [m[0] for m in markers] + [len(lines) + 1]
        for i, (line_no, kind, name) in enumerate(markers):
            start = line_no - 1
            end = boundaries[i + 1] - 1
            content = _slice(lines, start, end)
            if not content.strip():
                continue
            chunks.append(CodeChunk(
                id=_make_id(repo_id, rel_path, start + 1, end, kind),
                content=content, file_name=rel_path, language=language,
                chunk_type=kind, function_name=name if kind == "function" else None,
                class_name=name if kind == "class" else None,
                start_line=start + 1, end_line=end,
            ))
        if chunks:
            return chunks

    # Module-level single chunk if file small, else logical chunks by blank-line groups
    if len(source) <= MAX_CHUNK_CHARS:
        return [CodeChunk(
            id=_make_id(repo_id, rel_path, 1, len(lines) or 1, "module"),
            content=source[:MAX_CHUNK_CHARS], file_name=rel_path, language=language,
            chunk_type="module", start_line=1, end_line=len(lines) or 1,
        )]

    # Split by blank-line separated blocks
    blocks: List[List[str]] = [[]]
    for ln in lines:
        if not ln.strip() and blocks[-1]:
            blocks.append([])
        else:
            blocks[-1].append(ln)
    out: List[CodeChunk] = []
    line_cursor = 1
    for block in blocks:
        if not block:
            continue
        content = "\n".join(block)
        start = line_cursor
        end = start + len(block) - 1
        out.append(CodeChunk(
            id=_make_id(repo_id, rel_path, start, end, "block"),
            content=content[:MAX_CHUNK_CHARS], file_name=rel_path,
            language=language, chunk_type="block",
            start_line=start, end_line=end,
        ))
        line_cursor = end + 2
    return out


def chunk_file(repo_id: str, root: Path, file_path: Path) -> List[CodeChunk]:
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    if not source.strip():
        return []
    rel = str(file_path.relative_to(root))
    language = detect_language(file_path)
    if language == "python":
        return _chunk_python(repo_id, rel, source)
    return _chunk_generic(repo_id, rel, source, language)
