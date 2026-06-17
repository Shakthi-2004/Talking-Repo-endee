"""RAG chat orchestration using Endee retrieval +  Google Gemini 2.5 flash"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List

from .embedder import embed_one
from .vectorstore import get_vector_store
from google import genai
from google.genai import types as genai_types

_gemini_client = None
_gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

def _get_llm():
    global _gemini_client
    if _gemini_client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            return None
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client

logger = logging.getLogger(__name__)

CODE_INDEX = "code_chunks"
DOC_INDEX = "documentation"
ARCH_INDEX = "architecture_notes"


@dataclass
class Citation:
    file: str
    language: str
    chunk_type: str
    snippet: str
    score: float

    def to_dict(self) -> Dict:
        return {"file": self.file, "language": self.language,
                "chunk_type": self.chunk_type, "snippet": self.snippet,
                "score": self.score}


def search_code(repo_id: str, query: str, top_k: int = 5) -> List[Dict]:
    store = get_vector_store()
    vec = embed_one(query)
    results = store.query(CODE_INDEX, vec, top_k=top_k,
                          filter_=[{"repository_id": {"$eq": repo_id}}])
    return results


def build_context(results: List[Dict], max_chars: int = 6000) -> tuple:
    pieces: List[str] = []
    citations: List[Citation] = []
    total = 0
    for r in results:
        meta = r.get("meta") or {}
        content = meta.get("content", "")
        if not content:
            continue
        file_label = meta.get("file") or meta.get("file_name", "?")
        header = f"--- {file_label}  ({meta.get('language', '?')}) ---"
        block = f"{header}\n{content}\n"
        if total + len(block) > max_chars:
            break
        pieces.append(block)
        total += len(block)
        citations.append(Citation(
            file=file_label,
            language=meta.get("language", "?"),
            chunk_type=meta.get("chunk_type", "?"),
            snippet=content[:400],
            score=float(r.get("score", 0.0)),
        ))
    return "\n".join(pieces), citations


SYSTEM_PROMPT = (
    "You are 'Endee Codebase Assistant', an expert software engineer who explains "
    "unfamiliar codebases. You answer using ONLY the provided code context. "
    "If the context is insufficient, say so clearly. When you cite a fact, mention the "
    "source file in backticks (e.g. `src/auth.py`). Be concise, accurate, and structured."
)


async def answer(repo_id: str, question: str, session_id: str) -> Dict:
    client = _get_llm()
    if not client:
        return {"answer": "GEMINI_API_KEY missing in backend/.env.", "citations": []}

    results = search_code(repo_id, question, top_k=5)
    context, citations = build_context(results)

    user_text = (
        f"Repository code context:\n\n{context}\n\n"
        f"Question: {question}\n\nAnswer using the context above."
    )
    response = await client.aio.models.generate_content(
        model=_gemini_model,
        contents=user_text,
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=1024,
        ),
    )
    return {
        "answer": response.text or "",
        "citations": [c.to_dict() for c in citations],
    }



# ---------------------------------------------------------------
# Endee-driven architecture summary.
#
# Per the Endee Labs spec: "Generate architecture summaries using
# code chunks retrieved from Endee rather than scanning files
# repeatedly." This function never reads files directly — it issues
# several semantic queries against the Endee `code_chunks` index,
# stitches the top retrievals into a context window, and asks
# Gemini to synthesise a high-level architectural overview.
# ---------------------------------------------------------------
ARCH_PROBES = [
    "application entry point and server bootstrap",
    "core domain models and database schema",
    "API routes and request handlers",
    "authentication, session or authorization logic",
    "configuration, environment variables and dependency wiring",
    "background jobs, queues or long-running tasks",
    "third-party integrations and external services",
]


async def architecture_summary(repo_id: str, repo_name: str) -> Dict:
    """Build an LLM architecture overview using ONLY chunks retrieved from Endee."""
    store = get_vector_store()
    seen_ids = set()
    citations: List[Citation] = []
    context_pieces: List[str] = []
    total = 0
    MAX_CTX = 8000

    for probe in ARCH_PROBES:
        vec = embed_one(probe)
        hits = store.query(
            CODE_INDEX, vec, top_k=3,
            filter_=[{"repository_id": {"$eq": repo_id}}],
        )
        for r in hits:
            if r["id"] in seen_ids:
                continue
            seen_ids.add(r["id"])
            meta = r.get("meta") or {}
            content = meta.get("content", "")
            if not content:
                continue
            file_label = meta.get("file") or meta.get("file_name", "?")
            block = (
                f"### probe: {probe}\n"
                f"file: {file_label}  ({meta.get('language', '?')})\n"
                f"{content}\n"
            )
            if total + len(block) > MAX_CTX:
                break
            context_pieces.append(block)
            total += len(block)
            citations.append(Citation(
                file=file_label,
                language=meta.get("language", "?"),
                chunk_type=meta.get("chunk_type", "?"),
                snippet=content[:300],
                score=float(r.get("score", 0.0)),
            ))
        if total >= MAX_CTX:
            break

    if not context_pieces:
        return {"summary": "Endee returned no chunks for this repository — try re-indexing.",
                "citations": []}

    client = _get_llm()
    if not client:
        return {"summary": "GEMINI_API_KEY missing — cannot synthesise summary.",
                "citations": [c.to_dict() for c in citations]}

    system = (
        "You are a staff engineer producing a concise, accurate architecture brief for "
        "an unfamiliar repository. You may ONLY use the provided code excerpts. Output "
        "Markdown with these sections in order: Overview, Entry Points, Core Modules, "
        "Data Layer, External Integrations, Notable Patterns. Keep it under 350 words. "
        "Cite source files in backticks."
    )

    user_text = (
        f"Repository name: {repo_name}\n\n"
        f"Top semantic excerpts retrieved from Endee (each prefixed by the probe used):\n\n"
        + "\n\n".join(context_pieces)
        + "\n\nWrite the architecture brief now."
    )

    response = await client.aio.models.generate_content(
        model=_gemini_model,
        contents=user_text,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=1024,
        ),
    )

    return {
        "summary": response.text or "",
        "citations": [c.to_dict() for c in citations],
    }
