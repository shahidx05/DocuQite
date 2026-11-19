"""
scripts/score_check.py — Calibrate MIN_RERANK_SCORE on real data.

Prints top rerank score for 5 in-document questions and 5 out-of-document questions.
Usage:
    python scripts/score_check.py <workspace_id>
"""

import sys
import os
import uuid

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.retrieval_service import retrieve

IN_DOC_QUESTIONS = [
    "what personal information do you collect",
    "data retention policy",
    "how do you protect my data",
    "do you share information with third parties",
    "what are my rights regarding my personal data",
]

OUT_OF_DOC_QUESTIONS = [
    "who won the 2018 world cup",
    "how to bake chocolate chip cookies",
    "what is the capital of Australia",
    "how does a turbocharger work in a car",
    "what is the formula for calculating compound interest",
]


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/score_check.py <workspace_id>")
        sys.exit(1)

    workspace_id = uuid.UUID(sys.argv[1])
    print(f"Calibrating rerank scores for workspace {workspace_id}\n")

    print("=== IN-DOCUMENT QUESTIONS ===")
    in_scores = []
    for q in IN_DOC_QUESTIONS:
        results = retrieve(workspace_id=workspace_id, query=q, mode="hybrid", rerank=True)
        top_score = results[0].rerank_score if results else None
        in_scores.append(top_score)
        print(f"  Score: {top_score:8.4f} | Q: {q}")

    print("\n=== OUT-OF-DOCUMENT QUESTIONS ===")
    out_scores = []
    for q in OUT_OF_DOC_QUESTIONS:
        results = retrieve(workspace_id=workspace_id, query=q, mode="hybrid", rerank=True)
        top_score = results[0].rerank_score if results else None
        out_scores.append(top_score)
        print(f"  Score: {top_score:8.4f} | Q: {q}")

    valid_in = [s for s in in_scores if s is not None]
    valid_out = [s for s in out_scores if s is not None]

    print("\n=== SUMMARY ===")
    if valid_in:
        print(f"In-doc min score:  {min(valid_in):.4f}")
        print(f"In-doc max score:  {max(valid_in):.4f}")
        print(f"In-doc mean score: {sum(valid_in) / len(valid_in):.4f}")
    if valid_out:
        print(f"Out-of-doc min score:  {min(valid_out):.4f}")
        print(f"Out-of-doc max score:  {max(valid_out):.4f}")
        print(f"Out-of-doc mean score: {sum(valid_out) / len(valid_out):.4f}")


if __name__ == "__main__":
    main()
