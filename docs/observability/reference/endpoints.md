# Observability Endpoints

## Endpoint Table

| Endpoint | URL | Auth | Access |
|----------|-----|------|--------|
| Grafana | https://grafana.rediacc.io | Admin login | External (HTTPS) |
| OTLP Ingest | https://otlp.rediacc.io | Basic auth (compile-time injected) | External (HTTPS) |
| Pyroscope Ingest | https://profiles.rediacc.io | Basic auth (same credentials) | External (HTTPS) |
| Prometheus | http://127.0.12.67:9090 | None | Internal only |
| Tempo | http://127.0.12.70:3200 | None | Internal only |
| Loki | http://127.0.12.69:3100 | None | Internal only |
| Pyroscope UI | http://127.0.12.71:4040 | None | Internal only |
| Alloy | http://127.0.12.66:12345 | None | Internal only |

## Auth Token Management

The OTLP and Pyroscope ingest endpoints use basic auth. The credentials come from the GitHub secret `OTLP_AUTH_TOKEN` and are injected at compile time:

| Component | Injection Method |
|-----------|-----------------|
| CLI | esbuild `define` — token is baked into the JS bundle |
| Renet | Go `ldflags` — token is set at link time |
| Account Server | Environment variable `OTEL_AUTH_TOKEN` |

Internal endpoints (Prometheus, Tempo, Loki, Pyroscope UI, Alloy) require no authentication. They are bound to loopback addresses and are only accessible from the host machine.
