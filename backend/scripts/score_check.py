"""
scripts/score_check.py — Calibrate MIN_RERANK_SCORE on real data.

Prints top rerank score across three categories:
1. In-document questions (should rank high and pass threshold)
2. Tricky out-of-document questions (related topic or terms, but unanswerable from doc)
3. Completely out-of-document questions (completely unrelated topic)

Usage:
    python scripts/score_check.py <workspace_id>
"""

import os
import sys
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

TRICKY_OUT_OF_DOC_QUESTIONS = [
    "does the policy mention GDPR fines",
    "who is the CEO of the company",
    "what is the phone number for customer support",
    "how do I delete my account step by step",
    "what encryption algorithm do you use",
]

OUT_OF_DOC_QUESTIONS = [
    "who won the 2018 world cup",
    "how to install python on windows",
    "what is the capital of france",
    "how many casual leaves can an employee take",
    "what is the refund policy for hotel bookings",
]


def evaluate_questions(workspace_id: uuid.UUID, questions: list[str], label: str) -> list[float]:
    print(f"=== {label} ===")
    scores = []
    for q in questions:
        results = retrieve(workspace_id=workspace_id, query=q, mode="hybrid", rerank=True)
        top_score = results[0].rerank_score if results else None
        if top_score is not None:
            scores.append(top_score)
            print(f"  Score: {top_score:8.4f} | Q: {q}")
        else:
            print(f"  Score:     None | Q: {q}")
    print()
    return scores


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/score_check.py <workspace_id>")
        sys.exit(1)

    workspace_id = uuid.UUID(sys.argv[1])
    print(f"Calibrating rerank scores for workspace {workspace_id}\n")

    in_scores = evaluate_questions(workspace_id, IN_DOC_QUESTIONS, "IN-DOCUMENT QUESTIONS")
    tricky_scores = evaluate_questions(workspace_id, TRICKY_OUT_OF_DOC_QUESTIONS, "TRICKY OUT-OF-DOCUMENT")
    out_scores = evaluate_questions(workspace_id, OUT_OF_DOC_QUESTIONS, "OUT-OF-DOCUMENT QUESTIONS")

    print("=== SUMMARY ===")
    if in_scores:
        print(f"In-doc min score:     {min(in_scores):.4f}")
        print(f"In-doc max score:     {max(in_scores):.4f}")
        print(f"In-doc mean score:    {sum(in_scores) / len(in_scores):.4f}")
    if tricky_scores:
        print(f"Tricky max score:     {max(tricky_scores):.4f}")
        print(f"Tricky min score:     {min(tricky_scores):.4f}")
        print(f"Tricky mean score:    {sum(tricky_scores) / len(tricky_scores):.4f}")
    if out_scores:
        print(f"Out-of-doc max score: {max(out_scores):.4f}")
        print(f"Out-of-doc min score: {min(out_scores):.4f}")
        print(f"Out-of-doc mean score:{sum(out_scores) / len(out_scores):.4f}")


if __name__ == "__main__":
    main()
