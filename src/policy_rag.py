import sys
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mock_llm


POLICY_DIR = ROOT / "data" / "policies"
EVAL_FILE = ROOT / "data" / "raw" / "policy_eval.csv"

SYSTEM_PROMPT = (
    "You are a POLICY ASSISTANT. Answer only from the supplied context. "
    "If the context does not contain the answer, say: "
    "I could not find that information in the policy documents."
)


class PolicyRetriever:
    def __init__(self, policy_dir, overlap=10):
        self.chunks = []
        chunk_size = 40
        step = chunk_size - overlap

        for path in sorted(Path(policy_dir).glob("*.txt")):
            words = path.read_text(encoding="utf-8").split()
            start = 0

            while start < len(words):
                end = min(start + chunk_size, len(words))
                self.chunks.append(
                    {
                        "source": path.name,
                        "text": " ".join(words[start:end]),
                    }
                )
                if end >= len(words):
                    break
                start += step

        self.vectorizer = TfidfVectorizer()
        self.chunk_matrix = self.vectorizer.fit_transform(
            [chunk["text"] for chunk in self.chunks]
        )

    def retrieve(self, query, k=3):
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.chunk_matrix).ravel()
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda index: (-scores[index], index),
        )[:k]

        return [
            {
                "source": self.chunks[index]["source"],
                "score": float(scores[index]),
                "text": self.chunks[index]["text"],
            }
            for index in ranked_indices
        ]


def answer_with(retriever, question):
    results = retriever.retrieve(question, k=3)
    context = "\n".join(
        f"[{item['source']}]\n{item['text']}" for item in results
    )
    user_message = f"CONTEXT:\n{context}\nQUESTION:\n{question}"

    response = mock_llm.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
    )
    return {
        "answer": response.choices[0].message.content,
        "sources": [item["source"] for item in results],
    }


# Default answer() uses the required 10-word overlap.
DEFAULT_RETRIEVER = PolicyRetriever(POLICY_DIR, overlap=10)


def retrieve(query, k=3):
    return DEFAULT_RETRIEVER.retrieve(query, k=k)


def answer(question):
    return answer_with(DEFAULT_RETRIEVER, question)


def evaluate(retriever, evaluation_data, run_name):
    doc_hits = 0
    fact_hits = 0
    fallback_hits = 0
    answerable_count = 0
    unanswerable_count = 0
    broken_questions = []

    for row in evaluation_data.to_dict("records"):
        result = answer_with(retriever, row["question"])
        expected_doc = str(row["expected_doc"]).strip()
        expected_fact = str(row["expected_fact"]).strip()
        is_answerable = bool(expected_doc and expected_fact)

        if is_answerable:
            answerable_count += 1
            if expected_doc in result["sources"]:
                doc_hits += 1
            if expected_fact in result["answer"]:
                fact_hits += 1
            if (
                expected_doc not in result["sources"]
                or expected_fact not in result["answer"]
            ):
                broken_questions.append(
                    {
                        "question": row["question"],
                        "sources": result["sources"],
                        "answer": result["answer"],
                        "expected_doc": expected_doc,
                        "expected_fact": expected_fact,
                    }
                )
        else:
            unanswerable_count += 1
            if result["answer"].startswith("I could not find"):
                fallback_hits += 1

    print(f"\n=== {run_name} ===")
    print(f"Answerable questions with expected document in top 3: {doc_hits}/{answerable_count}")
    print(f"Answerable replies containing expected fact: {fact_hits}/{answerable_count}")
    print(f"Unanswerable questions with fallback answer: {fallback_hits}/{unanswerable_count}")
    return broken_questions


def main():
    print("=== CHUNK COUNTS WITH 10-WORD OVERLAP ===")
    counts = pd.Series(
        [chunk["source"] for chunk in DEFAULT_RETRIEVER.chunks]
    ).value_counts().sort_index()
    print(counts.to_string())
    print(f"Total chunks: {len(DEFAULT_RETRIEVER.chunks)}")

    print("\nTop sources for 'refund policy late delivery':")
    for result in retrieve("refund policy late delivery", k=3):
        print(f"{result['source']} ({result['score']:.3f})")

    evaluation_data = pd.read_csv(EVAL_FILE, keep_default_na=False)
    evaluate(DEFAULT_RETRIEVER, evaluation_data, "10-WORD OVERLAP")

    zero_overlap_retriever = PolicyRetriever(POLICY_DIR, overlap=0)
    broken = evaluate(
        zero_overlap_retriever,
        evaluation_data,
        "ZERO OVERLAP",
    )
    if broken:
        print("\nExample question affected by zero overlap:")
        print(broken[0])


if __name__ == "__main__":
    main()