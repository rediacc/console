# Elite

The Rediacc account server with a bundled RustFS object store, as a renet repo. Traefik terminates TLS for `ELITE_DOMAIN` (the web UI and API) and `ELITE_STORE_DOMAIN` (presigned backup URLs).

## Deploy

1. Copy `secrets.env.example` to `secrets.env` and fill it in.
2. Optionally place the image tarball at `images/server.tar`; `up()` loads it when the tag is absent.
3. `rdc repo up <repo>` runs `up()`. It refuses and names the first missing variable.

`health()` checks that `https://$ELITE_DOMAIN/health` answers.

## Data

`data/web` holds the account database and delegation cert; `data/rustfs` holds every config blob and backup object. Back both up with the repo.

The web service's environment tracks `private/elite/docker-compose.yml`; `.ci/rediacc_ci/tests/test_onprem_template_parity.py` fails when they drift.
