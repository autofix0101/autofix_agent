"""
Shared data models for the Repo Analyzer Agent.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class CodeChunk:
    chunk_key: str
    symbol_name: str | None
    chunk_type: str          # function | class | interface | type | module | block
    start_line: int
    end_line: int
    language: str
    content: str
    embedding: list[float] | None = field(default=None, repr=False)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "chunk_key": self.chunk_key,
            "symbol_name": self.symbol_name,
            "chunk_type": self.chunk_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "content": self.content,
            "content_hash": self.content_hash,
            "embedding": self.embedding,
        }
