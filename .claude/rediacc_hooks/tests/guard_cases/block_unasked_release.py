"""The test tables of `block_unasked_release`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.wellknown import IMAGE_REGISTRY

_ASK = "ASKED:2026-01-01T00:00Z"


_PY = "PYTHONPATH=.ci python3 -m"


EDGE_CASES = [
    ("the edge entry", "npm run release:local -- --channel edge"),
    ("the edge entry, dry run", "npm run release:local -- --channel edge --dry-run"),
    ("the entry, channel before the separator", "npm run release:local --channel edge"),
    ("the stable entry", "npm run release:local -- --channel stable --dry-run"),
    (
        "the stable entry with an ASKED",
        "RELEASE_ASKED=%s %s" % (_ASK, "npm run release:local -- --channel stable"),
    ),
    ("the entry by module", "%s rediacc_ci.release.local --channel edge" % _PY),
    ("wrangler deploy on a shared region config", "npx wrangler deploy --config wrangler.eu.toml"),
    ("wrangler deploy on the bench config", "npx wrangler deploy --config wrangler.bench-eu.toml"),
    ("wrangler deploy on a config outside the region set", "npx wrangler deploy"),
    ("wrangler deploy dry run", "npx wrangler deploy --dry-run --outdir /tmp/x"),
    ("wrangler tail reads", "npx wrangler tail www"),
    ("gh release create", "gh release create v1.2.3 --notes x"),
    ("gh release view", "gh release view v1.2.3"),
    ("a v tag push", "git push origin v1.2.3"),
    ("a branch push", "git push origin 1231-9"),
    ("docker push", "docker push %s/renet:1.2.3" % IMAGE_REGISTRY),
    ("docker build", "docker build -t x ."),
    ("the www deploy", "%s rediacc_ci.deploy.deploy_www" % _PY),
    ("a stable CLI promote", "%s rediacc_ci.deploy.promote_r2_to_stable" % _PY),
    ("an eu account deploy", "%s rediacc_ci.deploy.deploy_account --region eu" % _PY),
    (
        "an asia account deploy",
        "%s rediacc_ci.deploy.deploy_account --region asia --target edge" % _PY,
    ),
    ("the bench proxy", "%s rediacc_ci.deploy.deploy_proxy --target bench" % _PY),
    ("a regional proxy", "%s rediacc_ci.deploy.deploy_proxy --target stable --region eu" % _PY),
    ("a raw release step", "%s rediacc_ci.release.create_github_release --version 1.2.3" % _PY),
    ("deploy_bench", "%s rediacc_ci.ops.deploy_bench" % _PY),
    ("pytest naming a module", "python3 -m pytest -k rediacc_ci.deploy.deploy_www"),
    ("prose naming a verb", "echo 'wrangler deploy'"),
    ("a redirect into the release clone", "echo x > .ci/cache/release/abc/a.txt"),
    ("reading the release clone", "cat .ci/cache/release/abc/a.txt"),
]
