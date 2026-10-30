# legacy/

Superseded code kept for reference. Nothing here is imported by `gateway.py`, `api_pool.py`, the
React app, the Docker image or the test suites — they are archived, not supported.

| Item | What it was | Why it stayed |
| --- | --- | --- |
| `api_checker.html` | Single-file provider checker from the very first prototype, before the FastAPI gateway existed. | Useful to eyeball a provider by hand; its UI promised JWT and rate limiting that the real gateway implements differently. |
| `backend-core/` | First backend scaffolding: `.env` config loader, SQLite helper, rotating logger, API-key/rate-limit decorators. | Replaced by the single-file `gateway.py` plus `api_pool.py`; the actual token auth lives in `gateway.py` (`GATEWAY_TOKEN`) and per-key budgets in `api_pool.py`. |

Do not document these as features, and do not import from them. If you need something here,
port it into `gateway.py`/`api_pool.py` with tests and delete the original.
