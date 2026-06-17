"""Pluggable VectorStore abstraction. Endee is the default/primary backend
(per the project spec for Endee Labs evaluation). FAISS is used as a local
development fallback when an Endee server / token is not reachable.

All retrieval workflows in this app are designed around the Endee API surface.
"""
from __future__ import annotations

import logging
import os
import pickle
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class VectorStoreBackend:
    """Abstract interface mirroring the Endee Python SDK."""

    name: str = "base"

    def ensure_index(self, name: str, dimension: int) -> None: ...
    def upsert(self, index: str, items: List[Dict[str, Any]]) -> None: ...
    def query(self, index: str, vector: List[float], top_k: int = 8,
              filter_: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]: ...
    def delete_index(self, index: str) -> None: ...
    def list_indexes(self) -> List[str]: ...
    def describe(self, index: str) -> Dict[str, Any]: ...


# ---------------- Endee backend ----------------
class EndeeBackend(VectorStoreBackend):
    name = "endee"

    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None):
        from endee import Endee  # type: ignore
        self.client = Endee(token=token) if token else Endee()
        if base_url:
            # Endee SDK expects a base URL that ends in /api/v1. If the caller
            # supplied only the server origin (e.g. http://localhost:8080), we
            # transparently append the API path.
            normalised = base_url.rstrip("/")
            if not normalised.endswith("/api/v1"):
                normalised = f"{normalised}/api/v1"
            self.client.set_base_url(normalised)
            self.base_url = normalised
        else:
            self.base_url = None
        # Probe connection eagerly so the factory can fall back if unreachable.
        self.client.list_indexes()

    def ensure_index(self, name: str, dimension: int) -> None:
    # Idempotent: try to create; if Endee says it already exists, that's fine.
        try:
            from endee import Precision  # type: ignore
            self.client.create_index(
                name=name, dimension=dimension, space_type="cosine",
                precision=Precision.INT8,
            )
            return
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "already exists" in msg or "conflict" in msg:
                return
            # Fallback: some Endee builds reject the precision kwarg.
            try:
                self.client.create_index(
                    name=name, dimension=dimension, space_type="cosine",
                )
                return
            except Exception as exc2:  # noqa: BLE001
                msg2 = str(exc2).lower()
                if "already exists" in msg2 or "conflict" in msg2:
                    return
                raise

    def _index(self, name: str):
        return self.client.get_index(name=name)

    def upsert(self, index: str, items: List[Dict[str, Any]]) -> None:
        if not items:
            return
        # Self-heal: ensure the index exists right before writing.
        # Endee can drop indexes silently after lock recovery / restarts.
        self.ensure_index(index, dimension=len(items[0]["vector"]))
        idx = self._index(index)
        for chunk_start in range(0, len(items), 500):
            batch = items[chunk_start:chunk_start + 500]
            payload = [
                {"id": it["id"], "vector": it["vector"],
                "meta": it.get("meta", {}),
                "filter": it.get("filter", {})}
                for it in batch
            ]
            idx.upsert(payload)


    def query(self, index: str, vector: List[float], top_k: int = 8,
              filter_: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        idx = self._index(index)
        kwargs: Dict[str, Any] = {"vector": vector, "top_k": top_k}
        if filter_:
            kwargs["filter"] = filter_
        results = idx.query(**kwargs)
        return [
            {"id": r["id"], "score": float(r.get("similarity", 0.0)),
             "meta": r.get("meta", {})}
            for r in results
        ]

    def delete_index(self, index: str) -> None:
        try:
            self.client.delete_index(index)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Endee delete_index failed: %s", exc)

    def list_indexes(self) -> List[str]:
        return [i if isinstance(i, str) else i.get("name", "") for i in self.client.list_indexes()]

    def describe(self, index: str) -> Dict[str, Any]:
        try:
            return self._index(index).describe()
        except Exception:
            return {"name": index}


# ---------------- FAISS fallback ----------------
# class FaissBackend(VectorStoreBackend):
#     """File-backed FAISS store used when Endee is unreachable. Same surface."""

#     name = "faiss"

#     def __init__(self, root: Path):
#         self.root = root
#         self.root.mkdir(parents=True, exist_ok=True)
#         self._locks: Dict[str, threading.Lock] = {}

#     def _paths(self, name: str):
#         return self.root / f"{name}.faiss", self.root / f"{name}.meta.pkl"

#     def _lock(self, name: str) -> threading.Lock:
#         if name not in self._locks:
#             self._locks[name] = threading.Lock()
#         return self._locks[name]

#     def _load(self, name: str, dimension: Optional[int] = None):
#         import faiss  # type: ignore
#         ipath, mpath = self._paths(name)
#         if ipath.exists() and mpath.exists():
#             idx = faiss.read_index(str(ipath))
#             with open(mpath, "rb") as f:
#                 meta = pickle.load(f)
#             return idx, meta
#         if dimension is None:
#             raise FileNotFoundError(f"Index {name} not found")
#         idx = faiss.IndexFlatIP(dimension)
#         meta = {"ids": [], "items": {}, "dimension": dimension}
#         return idx, meta

#     def _save(self, name: str, idx, meta):
#         import faiss  # type: ignore
#         ipath, mpath = self._paths(name)
#         faiss.write_index(idx, str(ipath))
#         with open(mpath, "wb") as f:
#             pickle.dump(meta, f)

#     def ensure_index(self, name: str, dimension: int) -> None:
#         with self._lock(name):
#             idx, meta = self._load(name, dimension)
#             self._save(name, idx, meta)

#     def upsert(self, index: str, items: List[Dict[str, Any]]) -> None:
#         with self._lock(index):
#             idx, meta = self._load(index, len(items[0]["vector"]) if items else None)
#             vectors = []
#             for it in items:
#                 vec = np.asarray(it["vector"], dtype="float32")
#                 norm = np.linalg.norm(vec)
#                 if norm > 0:
#                     vec = vec / norm
#                 vectors.append(vec)
#                 meta["items"][it["id"]] = {"meta": it.get("meta", {}),
#                                            "filter": it.get("filter", {}),
#                                            "row": len(meta["ids"])}
#                 meta["ids"].append(it["id"])
#             if vectors:
#                 idx.add(np.vstack(vectors))
#             self._save(index, idx, meta)

#     def query(self, index: str, vector: List[float], top_k: int = 8,
#               filter_: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
#         with self._lock(index):
#             try:
#                 idx, meta = self._load(index)
#             except FileNotFoundError:
#                 return []
#             if idx.ntotal == 0:
#                 return []
#             q = np.asarray(vector, dtype="float32")
#             norm = np.linalg.norm(q)
#             if norm > 0:
#                 q = q / norm
#             scores, rows = idx.search(q.reshape(1, -1), min(top_k * 4, idx.ntotal))
#             out: List[Dict[str, Any]] = []
#             for score, row in zip(scores[0], rows[0]):
#                 if row < 0 or row >= len(meta["ids"]):
#                     continue
#                 _id = meta["ids"][row]
#                 entry = meta["items"][_id]
#                 if filter_ and not _match_filter(entry.get("filter", {}), filter_):
#                     continue
#                 out.append({"id": _id, "score": float(score), "meta": entry.get("meta", {})})
#                 if len(out) >= top_k:
#                     break
#             return out

#     def delete_index(self, index: str) -> None:
#         with self._lock(index):
#             ipath, mpath = self._paths(index)
#             for p in (ipath, mpath):
#                 if p.exists():
#                     p.unlink()

#     def list_indexes(self) -> List[str]:
#         return sorted(p.stem for p in self.root.glob("*.faiss"))

#     def describe(self, index: str) -> Dict[str, Any]:
#         try:
#             idx, meta = self._load(index)
#             return {"name": index, "count": idx.ntotal, "dimension": meta.get("dimension")}
#         except FileNotFoundError:
#             return {"name": index, "count": 0}


def _match_filter(filter_fields: Dict[str, Any], conditions: List[Dict[str, Any]]) -> bool:
    for cond in conditions:
        for field, op in cond.items():
            val = filter_fields.get(field)
            if isinstance(op, dict):
                if "$eq" in op and val != op["$eq"]:
                    return False
                if "$in" in op and val not in op["$in"]:
                    return False
            elif val != op:
                return False
    return True


# ---------------- Factory ----------------
_singleton: Optional[VectorStoreBackend] = None


def get_vector_store() -> VectorStoreBackend:
    global _singleton
    if _singleton is not None:
        return _singleton

    backend = (os.environ.get("VECTOR_STORE_BACKEND") or "auto").lower()
    endee_enabled = (os.environ.get("ENDEE_ENABLED") or "true").lower() == "true"
    token = os.environ.get("ENDEE_TOKEN") or None
    base_url = os.environ.get("ENDEE_BASE_URL") or "http://localhost:8080"
    data_dir = Path(os.environ.get("REPO_DATA_DIR", "/app/backend/data/repos")).parent / "faiss"

    if endee_enabled and backend in ("endee", "auto"):
        try:
            store: VectorStoreBackend = EndeeBackend(token=token, base_url=base_url)
            logger.info("Vector store: ENDEE (primary) initialised at %s.", base_url)
            _singleton = store
            return store
        except Exception as exc:  # noqa: BLE001
            logger.warning("Endee unavailable at %s (%s) — falling back to FAISS dev backend.",
                           base_url, exc)
            if backend == "endee":
                # Strict Endee mode: re-raise.
                raise

    # _singleton = FaissBackend(data_dir)
    # logger.info("Vector store: FAISS (fallback) initialised at %s.", data_dir)
    # return _singleton
