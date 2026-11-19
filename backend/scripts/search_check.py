"""
scripts/search_check.py — Manual vector search inspection tool.

Usage:
    python scripts/search_check.py <workspace_id> "<query>" [--mode dense|sparse]

Prints the raw top-5 results (score, document, page, first 150 chars of text).
This is a debugging/inspection tool only — no authentication, no reranking.

Run from the backend/ directory with the venv active.
"""

import argparse
import sys

# Ensure app is importable from backend/ directory
sys.path.insert(0, ".")

from app.core.config import settings
from app.services import embedding_service
from app.services.vector_service import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    get_qdrant_client,
)
from qdrant_client.http import models as qmodels


def search_dense(workspace_id: str, query: str, top_k: int = 5) -> list:
    client = get_qdrant_client()
    q_vec = embedding_service.embed_query(query)
    results = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=q_vec,
        using=DENSE_VECTOR_NAME,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="workspace_id",
                    match=qmodels.MatchValue(value=workspace_id),
                )
            ]
        ),
        limit=top_k,
        with_payload=True,
    ).points
    return results


def search_sparse(workspace_id: str, query: str, top_k: int = 5) -> list:
    client = get_qdrant_client()
    q_sparse = embedding_service.sparse_query(query)
    results = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=qmodels.SparseVector(
            indices=q_sparse["indices"],
            values=q_sparse["values"],
        ),
        using=SPARSE_VECTOR_NAME,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="workspace_id",
                    match=qmodels.MatchValue(value=workspace_id),
                )
            ]
        ),
        limit=top_k,
        with_payload=True,
    ).points
    return results


def print_results(results: list, mode: str) -> None:
    print(f"\n── {mode.upper()} search results ({'top ' + str(len(results))}) ───")
    if not results:
        print("  (no results)")
        return
    for i, r in enumerate(results, 1):
        p = r.payload or {}
        text_preview = (p.get("text") or "")[:150].replace("\n", " ")
        print(
            f"  [{i}] score={r.score:.4f}  doc={p.get('document_name', '?')}  "
            f"page={p.get('page_number')}  section={p.get('section_title')!r}\n"
            f"       {text_preview!r}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Vector search inspection tool.")
    parser.add_argument("workspace_id", help="Workspace UUID to search within.")
    parser.add_argument("query", help="Search query string.")
    parser.add_argument(
        "--mode",
        choices=["dense", "sparse", "both"],
        default="both",
        help="Which search mode to use (default: both).",
    )
    args = parser.parse_args()

    print(f"Query   : {args.query!r}")
    print(f"Mode    : {args.mode}")
    print(f"Collection: {settings.QDRANT_COLLECTION}")

    if args.mode in ("dense", "both"):
        results = search_dense(args.workspace_id, args.query)
        print_results(results, "dense")

    if args.mode in ("sparse", "both"):
        results = search_sparse(args.workspace_id, args.query)
        print_results(results, "sparse")


if __name__ == "__main__":
    main()
