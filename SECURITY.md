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
| API auth | Every API call needs `Authorization: Bearer <token>` (compared with `hmac.compare_digest`); only `/health` and the app shell are public. The token is a 32-byte random value generated on first start into `data/.gateway_token` (`0600` on POSIX, `GATEWAY_TOKEN`/`GATEWAY_TOKEN_FILE` override it). |
| Workspace folder reading | Confined to `WORKSPACE_ROOT` when set; home directory, drive/filesystem roots and system directories are refused; SSH keys, certificates, `.env`, `credentials*`, `*token*`, `*password*`, key stores and private-key contents are skipped; binary and oversized files are skipped; the mount is read-only in Docker. |
| Workspace writes | Refused unless `WORKSPACE_ROOT` is configured explicitly, and always confined to it. |
| Custom provider URLs | `https://` is required for remote hosts (`http://` for localhost only); embedded credentials and link-local/cloud-metadata addresses (`169.254.0.0/16`, `fd00:ec2::254`, also via DNS) are rejected. |
| File permissions | `gateway_config.json`, `gateway.db` and `data/.gateway_token` are set to `0600` on Linux/macOS; the Docker image runs as non-root UID 10001. |
| Model code preview | Rendered inside a sandboxed `iframe` with `sandbox="allow-scripts"` and no same-origin access. |
| Secrets in git | `.env`, `data/` (except `.gitkeep`), `gateway_config.json`, `*.db` and `logs/` are ignored by git and excluded by `.dockerignore`. |

## If you publish this for others

The defaults assume a single trusted local user. The token guard is on by default, but before
exposing the gateway beyond loopback you must also set your own `GATEWAY_TOKEN`, keep
`ALLOWED_ORIGINS` minimal, terminate TLS in front of it, and add real authentication.
The gateway has no user accounts and no per-user key isolation — do not share one instance between
untrusted people. Multi-key rotation is meant to spread your own quota across your own accounts;
keep it inside each provider's permitted usage.

## Rotation and quota honesty

Local budgets are app-local counters, not the provider's real balance. The gateway respects
`Retry-After` and `x-ratelimit-*` headers, cools down keys after 5xx, freezes keys rejected with
401/403 or 402, and skips models answered with 404 instead of burning the remaining keys.
