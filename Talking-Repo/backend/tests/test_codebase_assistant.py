"""Backend API tests for AI Codebase Assistant.

Covers: root, vectorstore, github ingest (small public repo), invalid URL,
zip upload, search, chat (multi-turn), architecture, health-report, reindex, delete.
"""
from __future__ import annotations

import io
import os
import time
import zipfile

import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

# A small public GitHub repo recommended in the testing brief.
SMALL_REPO_URL = "https://github.com/python-jsonschema/jsonschema-specifications"
INDEX_TIMEOUT_SEC = 180  # generous, model is already downloaded


# ---------------- module-level fixtures ----------------
@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    yield s
    s.close()


def _poll_until_ready(http, repo_id, timeout=INDEX_TIMEOUT_SEC):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = http.get(f"{API}/repositories/{repo_id}", timeout=30)
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("ready", "failed"):
            return last
        time.sleep(2)
    return last


# ---------------- basic endpoints ----------------
class TestBasic:
    def test_root(self, http):
        r = http.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["app"] == "Endee Codebase Assistant"
        assert data["vector_store"] in ("faiss", "endee")

    def test_vectorstore_info(self, http):
        r = http.get(f"{API}/vectorstore", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["backend"] in ("faiss", "endee")
        names = {idx["name"] for idx in data["indexes"]}
        assert {"code_chunks", "documentation", "architecture_notes"} <= names
        for idx in data["indexes"]:
            if "error" in idx:
                continue
            # describe may include dimension; if it does, validate 384
            if "dimension" in idx:
                assert idx["dimension"] == 384


# ---------------- github ingest flow + downstream ----------------
@pytest.fixture(scope="module")
def github_repo(http):
    r = http.post(f"{API}/github", json={"url": SMALL_REPO_URL}, timeout=30)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["status"] in ("queued", "indexing")
    assert doc["source"] == "github"
    final = _poll_until_ready(http, doc["id"])
    assert final is not None
    assert final["status"] == "ready", f"Indexing failed: {final}"
    yield final
    # cleanup
    http.delete(f"{API}/repositories/{final['id']}", timeout=30)


class TestGitHubIngest:
    def test_invalid_url(self, http):
        r = http.post(f"{API}/github", json={"url": "not-a-url"}, timeout=15)
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "Invalid GitHub URL" in detail

    def test_github_indexed(self, github_repo):
        assert github_repo["files_indexed"] > 0
        assert github_repo["chunks_indexed"] > 0


# ---------------- search ----------------
class TestSearch:
    def test_search_results(self, http, github_repo):
        r = http.post(f"{API}/search", json={
            "repository_id": github_repo["id"],
            "query": "json schema validation",
            "top_k": 8,
        }, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "took_ms" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) > 0
        first = data["results"][0]
        for k in ("id", "score", "file", "language", "chunk_type", "content"):
            assert k in first, f"missing field {k}"


# ---------------- chat ----------------
class TestChat:
    def test_chat_two_turns(self, http, github_repo):
        # turn 1
        r1 = http.post(f"{API}/chat", json={
            "repository_id": github_repo["id"],
            "question": "What does this codebase do?",
        }, timeout=120)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["answer"], "empty answer"
        assert d1["session_id"]
        assert isinstance(d1.get("citations"), list)
        for cit in d1["citations"]:
            for k in ("file", "language", "chunk_type", "snippet", "score"):
                assert k in cit, f"citation missing {k}"

        # turn 2 - same session
        r2 = http.post(f"{API}/chat", json={
            "repository_id": github_repo["id"],
            "question": "Which files define vocabularies?",
            "session_id": d1["session_id"],
        }, timeout=120)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["answer"]
        assert d2["session_id"] == d1["session_id"]
        assert isinstance(d2.get("citations"), list)


# ---------------- architecture & health ----------------
class TestArchitecture:
    def test_architecture(self, http, github_repo):
        r = http.get(f"{API}/architecture/{github_repo['id']}", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("summary", "tech_stack", "folder_tree", "api_routes",
                  "languages", "graph"):
            assert k in d
        assert "Python" in d["tech_stack"]
        assert "nodes" in d["graph"] and "edges" in d["graph"]

    def test_health_report(self, http, github_repo):
        r = http.get(f"{API}/health-report/{github_repo['id']}", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total_files", "largest_files", "most_connected",
                  "possible_dead_code", "circular_dependencies"):
            assert k in d
        assert isinstance(d["largest_files"], list)
        if d["largest_files"]:
            assert "file" in d["largest_files"][0]
            assert "bytes" in d["largest_files"][0]


# ---------------- reindex ----------------
class TestReindex:
    def test_reindex(self, http, github_repo):
        r = http.post(f"{API}/index/{github_repo['id']}", timeout=30)
        assert r.status_code == 200
        assert r.json().get("reindexing") == github_repo["id"]


# ---------------- ZIP upload ----------------
class TestZipUpload:
    def test_zip_flow(self, http):
        # Build small zip in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("tiny_pkg/__init__.py", "# tiny pkg\n")
            zf.writestr(
                "tiny_pkg/hello.py",
                "def hello(name):\n    return f'hello {name}'\n\n"
                "def add(a, b):\n    return a + b\n",
            )
            zf.writestr(
                "tiny_pkg/util.py",
                "import json\n\nclass Util:\n    def to_json(self, x):\n"
                "        return json.dumps(x)\n",
            )
        buf.seek(0)
        files = {"file": ("tiny.zip", buf.getvalue(), "application/zip")}
        # don't send Content-Type: application/json header
        upload_session = requests.Session()
        r = upload_session.post(f"{API}/upload", files=files,
                                data={"name": "TEST_tiny"}, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["source"] == "zip"
        assert doc["status"] in ("queued", "indexing")

        final = _poll_until_ready(http, doc["id"], timeout=120)
        assert final["status"] == "ready", f"Indexing failed: {final}"
        assert final["files_indexed"] > 0
        # cleanup
        http.delete(f"{API}/repositories/{final['id']}", timeout=30)


# ---------------- delete ----------------
class TestDelete:
    def test_delete_repo(self, http):
        r = http.post(f"{API}/github", json={"url": SMALL_REPO_URL}, timeout=30)
        assert r.status_code == 200
        rid = r.json()["id"]
        d = http.delete(f"{API}/repositories/{rid}", timeout=30)
        assert d.status_code == 200
        assert d.json().get("deleted") == rid
        g = http.get(f"{API}/repositories/{rid}", timeout=15)
        assert g.status_code == 404
