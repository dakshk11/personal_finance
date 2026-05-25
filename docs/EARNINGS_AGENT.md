# Earnings Agent

Earnings Agent lives at `/ai-advisor` under the **Earnings Agent** tab in FinanceOS Studio. It is an educational research digest for recent company earnings materials. It accepts a ticker or company name, fetches public source material when available, and uses the user's encrypted OpenAI key to create a structured digest.

Earnings Agent does not place trades, assign ratings, create price targets, or give investment advice.

## Source Flow

1. Resolve the query against SEC company ticker metadata, then fall back to known FinanceOS index holdings.
2. Fetch SEC submissions JSON for the resolved CIK.
3. Inspect recent `8-K` and `8-K/A` filings.
4. Parse the complete EDGAR submission text and prioritize `EX-99.1` / `EX-99.2` documents whose descriptions mention earnings releases, financial results, press releases, shareholder letters, or investor presentations.
5. Extract SEC HTML/TXT exhibit text directly. For PDF exhibits, use `pypdf==6.12.0` and keep a warning if parsing fails.
6. Search bounded Motley Fool earnings transcript pages for a ticker/company match.
7. Send available source excerpts to the LLM and save the structured digest.

## Storage Behavior

Each saved run is scoped to the current FinanceOS user and stores:

- query, ticker, company name, and CIK
- model name
- SEC source metadata and short excerpt
- transcript source metadata and short excerpt
- prompt text, response text, parsed digest, usage metadata, warnings, and timestamps

Full Motley Fool transcript text is not persisted or exported. It is used transiently for the digest, then only source metadata and short provenance excerpts are stored.

## API Contract

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/earnings-agent/run` | Resolve the query, fetch sources, generate an LLM digest, save the run, and return the full result. |
| `GET` | `/earnings-agent/runs` | Return recent saved run summaries for the current user. |
| `GET` | `/earnings-agent/runs/{id}` | Return one saved run if it belongs to the current user. |

Run request:

```json
{
  "query": "AAPL",
  "model": "gpt-5.4"
}
```

Digest sections:

- executive summary
- top takeaways
- financial metrics
- management tone
- risks
- deep-dive questions
- source notes

## UI Behavior

The tab shows:

- ticker/company input
- model selector for `gpt-5.5`, `gpt-5.4`, and `gpt-5.4-mini`
- key-required state when no OpenAI key is saved
- source cards for SEC EDGAR and transcript coverage
- digest cards for summary, takeaways, metrics, tone, risks, and next questions
- warnings for missing or partial sources
- saved run history

## Test Notes

Backend tests mock network and OpenAI calls and cover:

- ticker and company-name resolution
- SEC `EX-99.1` / `EX-99.2` selection
- HTML/TXT and PDF extraction paths
- missing Motley Fool transcript warning
- missing OpenAI key error
- LLM JSON parsing and markdown fallback
- per-user saved run access controls
- no full third-party transcript persistence
