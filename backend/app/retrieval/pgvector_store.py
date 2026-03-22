"""pgvector 向量存储与检索"""

from __future__ import annotations

import math
import re
from typing import Any

try:
    import psycopg
    from pgvector.psycopg import register_vector
except Exception:  # pragma: no cover
    psycopg = None
    register_vector = None


class PgVectorStore:
    """基于 PostgreSQL + pgvector 的知识向量检索。"""

    def __init__(self, dsn: str, table_name: str = "rag_knowledge_vectors", dim: int = 256):
        self.dsn = dsn
        self.table_name = table_name
        self.dim = max(16, dim)
        self.available = False
        self._init_db()

    def sync_items(self, items: list[dict[str, Any]]) -> None:
        if not self.available:
            return
        if not items:
            return

        sql = f"""
            INSERT INTO {self.table_name}
                (id, title, content, tags, source, version, timestamp, confidence, embedding)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id)
            DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                tags = EXCLUDED.tags,
                source = EXCLUDED.source,
                version = EXCLUDED.version,
                timestamp = EXCLUDED.timestamp,
                confidence = EXCLUDED.confidence,
                embedding = EXCLUDED.embedding,
                updated_at = NOW()
        """

        rows: list[tuple[Any, ...]] = []
        for idx, item in enumerate(items):
            item_id = str(item.get("id") or f"knowledge_{idx}")
            text = self._build_text(item)
            embedding = self._embed(text)
            rows.append(
                (
                    item_id,
                    str(item.get("title", "")),
                    str(item.get("content", "")),
                    list(item.get("tags", [])),
                    str(item.get("source", "unknown")),
                    str(item.get("version", "v1")),
                    str(item.get("timestamp", "")),
                    float(item.get("confidence", 0.6)),
                    embedding,
                )
            )

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not self.available:
            return []
        query = (query or "").strip()
        if not query:
            return []

        embedding = self._embed(query)
        sql = f"""
            SELECT id, GREATEST(0, 1 - (embedding <=> %s)) AS vector_score
            FROM {self.table_name}
            ORDER BY embedding <=> %s
            LIMIT %s
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (embedding, embedding, max(1, top_k)))
                rows = cur.fetchall()

        return [{"id": row[0], "vector_score": float(row[1])} for row in rows]

    def _init_db(self) -> None:
        if psycopg is None or register_vector is None:
            print("⚠️  未安装 psycopg/pgvector 依赖,将回退本地向量检索")
            self.available = False
            return
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {self.table_name} (
                            id TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            content TEXT NOT NULL,
                            tags TEXT[] DEFAULT '{{}}',
                            source TEXT DEFAULT 'unknown',
                            version TEXT DEFAULT 'v1',
                            timestamp TEXT DEFAULT '',
                            confidence REAL DEFAULT 0.6,
                            embedding VECTOR({self.dim}) NOT NULL,
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        )
                        """
                    )
                conn.commit()
            self.available = True
        except Exception as e:
            print(f"⚠️  pgvector 初始化失败,将回退本地向量检索: {str(e)}")
            self.available = False

    def _connect(self):
        if psycopg is None or register_vector is None:
            raise RuntimeError("psycopg/pgvector not installed")
        conn = psycopg.connect(self.dsn, autocommit=False)
        register_vector(conn)
        return conn

    def _build_text(self, item: dict[str, Any]) -> str:
        return " ".join(
            [
                str(item.get("title", "")),
                str(item.get("content", "")),
                " ".join(item.get("tags", [])),
            ]
        ).strip()

    def _embed(self, text: str) -> list[float]:
        # 轻量哈希嵌入（MVP），可后续替换为外部 embedding 模型
        tokens = self._tokenize(text)
        if not tokens:
            return [0.0] * self.dim

        vec = [0.0] * self.dim
        for tok in tokens:
            h = hash(tok)
            idx = h % self.dim
            sign = 1.0 if ((h >> 1) & 1) == 0 else -1.0
            vec[idx] += sign

        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        return re.findall(r"[\u4e00-\u9fff]{1,}|[a-z0-9_]+", text)
