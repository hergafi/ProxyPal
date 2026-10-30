# Contributing to ProxyPal

Thank you for reading this. مساهمتك محل ترحيب.

ProxyPal is a local-first AI chat gateway: the user brings their own provider API keys and the
app rotates between keys and providers when one is exhausted, rate-limited or broken. Everything
runs on `127.0.0.1`; there is no hosted backend, no accounts, and no telemetry. Please keep it
that way.

## What this project optimises for

1. **Key secrecy.** Keys never appear in the UI, logs, responses, screenshots, tests or commits.
   Masking is `••••` + the last 4 characters (`api_pool.py`), and mutation responses are never
   rendered because they can echo a submitted secret.
2. **Honest failover.** A partial streamed answer is kept and marked incomplete; it is never
   replayed or concatenated. Switching is reported per response, not per counter diff.
3. **Provider-permitted usage.** Rotating keys means spreading your own quota across your own
   accounts. Features that exist to bypass provider limits will be rejected.
4. **Local budgets are local.** Token/request budgets are app-local counters, not the provider's
   real balance. Do not describe them as balance.

## Repository map

| Path | What lives there |
| --- | --- |
| `gateway.py` | FastAPI app: routing, failover, streaming, provider/model/key endpoints, `/health`, `/status`. |
| `api_pool.py` | The key pool: SHA-256 key identity, sticky/round_robin/least_used routing, reserve/observe/finish accounting, cooldowns, model health. |
| `backend/tests/test_api_pool.py` | Engine tests against a mocked transport — no real keys, no network. |
| `backend/tests/test_proxypal_ui.py` | Playwright UI tests (Edge headless) against a mocked gateway. |
| `modern-workspace/src/App.jsx` | The whole React UI: chat, settings, provider management, mascot, TTS. |
| `modern-workspace/src/i18n.js` | Flat AR/EN/FR dictionaries — every locale must carry every key. |
| `modern-workspace/src/index.css` | Styles, themes and RTL handling. |

## Environment

- Python 3.11+ and Node 20.19+ (or 22.12+).
- `pip install -r requirements-dev.txt` (pulls in `requirements.txt`, pytest, Playwright).
- `cd modern-workspace && npm install`.
- Copy `.env.example` to `.env`. Never commit `.env`, `gateway_config.json`, `gateway.db` or `logs/`.
- For a fresh clone, `gateway_config.json` does not exist; the gateway starts with an empty
  provider list. Use `gateway_config.example.json` as the shape reference, and prefer adding keys
  through the UI.

## Commands

```bash
python gateway.py                              # http://127.0.0.1:8790
cd modern-workspace && npm run dev             # http://localhost:5173
cd modern-workspace && npm run lint && npm run build
python -m pytest backend/tests/test_api_pool.py -q
python backend/tests/test_proxypal_ui.py       # needs Playwright + a dev server on 5173
docker compose up --build                      # http://127.0.0.1:8790/app/
```

UI tests run headless and mock every provider call, so they never consume a real key. To point
them at a running build instead of the dev server:
`PROXYPAL_UI_URL=http://127.0.0.1:8790/app/` — note that live run needs the gateway's
`ALLOWED_ORIGINS` to include the UI origin, otherwise `/status` is blocked by CORS.

## Making a change

1. Branch from `main`, one concern per branch.
2. Add or adjust a test for behaviour you changed. Engine tests go in `test_api_pool.py`; visible
   flows go in `test_proxypal_ui.py`.
3. Run lint, build and both suites. Report the real counts — do not claim something passes that
   you did not run.
4. Keep user-visible strings in `i18n.js` for **all three** locales, with `{placeholders}` named
   identically in each.
5. Respect `.editorconfig`. Python is 4 spaces, everything else 2; comments only where the *why*
   is non-obvious.

### Version bumps

`GATEWAY_VERSION` in `gateway.py`, `GATEWAY_VERSION` in `modern-workspace/src/App.jsx`, and the
`-ge 6` health checks in `run.bat` must stay identical. The UI compares them and warns when the
gateway runs a stale build.

### Adding a provider preset

Three places, all required:

- `gateway.py` → `PROVIDER_URLS` (OpenAI-compatible base URL) and optionally `PROVIDER_MODELS`.
- `modern-workspace/src/App.jsx` → `PROVIDER_CATALOG` (id, display name, brand tone, glyph).
- `modern-workspace/src/App.jsx` → `PROVIDER_GLYPHS` if you introduced a new glyph.

Non-chat model ids (embedding, TTS, moderation, image, etc.) are filtered by
`is_chat_model()`; a new provider whose catalog mixes them should be verified against the
existing filter tests before adding patterns.

## Pull requests

Describe the user-visible problem, not only the code change. Include screenshots for UI work
(store them under `docs/screenshots/`, never in `logs/` which is git-ignored) and the exact test
commands you ran with their output. If a change touches failover, streaming, key handling or
CORS, say so explicitly in the first line.

## Out of scope

Hosted multi-user deployments, account systems, proxying keys through a third-party server,
scraping free quota, or anything that widens `ALLOWED_ORIGINS` by default. Security findings
belong in a private report — see [SECURITY.md](SECURITY.md).
