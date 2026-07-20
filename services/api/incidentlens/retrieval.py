from __future__ import annotations

from hashlib import blake2b
from math import sqrt
from re import findall

EMBEDDING_DIMENSIONS = 32


def deterministic_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Build a stable local embedding for offline demos and repeatable tests."""
    values = [0.0] * dimensions
    for token in findall(r"[\w.-]+", text.casefold()):
        digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        values[index] += sign
    norm = sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 8) for value in values]
