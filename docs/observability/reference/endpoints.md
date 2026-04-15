# Observability Endpoints

## Endpoint Table

| Endpoint | URL | Auth | Access |
|----------|-----|------|--------|
| Grafana | https://grafana.rediacc.io | Admin login | External (HTTPS) |
| OTLP Ingest | https://otlp.rediacc.io | Basic auth (runtime per-region) | External (HTTPS) |
| Pyroscope Ingest | https://profiles.rediacc.io | Basic auth (shared middleware) | External (HTTPS) |
| Prometheus | http://127.0.12.67:9090 | None | Internal only |
| Tempo | http://127.0.12.70:3200 | None | Internal only |
| Loki | http://127.0.12.69:3100 | None | Internal only |
| Pyroscope UI | http://127.0.12.71:4040 | None | Internal only |
| Alloy | http://127.0.12.66:12345 | None | Internal only |

## Auth Token Management

The OTLP and Pyroscope ingest endpoints use basic auth against a Traefik middleware whose user list is a comma-separated `user:hash` set in `observability/secrets.env:OTLP_BASIC_AUTH`. Each region has its own user entry, managed by the rotation tool (`./run.sh rotation rotate otlp-{eu,us,asia}`).

| Component | Credential Source |
|-----------|------------------|
| CLI | Fetched at runtime from the unauthenticated `GET /account/api/v1/telemetry/config` endpoint. Cached in memory for the CLI process lifetime; never persisted to disk. |
| Renet | Received via `REDIACC_OTLP_USER` / `REDIACC_OTLP_PASS` env vars, injected by the CLI when spawning `renet execute` via SSH. Renet never contacts the account server itself. |
| Account Server | Read from the `OTLP_CLIENT_CREDENTIALS` Cloudflare Worker secret on each regional deployment. |

Previously (before renet#51), credentials were baked into the CLI bundle via esbuild `define` and into the renet binary via Go `-ldflags -X`. Both paths leaked the credentials: esbuild `define` inlines the value as a JS string literal, and Go records the full ldflags line in `.go.buildinfo` (recoverable via `go version -m` or `strings`). The runtime-fetch model fixes both leaks and enables per-region credentials that rotate without rebuilds.

**Default-deny and opt-out.** Telemetry is disabled (no requests sent) when any of these is true:
- The account server returns `{otlp: null}` for this region (bench, on-premise, or intentionally disabled).
- The fetch fails (network error, account server unreachable).
- The user has opted out via `REDIACC_TELEMETRY_DISABLED=1` or the CLI is running in CI (any truthy `CI` env var).

When the user opts out via env var, the CLI skips the credential fetch AND injects `REDIACC_TELEMETRY_DISABLED=1` into the remote renet environment via SSH, so the remote renet process also takes its default-deny branch. Setting `REDIACC_TELEMETRY_DISABLED=1` on the workstation produces zero outbound telemetry from any process involved.

Internal endpoints (Prometheus, Tempo, Loki, Pyroscope UI, Alloy) require no authentication. They are bound to loopback addresses and are only accessible from the host machine.
