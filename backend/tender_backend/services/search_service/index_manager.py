"""OpenSearch index manager — creates and manages indices with ik_max_word Chinese tokenizer."""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

logger = structlog.stdlib.get_logger(__name__)

OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")

# Base analyzer settings with ik_max_word + synonym filter
INDEX_SETTINGS: dict[str, Any] = {
    "settings": {
        "analysis": {
            "filter": {
                "construction_synonym": {
                    "type": "synonym",
                    "synonyms_path": "synonyms.txt",
                    "updateable": True,
                }
            },
            "analyzer": {
                "cn_with_synonym": {
                    "tokenizer": "ik_max_word",
                    "filter": ["lowercase", "construction_synonym"],
                },
                "cn_default": {
                    "tokenizer": "ik_max_word",
                    "filter": ["lowercase"],
                },
            },
        },
        "number_of_shards": 1,
        "number_of_replicas": 0,
    }
}

# Index-specific mappings
SECTION_INDEX_MAPPINGS = {
    "mappings": {
        "properties": {
            "project_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "section_id": {"type": "keyword"},
            "section_code": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "cn_with_synonym"},
            "text": {"type": "text", "analyzer": "cn_with_synonym"},
            "level": {"type": "integer"},
            "page_start": {"type": "integer"},
        }
    }
}

CLAUSE_INDEX_MAPPINGS = {
    "mappings": {
        "properties": {
            "standard_id": {"type": "keyword"},
            "standard_code": {"type": "keyword"},
            "standard_name": {"type": "text", "analyzer": "cn_default"},
            "clause_id": {"type": "keyword"},
            "clause_no": {"type": "keyword"},
            "clause_title": {"type": "text", "analyzer": "cn_with_synonym"},
            "clause_text": {"type": "text", "analyzer": "cn_with_synonym"},
            "summary": {"type": "text", "analyzer": "cn_default"},
            "tags": {"type": "keyword"},
            "specialty": {"type": "keyword"},
            "page_start": {"type": "integer"},
            "page_end": {"type": "integer"},
        }
    }
}

REQUIREMENT_INDEX_MAPPINGS = {
    "mappings": {
        "properties": {
            "project_id": {"type": "keyword"},
            "requirement_id": {"type": "keyword"},
            "category": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "cn_with_synonym"},
            "source_text": {"type": "text", "analyzer": "cn_with_synonym"},
        }
    }
}


class IndexManager:
    def __init__(self, base_url: str = OPENSEARCH_URL) -> None:
        self._url = base_url.rstrip("/")

    async def create_index(self, name: str, body: dict) -> None:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            resp = await client.head(f"{self._url}/{name}")
            if resp.status_code == 200:
                logger.info("index_exists", index=name)
                return
            resp = await client.put(
                f"{self._url}/{name}",
                json=body,
            )
            resp.raise_for_status()
            logger.info("index_created", index=name)

    async def ensure_all_indices(self) -> None:
        """Create all required indices if they don't exist."""
        await self.create_index(
            "section_index",
            {**INDEX_SETTINGS, **SECTION_INDEX_MAPPINGS},
        )
        await self.create_index(
            "clause_index",
            {**INDEX_SETTINGS, **CLAUSE_INDEX_MAPPINGS},
        )
        await self.create_index(
            "requirement_index",
            {**INDEX_SETTINGS, **REQUIREMENT_INDEX_MAPPINGS},
        )

    async def index_document(self, index: str, doc_id: str, body: dict) -> None:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.put(
                f"{self._url}/{index}/_doc/{doc_id}",
                json=body,
            )
            resp.raise_for_status()

    async def bulk_index(self, index: str, docs: list[tuple[str, dict]]) -> int:
        """Bulk index documents. Each item is (doc_id, body)."""
        if not docs:
            return 0
        lines = []
        for doc_id, body in docs:
            lines.append(f'{{"index":{{"_index":"{index}","_id":"{doc_id}"}}}}')
            import json
            lines.append(json.dumps(body, ensure_ascii=False))
        payload = "\n".join(lines) + "\n"
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            resp = await client.post(
                f"{self._url}/_bulk",
                content=payload,
                headers={"Content-Type": "application/x-ndjson"},
            )
            resp.raise_for_status()
        logger.info("bulk_indexed", index=index, count=len(docs))
        return len(docs)

    async def delete_index(self, name: str) -> None:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            await client.delete(f"{self._url}/{name}")
