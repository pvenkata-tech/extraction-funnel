"""
Stage 2 (cheap filter) for PDF: a keyword/boolean gate that discards irrelevant
documents before any LLM call. This single stage is what keeps LLM spend from
scaling with raw document volume instead of with the narrow relevant slice.
"""
from opensearchpy import OpenSearch

from common.config import settings

INDEX_NAME = "clinical_notes"

# Trigger vocabulary for the cohort question in DIVE 2: "cancer diagnosis" + smoking status.
# In production this comes from a domain ontology (ICD-10 codes, SNOMED), not a hardcoded list.
TRIGGER_TERMS = [
    "cancer", "carcinoma", "oncology", "neoplasm", "tumor", "malignant", "malignancy",
    "smoking", "smoker", "tobacco", "non-smoker", "nonsmoker",
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
    """Returns True if the document contains ANY trigger term — the cheap gate before chunking/LLM."""
    query = {"query": {"bool": {
        "must": [{"term": {"file_id": file_id}}],
        "filter": [{"match": {"text": {"query": " ".join(TRIGGER_TERMS), "operator": "or"}}}],
    }}}
    result = _client().search(index=INDEX_NAME, body=query)
    return result["hits"]["total"]["value"] > 0
