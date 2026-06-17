"""FastAPI backend for AI Codebase Assistant powered by Endee Vector DB."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# --- third-party services ---
from services.analyzer import (  # noqa: E402
    detect_api_routes, detect_tech_stack, folder_structure,
    graph_nodes_edges, health_report, language_breakdown, repository_summary,
)
from services.chunker import chunk_file  # noqa: E402
from services.embedder import DIMENSION, embed  # noqa: E402
from services.rag import (  # noqa: E402
    ARCH_INDEX, CODE_INDEX, DOC_INDEX, answer as rag_answer, search_code,
)
from services.repo_ingest import (  # noqa: E402
    clone_github, extract_zip, iter_source_files, parse_github_url, safe_cleanup,
)
from services.vectorstore import get_vector_store  # noqa: E402

# --- logging ---
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("endee-codebase")

# --- mongo ---
mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

# --- repo storage dir ---
REPO_DIR = Path(os.environ.get("REPO_DATA_DIR", "/app/backend/data/repos"))
REPO_DIR.mkdir(parents=True, exist_ok=True)

# --- FastAPI ---
app = FastAPI(title="Endee Codebase Assistant")
api = APIRouter(prefix="/api")


# ============================================================
#                       MODELS
# ============================================================
class Repository(BaseModel):
    id: str
    name: str
    source: str  # "github" | "zip"
    url: Optional[str] = None
    status: str  # "queued" | "indexing" | "ready" | "failed"
    progress: float = 0.0
    files_indexed: int = 0
    chunks_indexed: int = 0
    languages: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: str
    updated_at: str


class GitHubReq(BaseModel):
    url: str


class SearchReq(BaseModel):
    repository_id: str
    query: str
    top_k: int = 8


class ChatReq(BaseModel):
    repository_id: str
    question: str
    session_id: Optional[str] = None


# ============================================================
#                       HELPERS
# ============================================================
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _save_repo(doc: Dict[str, Any]) -> None:
    await db.repositories.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)


async def _get_repo(repo_id: str) -> Optional[Dict[str, Any]]:
    return await db.repositories.find_one({"id": repo_id}, {"_id": 0})


async def _update_repo(repo_id: str, **patch: Any) -> None:
    patch["updated_at"] = _now()
    await db.repositories.update_one({"id": repo_id}, {"$set": patch})


def _repo_path(repo_id: str) -> Path:
    return REPO_DIR / repo_id


def _ensure_indexes_blocking() -> None:
    store = get_vector_store()
    for name in (CODE_INDEX, DOC_INDEX, ARCH_INDEX):
        store.ensure_index(name, DIMENSION)


async def _index_repository(repo_id: str, root: Path) -> None:
    """Background pipeline: chunk → embed → upsert into Endee/FAISS."""
    try:
        await _update_repo(repo_id, status="indexing", progress=0.05)
        repo_doc = await _get_repo(repo_id) or {}
        repo_name = repo_doc.get("name") or repo_id
        logger.info("[%s] step: ensuring Endee indexes", repo_id)
        await asyncio.to_thread(_ensure_indexes_blocking)
        logger.info("[%s] step: walking source files", repo_id)
        store = get_vector_store()
        files = list(iter_source_files(root))
        logger.info("[%s] step: chunking %d files", repo_id, len(files))
        total_files = len(files) or 1
        all_chunks: List[Dict[str, Any]] = []

        for i, fp in enumerate(files):
            chunks = chunk_file(repo_id, root, fp)
            for c in chunks:
                d = c.to_dict()
                d["repository_id"] = repo_id
                all_chunks.append(d)
            if i % 25 == 0:
                await _update_repo(repo_id, progress=round(0.05 + 0.35 * (i / total_files), 3),
                                   files_indexed=i + 1)

        await _update_repo(repo_id, progress=0.45, files_indexed=total_files,
                           chunks_indexed=len(all_chunks))

        if not all_chunks:
            await _update_repo(repo_id, status="failed", error="No source code chunks produced.")
            return

        # Embed in batches
        BATCH = 64
        records: List[Dict[str, Any]] = []
        for start in range(0, len(all_chunks), BATCH):
            slab = all_chunks[start:start + BATCH]
            texts = [c["content"] for c in slab]
            vectors = await asyncio.to_thread(embed, texts)
            for chunk, vec in zip(slab, vectors):
                records.append({
                    "id": chunk["id"],
                    "vector": vec,
                    # Metadata schema (per Endee Labs spec):
                    # file, language, function, class, repository
                    # plus content + chunk_type + line range for the UI/RAG.
                    "meta": {
                        "file": chunk["file_name"],
                        "language": chunk["language"],
                        "function": chunk.get("function_name"),
                        "class": chunk.get("class_name"),
                        "repository": repo_name,
                        "repository_id": repo_id,
                        "chunk_type": chunk["chunk_type"],
                        "start_line": chunk.get("start_line"),
                        "end_line": chunk.get("end_line"),
                        "content": chunk["content"][:4000],
                    },
                    # Searchable filters (per spec): language, repository.
                    # We also keep repository_id for unique scoping in case
                    # two ingested repos share the same display name.
                    "filter": {
                        "repository": repo_name,
                        "repository_id": repo_id,
                        "language": chunk["language"],
                        "chunk_type": chunk["chunk_type"],
                    },
                })
            progress = 0.45 + 0.45 * (start + BATCH) / max(1, len(all_chunks))
            await _update_repo(repo_id, progress=round(min(0.9, progress), 3))

        await asyncio.to_thread(store.upsert, CODE_INDEX, records)

        # Pre-compute language breakdown for the dashboard
        langs = language_breakdown(root)
        await _update_repo(repo_id, status="ready", progress=1.0,
                           chunks_indexed=len(records), languages=langs)
        logger.info("Repository %s indexed: %d chunks", repo_id, len(records))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Indexing failed for %s", repo_id)
        await _update_repo(repo_id, status="failed", error=str(exc))


# ============================================================
#                       ENDPOINTS
# ============================================================
@api.get("/")
async def root():
    store = get_vector_store()
    return {"app": "Endee Codebase Assistant", "vector_store": store.name}


@api.get("/repositories", response_model=List[Repository])
async def list_repositories():
    docs = await db.repositories.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return docs


@api.get("/repositories/{repo_id}", response_model=Repository)
async def get_repository(repo_id: str):
    doc = await _get_repo(repo_id)
    if not doc:
        raise HTTPException(404, "Repository not found")
    return doc


@api.delete("/repositories/{repo_id}")
async def delete_repository(repo_id: str):
    store = get_vector_store()
    try:
        store.delete_index(CODE_INDEX)  # FAISS-friendly: index per-app, repo isolation via filter
    except Exception:
        pass
    safe_cleanup(_repo_path(repo_id))
    await db.repositories.delete_one({"id": repo_id})
    return {"deleted": repo_id}


@api.post("/github", response_model=Repository)
async def ingest_github(req: GitHubReq):
    parsed = parse_github_url(req.url)
    if not parsed:
        raise HTTPException(400, "Invalid GitHub URL (expected https://github.com/<owner>/<repo>).")
    owner, name = parsed
    repo_id = str(uuid.uuid4())
    doc = {
        "id": repo_id, "name": f"{owner}/{name}", "source": "github", "url": req.url,
        "status": "queued", "progress": 0.0, "files_indexed": 0, "chunks_indexed": 0,
        "languages": [], "error": None, "created_at": _now(), "updated_at": _now(),
    }
    await _save_repo(doc)

    async def _runner():
        try:
            path = _repo_path(repo_id)
            await asyncio.to_thread(clone_github, req.url, path)
            await _index_repository(repo_id, path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("GitHub ingest failed")
            await _update_repo(repo_id, status="failed", error=str(exc))

    asyncio.create_task(_runner())
    return doc


@api.post("/upload", response_model=Repository)
async def ingest_upload(file: UploadFile = File(...), name: Optional[str] = Form(None)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Only .zip uploads are supported.")
    repo_id = str(uuid.uuid4())
    repo_name = name or Path(file.filename).stem
    doc = {
        "id": repo_id, "name": repo_name, "source": "zip", "url": None,
        "status": "queued", "progress": 0.0, "files_indexed": 0, "chunks_indexed": 0,
        "languages": [], "error": None, "created_at": _now(), "updated_at": _now(),
    }
    await _save_repo(doc)

    tmp_dir = Path(tempfile.mkdtemp(prefix="upload_"))
    zip_path = tmp_dir / file.filename
    with open(zip_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    async def _runner():
        try:
            dest = _repo_path(repo_id)
            extracted = await asyncio.to_thread(extract_zip, zip_path, dest)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            await _index_repository(repo_id, extracted)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ZIP ingest failed")
            await _update_repo(repo_id, status="failed", error=str(exc))

    asyncio.create_task(_runner())
    return doc


@api.post("/index/{repo_id}")
async def reindex(repo_id: str):
    doc = await _get_repo(repo_id)
    if not doc:
        raise HTTPException(404, "Repository not found")
    path = _repo_path(repo_id)
    if not path.exists():
        raise HTTPException(400, "Repository files no longer exist on disk.")
    asyncio.create_task(_index_repository(repo_id, path))
    return {"reindexing": repo_id}


@api.post("/search")
async def semantic_search(req: SearchReq):
    t0 = time.time()
    results = await asyncio.to_thread(search_code, req.repository_id, req.query, req.top_k)
    enriched = []
    for r in results:
        meta = r.get("meta", {})
        enriched.append({
            "id": r["id"], "score": r["score"],
            "file": meta.get("file") or meta.get("file_name"),
            "language": meta.get("language"),
            "chunk_type": meta.get("chunk_type"),
            "function_name": meta.get("function") or meta.get("function_name"),
            "class_name": meta.get("class") or meta.get("class_name"),
            "repository": meta.get("repository"),
            "start_line": meta.get("start_line"),
            "end_line": meta.get("end_line"),
            "content": meta.get("content", ""),
        })
    return {"query": req.query, "took_ms": int((time.time() - t0) * 1000),
            "results": enriched}


@api.post("/chat")
async def chat(req: ChatReq):
    session_id = req.session_id or str(uuid.uuid4())
    result = await rag_answer(req.repository_id, req.question, session_id)
    await db.chat_messages.insert_one({
        "id": str(uuid.uuid4()),
        "repository_id": req.repository_id,
        "session_id": session_id,
        "question": req.question,
        "answer": result.get("answer"),
        "citations": result.get("citations", []),
        "created_at": _now(),
    })
    return {"session_id": session_id, **result}


@api.get("/chat/{repository_id}")
async def chat_history(repository_id: str, session_id: Optional[str] = None):
    query: Dict[str, Any] = {"repository_id": repository_id}
    if session_id:
        query["session_id"] = session_id
    msgs = await db.chat_messages.find(query, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"messages": msgs}


@api.get("/architecture/{repo_id}")
async def architecture(repo_id: str):
    doc = await _get_repo(repo_id)
    if not doc:
        raise HTTPException(404, "Repository not found")
    path = _repo_path(repo_id)
    if not path.exists():
        raise HTTPException(400, "Repository files no longer exist on disk.")
    summary = await asyncio.to_thread(repository_summary, path)
    stack = await asyncio.to_thread(detect_tech_stack, path)
    tree = await asyncio.to_thread(folder_structure, path)
    routes = await asyncio.to_thread(detect_api_routes, path)
    langs = await asyncio.to_thread(language_breakdown, path)
    graph = await asyncio.to_thread(graph_nodes_edges, path)
    # Endee-driven LLM brief — uses chunks retrieved from Endee, no file scanning.
    try:
        from services.rag import architecture_summary
        brief = await architecture_summary(repo_id, doc.get("name") or repo_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("architecture_summary failed: %s", exc)
        brief = {"summary": None, "citations": []}
    return {
        "summary": summary, "tech_stack": stack["stack"], "folder_tree": tree,
        "api_routes": routes, "languages": langs, "graph": graph,
        "brief": brief.get("summary"),
        "brief_citations": brief.get("citations", []),
    }


@api.get("/health-report/{repo_id}")
async def health(repo_id: str):
    doc = await _get_repo(repo_id)
    if not doc:
        raise HTTPException(404, "Repository not found")
    path = _repo_path(repo_id)
    if not path.exists():
        raise HTTPException(400, "Repository files no longer exist on disk.")
    return await asyncio.to_thread(health_report, path)


@api.get("/vectorstore")
async def vectorstore_info():
    store = get_vector_store()
    info: Dict[str, Any] = {"backend": store.name, "indexes": []}
    for name in (CODE_INDEX, DOC_INDEX, ARCH_INDEX):
        try:
            info["indexes"].append({"name": name, **store.describe(name)})
        except Exception as exc:  # noqa: BLE001
            info["indexes"].append({"name": name, "error": str(exc)})
    return info


# Mount router & CORS
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup():
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_ensure_indexes_blocking),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Vector indexes pre-create timed out — will retry lazily.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector indexes not pre-created: %s", exc)


@app.on_event("shutdown")
async def _shutdown():
    mongo_client.close()
