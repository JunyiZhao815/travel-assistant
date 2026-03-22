"""轻量向量检索存储（TF-IDF + 余弦相似度）"""

from __future__ import annotations

import math
from collections import Counter
from typing import Callable


class VectorStore:
    """基于稀疏向量的本地检索器，不依赖外部向量数据库。"""

    def __init__(self, items: list[dict], tokenize: Callable[[str], list[str]]):
        self.items = items
        self.tokenize = tokenize
        self.idf: dict[str, float] = {}
        self.doc_vectors: list[dict[str, float]] = []
        self._build()

    def search(self, query: str, top_k: int = 3) -> list[dict[str, float]]:
        query_vector = self.embed(query)
        if not query_vector:
            return []

        scores: list[dict[str, float]] = []
        for idx, doc_vector in enumerate(self.doc_vectors):
            sim = self.cosine_similarity(query_vector, doc_vector)
            if sim <= 0:
                continue
            scores.append({"index": idx, "vector_score": round(sim, 6)})

        scores.sort(key=lambda x: x["vector_score"], reverse=True)
        return scores[: max(1, top_k)]

    def embed(self, text: str) -> dict[str, float]:
        tokens = self.tokenize(text)
        if not tokens:
            return {}
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        for token, cnt in tf.items():
            idf = self.idf.get(token)
            if idf is None:
                continue
            vec[token] = float(cnt) * idf
        return self._normalize(vec)

    def cosine_similarity(self, a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        if len(a) > len(b):
            a, b = b, a
        dot = 0.0
        for token, value in a.items():
            dot += value * b.get(token, 0.0)
        return dot

    def _build(self) -> None:
        tokenized_docs: list[list[str]] = []
        df: Counter[str] = Counter()

        for item in self.items:
            text = " ".join(
                [
                    str(item.get("title", "")),
                    str(item.get("content", "")),
                    " ".join(item.get("tags", [])),
                ]
            )
            tokens = self.tokenize(text)
            tokenized_docs.append(tokens)
            for token in set(tokens):
                df[token] += 1

        doc_count = max(1, len(tokenized_docs))
        self.idf = {
            token: math.log((doc_count + 1) / (freq + 1)) + 1.0
            for token, freq in df.items()
        }

        self.doc_vectors = []
        for tokens in tokenized_docs:
            tf = Counter(tokens)
            vec: dict[str, float] = {}
            for token, cnt in tf.items():
                vec[token] = float(cnt) * self.idf.get(token, 0.0)
            self.doc_vectors.append(self._normalize(vec))

    def _normalize(self, vec: dict[str, float]) -> dict[str, float]:
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm == 0:
            return {}
        return {k: v / norm for k, v in vec.items()}
