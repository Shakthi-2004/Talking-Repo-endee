"""Architecture + Health analyses computed from a repository tree."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .chunker import LANGUAGE_BY_EXT
from .repo_ingest import iter_source_files

DEP_FILE_NAMES = {
    "package.json": "Node.js",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "Pipfile": "Python",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "pom.xml": "Java/Maven",
    "build.gradle": "Java/Gradle",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "next.config.js": "Next.js",
    "vite.config.ts": "Vite",
    "vite.config.js": "Vite",
    "tailwind.config.js": "Tailwind CSS",
}

API_PATTERNS = [
    re.compile(r"@(?:app|api_router|router)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)"),
    re.compile(r"app\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)"),
    re.compile(r"router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)"),
    re.compile(r"@(?:Get|Post|Put|Patch|Delete)Mapping\(\s*[\"']([^\"']+)"),
]


def detect_tech_stack(root: Path) -> Dict[str, List[str]]:
    detected: Set[str] = set()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        if name in DEP_FILE_NAMES:
            detected.add(DEP_FILE_NAMES[name])
    return {"stack": sorted(detected)}


def folder_structure(root: Path, max_depth: int = 3) -> List[Dict]:
    def walk(path: Path, depth: int):
        if depth > max_depth:
            return None
        children = []
        try:
            for entry in sorted(path.iterdir()):
                if entry.name.startswith(".") or entry.name in {"node_modules", "venv", ".venv", "__pycache__"}:
                    continue
                if entry.is_dir():
                    sub = walk(entry, depth + 1)
                    if sub is not None:
                        children.append(sub)
                else:
                    children.append({"name": entry.name, "type": "file",
                                     "size": entry.stat().st_size})
        except PermissionError:
            pass
        return {"name": path.name, "type": "dir", "children": children}

    return walk(root, 0) or {"name": root.name, "type": "dir", "children": []}


def detect_api_routes(root: Path) -> List[Dict[str, str]]:
    routes: List[Dict[str, str]] = []
    for f in iter_source_files(root):
        if f.suffix.lower() not in {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt"}:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(f.relative_to(root))
        for pat in API_PATTERNS:
            for m in pat.finditer(text):
                groups = m.groups()
                if len(groups) == 2:
                    method, path = groups[0].upper(), groups[1]
                elif len(groups) == 1:
                    method, path = "GET", groups[0]
                else:
                    continue
                routes.append({"method": method, "path": path, "file": rel})
    # Dedupe
    seen = set()
    unique: List[Dict[str, str]] = []
    for r in routes:
        key = (r["method"], r["path"], r["file"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


def language_breakdown(root: Path) -> List[Dict[str, int]]:
    counter: Counter = Counter()
    sizes: Counter = Counter()
    for f in iter_source_files(root):
        lang = LANGUAGE_BY_EXT.get(f.suffix.lower(), "other")
        counter[lang] += 1
        try:
            sizes[lang] += f.stat().st_size
        except OSError:
            pass
    items = [{"language": lang, "files": counter[lang], "bytes": sizes[lang]}
             for lang in sorted(counter, key=counter.get, reverse=True)]
    return items


# ---------------- Health metrics ----------------

_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"""(?:import\s+[^'"]*from\s+|require\(\s*)['"]([^'"]+)['"]""")


def _collect_imports(root: Path) -> Dict[str, Set[str]]:
    deps: Dict[str, Set[str]] = defaultdict(set)
    file_keys: Dict[Path, str] = {}
    for f in iter_source_files(root):
        rel = str(f.relative_to(root))
        file_keys[f] = rel
    for f, rel in file_keys.items():
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if f.suffix == ".py":
            for m in _PY_IMPORT_RE.finditer(text):
                mod = m.group(1) or m.group(2) or ""
                deps[rel].add(mod.split(".")[0])
        elif f.suffix in {".js", ".jsx", ".ts", ".tsx"}:
            for m in _JS_IMPORT_RE.finditer(text):
                imp = m.group(1)
                deps[rel].add(imp)
    return deps


def health_report(root: Path) -> Dict:
    files = list(iter_source_files(root))
    file_sizes = []
    for f in files:
        try:
            file_sizes.append((str(f.relative_to(root)), f.stat().st_size))
        except OSError:
            pass
    file_sizes.sort(key=lambda x: x[1], reverse=True)
    largest = [{"file": p, "bytes": s} for p, s in file_sizes[:10]]

    imports = _collect_imports(root)
    # Most connected modules (highest fan-out)
    fan_out = sorted(imports.items(), key=lambda kv: len(kv[1]), reverse=True)
    most_connected = [{"file": k, "imports": len(v)} for k, v in fan_out[:10]]

    # Possibly dead code = source files that are never referenced by any other file's imports (heuristic)
    all_modules = {Path(rel).stem for rel in imports.keys()}
    referenced: Set[str] = set()
    for deps in imports.values():
        for d in deps:
            referenced.add(Path(d).stem)
    dead = sorted([rel for rel in imports.keys()
                   if Path(rel).stem not in referenced
                   and Path(rel).stem in all_modules
                   and Path(rel).name not in {"__init__.py", "index.js", "index.ts", "main.py", "server.py", "App.js"}])[:15]

    # Circular dependencies via DFS over the import graph (stem-level)
    graph: Dict[str, Set[str]] = defaultdict(set)
    stem_to_file: Dict[str, str] = {}
    for rel, deps in imports.items():
        stem = Path(rel).stem
        stem_to_file[stem] = rel
        for d in deps:
            graph[stem].add(Path(d).stem)

    cycles: List[List[str]] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = defaultdict(int)
    parent: Dict[str, str] = {}

    def dfs(node: str):
        color[node] = GRAY
        for neigh in graph.get(node, set()):
            if neigh not in stem_to_file:
                continue
            if color[neigh] == GRAY:
                # found cycle: trace
                cycle = [neigh]
                cur = node
                while cur != neigh and cur in parent:
                    cycle.append(cur)
                    cur = parent[cur]
                cycle.append(neigh)
                cycles.append([stem_to_file[s] for s in reversed(cycle) if s in stem_to_file])
            elif color[neigh] == WHITE:
                parent[neigh] = node
                dfs(neigh)
        color[node] = BLACK

    for n in list(graph.keys()):
        if color[n] == WHITE:
            dfs(n)

    return {
        "total_files": len(files),
        "largest_files": largest,
        "most_connected": most_connected,
        "possible_dead_code": dead,
        "circular_dependencies": cycles[:10],
    }


def repository_summary(root: Path) -> Dict:
    files = list(iter_source_files(root))
    return {
        "name": root.name,
        "total_files": len(files),
        "total_bytes": sum(f.stat().st_size for f in files if f.exists()),
    }


def graph_nodes_edges(root: Path) -> Dict[str, List[Dict]]:
    """Lightweight module graph (nodes + edges) for visualisation."""
    imports = _collect_imports(root)
    nodes_set: Set[str] = set()
    edges: List[Dict[str, str]] = []
    for rel, deps in imports.items():
        nodes_set.add(rel)
        for d in deps:
            # Find an internal target
            target = None
            for candidate in imports.keys():
                if Path(candidate).stem == d:
                    target = candidate
                    break
            if target:
                edges.append({"source": rel, "target": target})
                nodes_set.add(target)
    nodes = [{"id": n, "label": Path(n).name} for n in sorted(nodes_set)][:80]
    edges = edges[:120]
    allowed = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in allowed and e["target"] in allowed]
    return {"nodes": nodes, "edges": edges}
