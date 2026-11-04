# Unresolved extraction review

`card_ai_call.call_resp_json` remains the immutable source for page-level unresolved items. The review queue reads those arrays and joins them to `data/review/unresolved_links.json`; it does not update `card_ai_call` or `card_extr_stg`.

From `src/card_benefit`, inspect a run with:

```powershell
uv run python -m payment_card.db_pipeline.benefit_main review-queue --run-id 20261104_000032
```

The command is read-only and does not require `--apply`. Entries without a matching review reference remain `PENDING_REVIEW`. A reviewed reference is valid only when run, document, page, chunk, ordinal, and unresolved raw text all still match the saved LLM response.

To resolve another entry, add a registry review containing those source identifiers, the verbatim unresolved text, exact target benefit names, reviewer and date, and exact source quotes with their page and chunk. Keep it `PENDING_REVIEW` until the visual document check and target mapping are complete. Use `APPROVED` only for a human-confirmed mapping. Approved evidence quotes are checked against the referenced stored chunk before use. A stale reference or a quote that does not match the chunk is downgraded or rejected at registration time.

The product registration service then appends located evidence through the existing `card_source_evidence` table, links it through the existing evidence-link tables, and appends the reviewed scope note to `card_bnft.bnft_limit_txt`. It does not rewrite the original extraction response or staging JSON. Any targeted pending or rejected review keeps that benefit at `REVIEW`; it is not automatically promoted. Evidence is still stored as `PENDING` under the existing approval workflow.

`card_limit_pool` and `tier_list` are not used. Tier rows are preserved as source text with their reviewed scope note; this path does not calculate discounts or create structured tier pools.
