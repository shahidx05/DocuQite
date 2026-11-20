"""
rag/generation.py — Grounded answer generation pipeline with citations and abstention.

Pipeline:
    1. Retrieve candidates via hybrid search + cross-encoder reranking.
    2. Check confidence threshold: abstain if no chunks or top rerank_score < MIN_RERANK_SCORE.
    3. Build context blocks respecting MAX_CONTEXT_CHARS.
    4. Call LLM (Gemini via llm_service).
    5. Validate citations (strip invalid [n] markers; collect valid citation details).
    6. Return AskResponse with answer, abstained status, citations, timings, and token metrics.
"""

import logging
import re
import time
import uuid
from typing import Optional

from app.core.config import settings
from app.rag.prompts import ABSTENTION_MESSAGE, GROUNDING_SYSTEM_PROMPT, build_user_prompt
from app.schemas.ask import AskResponse, AskTimings, AskTokens, Citation
from app.services import llm_service, retrieval_service

logger = logging.getLogger(__name__)


def answer(
    workspace_id: uuid.UUID,
    question: str,
    collection_name: Optional[str] = None,
) -> AskResponse:
    """
    Generate a grounded answer for the question using workspace documents.

    Args:
        workspace_id:    Only use documents from this workspace.
        question:        User's natural-language question.
        collection_name: Override Qdrant collection name (used in tests).

    Returns:
        AskResponse with answer text, abstained flag, citations, timings, and token counts.
    """
    t_start = time.perf_counter()

    # ── 1. Retrieve candidates (hybrid + rerank) ──────────────────────
    t_ret = time.perf_counter()
    candidates = retrieval_service.retrieve(
        workspace_id=workspace_id,
        query=question,
        mode="hybrid",
        rerank=True,
        collection_name=collection_name,
    )
    retrieval_ms = int((time.perf_counter() - t_ret) * 1000)
    embed_ms = getattr(candidates, "embed_ms", 0)
    qdrant_ms = getattr(candidates, "qdrant_ms", 0)
    rerank_ms = getattr(candidates, "rerank_ms", 0)
    candidates_count = getattr(candidates, "candidates_count", len(candidates))

    # ── 2. Abstention check ────────────────────────────────────────────
    # If no results or top score below threshold, abstain immediately without calling LLM.
    top_score = candidates[0].rerank_score if candidates else None
    if not candidates or top_score is None or top_score < settings.MIN_RERANK_SCORE:
        total_ms = int((time.perf_counter() - t_start) * 1000)
        logger.info(
            "Abstaining before LLM call: candidates=%d, top_score=%s, min_threshold=%.2f",
            len(candidates),
            top_score,
            settings.MIN_RERANK_SCORE,
        )
        return AskResponse(
            answer=ABSTENTION_MESSAGE,
            abstained=True,
            citations=[],
            timings=AskTimings(
                retrieval_ms=retrieval_ms,
                llm_ms=0,
                total_ms=total_ms,
                embed_ms=embed_ms,
                qdrant_ms=qdrant_ms,
                rerank_ms=rerank_ms,
            ),
            tokens=AskTokens(
                input_tokens=0,
                output_tokens=0,
            ),
            candidates_count=candidates_count,
            top_rerank_score=top_score,
        )

    # ── 3. Build context blocks respecting MAX_CONTEXT_CHARS ───────────
    context_blocks = []
    total_chars = 0
    for idx, candidate in enumerate(candidates, 1):
        chunk_text = candidate.text
        # Truncate if single chunk exceeds limit on its own
        if total_chars + len(chunk_text) > settings.MAX_CONTEXT_CHARS:
            if context_blocks:
                break
            chunk_text = chunk_text[: settings.MAX_CONTEXT_CHARS]

        context_blocks.append(
            {
                "index": idx,
                "document_id": candidate.document_id,
                "document_name": candidate.document_name,
                "page_number": candidate.page_number,
                "section_title": candidate.section_title,
                "text": chunk_text,
            }
        )
        total_chars += len(chunk_text)

    # ── 4. Call LLM ────────────────────────────────────────────────────
    system_prompt = GROUNDING_SYSTEM_PROMPT
    user_prompt = build_user_prompt(question, context_blocks)

    llm_res = llm_service.generate(system_prompt=system_prompt, user_prompt=user_prompt)
    raw_answer = llm_res["text"].strip()
    llm_ms = llm_res["latency_ms"]
    input_tokens = llm_res["input_tokens"]
    output_tokens = llm_res["output_tokens"]

    # ── 5. Validate citations and abstention ───────────────────────────
    if raw_answer == ABSTENTION_MESSAGE or raw_answer.startswith(ABSTENTION_MESSAGE):
        total_ms = int((time.perf_counter() - t_start) * 1000)
        return AskResponse(
            answer=ABSTENTION_MESSAGE,
            abstained=True,
            citations=[],
            timings=AskTimings(
                retrieval_ms=retrieval_ms,
                llm_ms=llm_ms,
                total_ms=total_ms,
                embed_ms=embed_ms,
                qdrant_ms=qdrant_ms,
                rerank_ms=rerank_ms,
            ),
            tokens=AskTokens(input_tokens=input_tokens, output_tokens=output_tokens),
            candidates_count=candidates_count,
            top_rerank_score=top_score,
        )

    valid_indices = {b["index"] for b in context_blocks}

    # Remove invalid citations (e.g. [99] where only 1-5 exist)
    def _validate_citation(match: re.Match) -> str:
        num = int(match.group(1))
        return match.group(0) if num in valid_indices else ""

    cleaned_answer = re.sub(r"\[(\d+)\]", _validate_citation, raw_answer)
    cleaned_answer = re.sub(r" +", " ", cleaned_answer).strip()

    # Collect unique citations in order of appearance
    cited_indices: list[int] = []
    for match in re.finditer(r"\[(\d+)\]", cleaned_answer):
        num = int(match.group(1))
        if num in valid_indices and num not in cited_indices:
            cited_indices.append(num)

    citations = []
    for num in cited_indices:
        b = context_blocks[num - 1]
        citations.append(
            Citation(
                n=num,
                document_id=b["document_id"],
                document_name=b["document_name"],
                page_number=b["page_number"],
                section_title=b["section_title"],
                snippet=b["text"][:200],
            )
        )

    total_ms = int((time.perf_counter() - t_start) * 1000)
    return AskResponse(
        answer=cleaned_answer,
        abstained=False,
        citations=citations,
        timings=AskTimings(
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            total_ms=total_ms,
            embed_ms=embed_ms,
            qdrant_ms=qdrant_ms,
            rerank_ms=rerank_ms,
        ),
        tokens=AskTokens(input_tokens=input_tokens, output_tokens=output_tokens),
        candidates_count=candidates_count,
        top_rerank_score=top_score,
    )
