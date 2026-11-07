# db_pipeline_origin_search

This folder contains the N-mode-only LangGraph GraphRAG application. User questions use Neo4j keyword and vector candidate search with RRF, followed by `interpret -> retrieve -> answer -> finish`. Benefit conditions, limits, and PDF Evidence are read from Neo4j. The question path does not query PostgreSQL benefit tables or use a PostgreSQL fallback. PostgreSQL remains in use for ingestion workflows and `app_log` persistence.

## Run locally

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/card_benefit/payment_card/db_pipeline_origin_search/streamlit_app.py --server.address 127.0.0.1
```

## Environment

| Variable | Purpose |
|---|---|
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` | Neo4j connection |
| `NEO4J_DATABASE`, `NEO4J_TRUSTED_CA_FILE` | Optional Neo4j settings |
| `OPENAI_API_KEY` | LLM and query embedding calls |
| `CARD_SEARCH_MODEL` | Optional LLM model; default is `DEFAULT_MODEL` in code |
| `CARD_SEARCH_LOG_LEVEL` | Card GraphRAG logging level |
| `DB_QUERY_LOG` | Shared database query logging |

There is no search mode selector or A/B/C runtime path; the app always uses the N-mode Neo4j pipeline.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest src/card_benefit/payment_card/tests
```

Live Neo4j tests require their integration environment and use read-only query sessions.
