# Security policy — سياسة الأمان

ProxyPal is a local-first gateway: your API keys are stored on your machine in
`gateway_config.json` and never leave it except as the `Authorization` header toward the
provider you configured. هذه الأداة محلية أولاً: مفاتيحك تبقى على جهازك ولا تُرسل إلا إلى المزود الذي اخترته.

## Reported problems

Please do **not** open a public issue for anything that exposes keys, bypasses the loopback
default, or allows an unrelated origin to reach the gateway. Mail the maintainer privately or
use GitHub's *Report a vulnerability* form, and include the version shown by `GET /health`.

## What is already covered

| Concern | Current behaviour |
| --- | --- |
| Key display | Masked to the last 4 characters in the UI and `/pool/*` responses; mutation bodies are never rendered because they can echo a submitted secret. |
| Key logging | Only SHA-256 key identities and provider names reach logs. |
| Network exposure | `GATEWAY_HOST` defaults to `127.0.0.1`; the Docker compose file publishes `127.0.0.1:8790` only. |
| Cross-origin | `ALLOWED_ORIGINS` is an explicit list; requests from other origins are rejected. |
| Optional auth | Set `GATEWAY_TOKEN` to require `Authorization: Bearer <token>` on every API call. |
| Workspace folder reading | Confined to `WORKSPACE_ROOT` when set; binary, secret and oversized files are skipped, and the mount is read-only in Docker. |
| Model code preview | Rendered inside a sandboxed `iframe` with `sandbox="allow-scripts"` and no same-origin access. |
| Secrets in git | `.env`, `gateway_config.json`, `*.db` and `logs/` are ignored by git and excluded by `.dockerignore`. |

## If you publish this for others

The defaults assume a single trusted local user. Before exposing the gateway beyond loopback you
must set `GATEWAY_TOKEN`, keep `ALLOWED_ORIGINS` minimal, and put authentication in front of it.
The gateway has no user accounts and no per-user key isolation — do not share one instance between
untrusted people. Multi-key rotation is meant to spread your own quota across your own accounts;
keep it inside each provider's permitted usage.

## Rotation and quota honesty

Local budgets are app-local counters, not the provider's real balance. The gateway respects
`Retry-After` and `x-ratelimit-*` headers, cools down keys after 5xx, freezes keys rejected with
401/403 or 402, and skips models answered with 404 instead of burning the remaining keys.
