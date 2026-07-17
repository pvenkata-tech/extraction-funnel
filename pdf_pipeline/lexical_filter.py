"""
Stage 2 (cheap filter) for PDF: a keyword/boolean gate that discards irrelevant
documents before any LLM call. This single stage is what keeps LLM spend from
scaling with raw document volume instead of with the narrow relevant slice.
"""
from opensearchpy import OpenSearch

from common.config import settings

INDEX_NAME = "vendor_contracts"

# Trigger vocabulary for the cohort question in DIVE 2: contracts with an
# indemnification obligation and a liability-cap question. In production this
# comes from a domain taxonomy (a clause library / contract ontology), not a
# hardcoded list.
TRIGGER_TERMS = [
    "indemnify", "indemnification", "hold harmless",
    "liability", "liable", "limitation of liability", "damages",
]


def _client() -> OpenSearch:
    return OpenSearch(hosts=[settings.opensearch_url], use_ssl=False, verify_certs=False)


def ensure_index():
    client = _client()
    if not client.indices.exists(INDEX_NAME):
        client.indices.create(INDEX_NAME, body={
            "mappings": {"properties": {"file_id": {"type": "keyword"}, "text": {"type": "text"}}}
        })


def index_document(file_id: str, text: str):
    _client().index(index=INDEX_NAME, id=file_id, body={"file_id": file_id, "text": text}, refresh=True)


def matches_trigger_vocabulary(file_id: str) -> bool:
    """Returns True if the document contains ANY trigger term — the cheap gate before chunking/LLM.

    Each term is matched as a phrase, not space-joined into one OR'd query string.
    An earlier version did the latter, which silently ORs in every individual word
    of a multi-word term ("limitation of liability" -> also matches on bare "of") --
    a stopword leak that let an unrelated document (no liability language at all,
    just the word "of" in an unrelated sentence) pass the cheap filter. Phrase
    matching requires the words adjacent and in order, which is what "trigger
    vocabulary" should mean in the first place."""
    should_clauses = [{"match_phrase": {"text": term}} for term in TRIGGER_TERMS]
    query = {"query": {"bool": {
        "must": [{"term": {"file_id": file_id}}],
        "filter": [{"bool": {"should": should_clauses, "minimum_should_match": 1}}],
    }}}
    result = _client().search(index=INDEX_NAME, body=query)
    return result["hits"]["total"]["value"] > 0
