#!/usr/bin/env python3
"""Control harness for block_unasked_release: the release entry only when asked, no raw publish verb, no hand write into the release clone.

BOTH DIRECTIONS, through the real dispatcher. Every refusal has an admission twin that differs by one planted fact: `--dry-run` after `--` against before it, a proven `RELEASE_ASKED` minute against an unproven, malformed or missing one, `--target bench` against another target, `--region eu` against another region, a branch push against a `v*` tag push, a build against a push, a read of the release clone against a write.

THE ASKED PROOF is driven against a planted transcript holding one AskUserQuestion answered at 00:00:30Z: `ASKED:2026-01-01T00:00Z` is inside the 300 s window and `ASKED:2026-01-01T00:10Z` is not, and the same proven minute with no transcript in the payload is refused.

THE MUTANTS ARE PROVEN HERE TOO. The guard's DEFECT and every one of its MUTANTS are planted in a copy run through the same payloads, and each must flip its named refusal to allowed; a suite whose green did not depend on that line would pass the copy too.

THE SHAPE IS PRINTED: the number of cases, how many were refused and admitted, and every control that fired, so a collapse to zero is visible rather than green.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import _hookpath

from rediacc_hooks import guards

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_unasked_release"
GUARD = HERE / ("%s.py" % STEM)
G = guards.load(STEM)

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", REPO / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-unasked-release-")


def transcript(answer_ts):
    """A lead transcript holding one AskUserQuestion and its answer at `answer_ts`."""
    path = pathlib.Path(tempfile.mkdtemp(prefix="transcript-", dir=RUN_TMP)) / "lead.jsonl"
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-01-01T00:00:10Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "AskUserQuestion", "id": "toolu_fixture_ask"}
                ]
            },
        },
        {
            "type": "user",
            "timestamp": answer_ts,
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_fixture_ask", "content": "a"}
                ]
            },
        },
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return str(path)


TR = transcript("2026-01-01T00:00:30Z")
ASK = "RELEASE_ASKED=ASKED:2026-01-01T00:00Z"
ASK_ELSEWHERE = "RELEASE_ASKED=ASKED:2026-01-01T00:10Z"
ENTRY = "npm run release:local -- --channel edge"
PY = "PYTHONPATH=.ci python3 -m"
CLONE = ".ci/cache/release/abc"
BWS = "%s rediacc_ci.core.bws_env exec --profile deploy-workers --" % PY
DEVBOX = "./run.sh devbox exec --"
WWW = "%s rediacc_ci.deploy.deploy_www" % PY
ACCT_SECRETS = "rediacc_ci.deploy.set_account_worker_secrets"

B, A = True, False

# (name, command, transcript, expect_blocked, stderr needle; "!x" means x must be absent)
CASES = [
    # ------------------------------------------------------------- the entry: edge free, stable refused outright
    ("entry: edge, no ASKED", ENTRY, None, A, "!BLOCKED"),
    ("entry: edge, dry run", ENTRY + " --dry-run", None, A, ""),
    ("entry: edge, --channel=edge", "npm run release:local -- --channel=edge", None, A, ""),
    ("entry: edge by module", "%s rediacc_ci.release.local --channel edge" % PY, None, A, ""),
    ("entry: edge inside the devbox", "%s %s" % (DEVBOX, ENTRY), None, A, ""),
    ("entry: edge under bws_env", "%s %s" % (BWS, ENTRY), None, A, ""),
    ("entry: edge inside bash -c", "bash -c '%s'" % ENTRY, None, A, ""),
    (
        "entry: edge, npm --prefix spelling",
        "npm --prefix . run release:local -- --channel edge",
        None,
        A,
        "",
    ),
    (
        "entry: channel before the separator",
        "npm run release:local --channel edge",
        None,
        B,
        "names no --channel edge",
    ),
    ("entry: no channel", "npm run release:local", None, B, "names no --channel edge"),
    ("entry: no channel, dry run", "npm run release:local -- --dry-run", None, B, "no --channel"),
    (
        "entry: stable channel",
        "npm run release:local -- --channel stable",
        None,
        B,
        "promoted through CI/CD only",
    ),
    (
        "entry: stable channel, dry run",
        "npm run release:local -- --channel stable --dry-run",
        None,
        B,
        "promoted through CI/CD only",
    ),
    (
        "entry: stable channel with a proven ASKED",
        "%s npm run release:local -- --channel stable" % ASK,
        TR,
        B,
        "RELEASE_ASKED does not admit it",
    ),
    (
        "entry: stable by module with a proven ASKED",
        "%s %s rediacc_ci.release.local --channel stable" % (ASK, PY),
        TR,
        B,
        "promoted through CI/CD only",
    ),
    # ------------------------------------------------------------- the ASKED proof, on a stable deploy
    ("stable: proven ASKED", "%s %s" % (ASK, WWW), TR, A, "admitted by RELEASE_ASKED"),
    ("stable: no ASKED", WWW, None, B, "carries no RELEASE_ASKED"),
    (
        "stable: ASKED with no transcript",
        "%s %s" % (ASK, WWW),
        None,
        B,
        "matches no AskUserQuestion",
    ),
    (
        "stable: ASKED matching no answer",
        "%s %s" % (ASK_ELSEWHERE, WWW),
        TR,
        B,
        "matches no AskUserQuestion",
    ),
    (
        "stable: ASKED without the Z",
        "RELEASE_ASKED=ASKED:2026-01-01T00:00 %s" % WWW,
        TR,
        B,
        "is not ASKED",
    ),
    (
        "stable: ASKED as prose, not the variable",
        "%s # ASKED:2026-01-01T00:00Z" % WWW,
        TR,
        B,
        "carries no RELEASE_ASKED",
    ),
    ("stable: ASKED exported first", "export %s; %s" % (ASK, WWW), TR, A, "admitted"),
    (
        "stable: ASKED carried through the devbox",
        "%s %s %s" % (ASK, DEVBOX, WWW),
        TR,
        A,
        "admitted",
    ),
    # ------------------------------------------------------------- wrangler: stable config asked, edge config refused for its module
    ("wrangler deploy", "npx wrangler deploy", None, B, "on the stable config wrangler.toml"),
    (
        "wrangler deploy on a stable config, no ASKED",
        "npx wrangler deploy --config wrangler.eu.toml",
        None,
        B,
        "carries no RELEASE_ASKED",
    ),
    (
        "wrangler deploy on a stable config, proven ASKED",
        "%s npx wrangler deploy --config wrangler.eu.toml" % ASK,
        TR,
        A,
        "admitted by RELEASE_ASKED",
    ),
    ("wrangler rollback on stable", "npx wrangler rollback -c wrangler.us.toml", None, B, "stable"),
    ("wrangler publish", "npx wrangler publish", None, B, "wrangler publish"),
    ("wrangler versions deploy", "npx wrangler versions deploy", None, B, "versions deploy"),
    (
        "wrangler deploy on an edge config",
        "npx wrangler --config wrangler.edge.toml deploy",
        None,
        B,
        "deploys through its module",
    ),
    (
        "wrangler deploy on an edge config, proven ASKED",
        "%s npx wrangler deploy -c wrangler.edge-eu.toml" % ASK,
        TR,
        B,
        "deploys through its module",
    ),
    (
        "wrangler deploy on the bench config",
        "npx wrangler deploy --config=wrangler.bench.toml",
        None,
        B,
        "deploys through its module",
    ),
    (
        "wrangler deploy by path under cd",
        "cd workers/www && ./node_modules/.bin/wrangler deploy",
        None,
        B,
        "wrangler deploy",
    ),
    (
        "wrangler deploy under bws_env in the devbox",
        "%s env %s bash -c 'cd workers/www && npx wrangler deploy'" % (DEVBOX, BWS),
        None,
        B,
        "wrangler deploy",
    ),
    (
        "wrangler deploy through docker exec",
        "docker exec -u vscode box bash -lc 'npx wrangler deploy'",
        None,
        B,
        "wrangler deploy",
    ),
    (
        "npm run deploy of mta-sts is a wrangler deploy",
        "npm --prefix workers/mta-sts run deploy",
        None,
        B,
        "wrangler deploy",
    ),
    (
        "npm run deploy of mta-sts after cd",
        "cd workers/mta-sts && npm run deploy",
        None,
        B,
        "wrangler deploy",
    ),
    ("wrangler deploy dry run", "npx wrangler deploy --dry-run --outdir /tmp/x", None, A, ""),
    ("the proxy dry-run npm script", "npm --prefix workers/proxy run dry-run", None, A, ""),
    ("wrangler tail", "npx wrangler tail edge-rediacc-www", None, A, ""),
    ("wrangler d1 migrations list", "npx wrangler d1 migrations list DB --remote", None, A, ""),
    ("wrangler deployments list", "npx wrangler deployments list", None, A, ""),
    # ------------------------------------------------------------- gh release
    ("gh release create", "gh release create v1.2.3 --notes x", None, B, "gh release create"),
    ("gh release upload", "gh release upload v1.2.3 a.tgz", None, B, "gh release upload"),
    ("gh release edit", "gh release edit v1.2.3 --draft=false", None, B, "gh release edit"),
    ("gh release delete", "gh release delete v1.2.3 --yes", None, B, "gh release delete"),
    (
        "gh release create with -R first",
        "gh release -R rediacc/console create v1.2.3",
        None,
        B,
        "gh release create",
    ),
    ("gh release view", "gh release view v1.2.3", None, A, ""),
    ("gh release list", "gh release list", None, A, ""),
    ("gh workflow run", "gh workflow run ci.yml", None, A, ""),
    # ------------------------------------------------------------- tag pushes
    ("push a v tag", "git push origin v1.2.3", None, B, "release tag `v1.2.3`"),
    ("push refs/tags/v", "git push origin refs/tags/v1.2.3", None, B, "release tag"),
    (
        "force-push a v tag by refspec",
        "git push origin +v1.2.3:refs/tags/v1.2.3",
        None,
        B,
        "release tag",
    ),
    ("delete a v tag by refspec", "git push origin :refs/tags/v1.2.3", None, B, "release tag"),
    ("delete a v tag by --delete", "git push --delete origin v1.2.3", None, B, "release tag"),
    ("push every tag", "git push --tags origin", None, B, "--tags"),
    ("push a mirror", "git push --mirror origin", None, B, "--mirror"),
    ("push a submodule v tag", "git -C private/renet push origin v0.9.1", None, B, "release tag"),
    ("push a v tag pattern", "git push origin 'refs/tags/v*'", None, B, "release tag"),
    ("push the branch", "git push origin 1023-1", None, A, ""),
    (
        "push a branch named v-ish under refs/heads",
        "git push origin HEAD:refs/heads/vendor-sync",
        None,
        A,
        "",
    ),
    ("dry-run a v tag push", "git push --dry-run origin v1.2.3", None, A, ""),
    ("a local tag", "git tag v1.2.3", None, A, ""),
    ("fetch tags", "git fetch --tags origin", None, A, ""),
    # ------------------------------------------------------------- docker
    ("docker push", "docker push ghcr.io/rediacc/renet:1.2.3", None, B, "docker push"),
    (
        "docker image push",
        "docker image push ghcr.io/rediacc/rdc:1.2.3",
        None,
        B,
        "docker image push",
    ),
    (
        "docker manifest push",
        "docker manifest push ghcr.io/rediacc/rdc:1.2.3",
        None,
        B,
        "docker manifest push",
    ),
    ("sudo docker push", "sudo docker push ghcr.io/rediacc/rdc:1.2.3", None, B, "docker push"),
    ("buildx build --push", "docker buildx build --push -t ghcr.io/x:1 .", None, B, "--push"),
    ("docker build --push", "docker build --push -t ghcr.io/x:1 .", None, B, "--push"),
    (
        "buildx registry output",
        "docker buildx build --output type=registry -t ghcr.io/x:1 .",
        None,
        B,
        "--push",
    ),
    (
        "buildx imagetools create",
        "docker buildx imagetools create -t ghcr.io/x:latest ghcr.io/x:1",
        None,
        B,
        "imagetools create",
    ),
    ("docker build", "docker build -t x .", None, A, ""),
    ("buildx build --load", "docker buildx build --load -t x .", None, A, ""),
    ("docker pull", "docker pull ghcr.io/rediacc/renet:1.2.3", None, A, ""),
    ("buildx imagetools inspect", "docker buildx imagetools inspect ghcr.io/x:1", None, A, ""),
    # ------------------------------------------------------------- publish modules: edge and bench free, stable asked, entry steps refused
    ("deploy_edge is free", "%s rediacc_ci.deploy.deploy_edge" % PY, None, A, "!BLOCKED"),
    (
        "the skill's edge www deploy in the devbox",
        "%s env %s bash -c 'npm run build:packages && "
        "PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_edge'" % (DEVBOX, BWS),
        None,
        A,
        "",
    ),
    ("deploy_bench is free", "%s rediacc_ci.ops.deploy_bench" % PY, None, A, ""),
    (
        "deploy_account eu, default production",
        "%s rediacc_ci.deploy.deploy_account --region eu" % PY,
        None,
        B,
        "a stable target",
    ),
    (
        "deploy_account eu --target production",
        "%s rediacc_ci.deploy.deploy_account --region eu --target production" % PY,
        None,
        B,
        "a stable target",
    ),
    (
        "deploy_account us --target stable",
        "%s rediacc_ci.deploy.deploy_account --region us --target stable" % PY,
        None,
        B,
        "a stable target",
    ),
    (
        "deploy_account eu production, proven ASKED",
        "%s %s rediacc_ci.deploy.deploy_account --region eu --target production" % (ASK, PY),
        TR,
        A,
        "admitted by RELEASE_ASKED",
    ),
    (
        "deploy_account asia --target edge",
        "%s rediacc_ci.deploy.deploy_account --region asia --target edge" % PY,
        None,
        A,
        "",
    ),
    (
        "deploy_account eu --target=edge",
        "%s rediacc_ci.deploy.deploy_account --region eu --target=edge" % PY,
        None,
        A,
        "",
    ),
    ("deploy_www is stable", WWW, None, B, "(stable)"),
    (
        "account_secrets_local --target stable",
        "%s rediacc_ci.deploy.account_secrets_local --region eu --target stable" % PY,
        None,
        B,
        "a stable target",
    ),
    (
        "account_secrets_local --target stable, proven ASKED",
        "%s %s rediacc_ci.deploy.account_secrets_local --region eu --target stable" % (ASK, PY),
        TR,
        A,
        "admitted",
    ),
    (
        "account_secrets_local --target edge",
        "%s rediacc_ci.deploy.account_secrets_local --region us --target edge" % PY,
        None,
        A,
        "",
    ),
    (
        "account_secrets_local stable dry run",
        "%s rediacc_ci.deploy.account_secrets_local --region eu --target stable --dry-run" % PY,
        None,
        A,
        "",
    ),
    (
        "deploy_proxy --target bench",
        "%s rediacc_ci.deploy.deploy_proxy --target bench" % PY,
        None,
        A,
        "",
    ),
    (
        "deploy_proxy --target=bench",
        "%s rediacc_ci.deploy.deploy_proxy --target=bench" % PY,
        None,
        A,
        "",
    ),
    (
        "deploy_proxy --target edge",
        "%s rediacc_ci.deploy.deploy_proxy --target edge --region eu" % PY,
        None,
        A,
        "",
    ),
    (
        "deploy_proxy --target stable",
        "%s rediacc_ci.deploy.deploy_proxy --target stable --region eu" % PY,
        None,
        B,
        "a stable target",
    ),
    (
        "deploy_proxy with no target",
        "%s rediacc_ci.deploy.deploy_proxy --region eu" % PY,
        None,
        B,
        "a stable target",
    ),
    (
        "console_executor --target edge",
        "%s rediacc_ci.deploy.console_executor --enable --target edge --region eu" % PY,
        None,
        A,
        "",
    ),
    (
        "console_executor --target stable",
        "%s rediacc_ci.deploy.console_executor --enable --target stable --region eu" % PY,
        None,
        B,
        "a stable target",
    ),
    (
        "account secrets for a stable Worker",
        "TARGET=stable WORKER_NAME=rediacc-account-eu %s %s" % (PY, ACCT_SECRETS),
        None,
        B,
        "a stable target",
    ),
    (
        "account secrets for an edge Worker",
        "TARGET=edge WORKER_NAME=edge-rediacc-account-eu %s %s" % (PY, ACCT_SECRETS),
        None,
        A,
        "",
    ),
    (
        "account secrets with no target on the line",
        "%s %s" % (PY, ACCT_SECRETS),
        None,
        B,
        "a stable target",
    ),
    (
        "edge secrets aimed at a stable Worker",
        "TARGET=edge WORKER_NAME=rediacc-account-eu %s %s" % (PY, ACCT_SECRETS),
        None,
        B,
        "a stable target",
    ),
    (
        "www secrets for the edge Worker",
        "WORKER_NAME=edge-rediacc-www %s rediacc_ci.deploy.set_www_worker_secrets" % PY,
        None,
        A,
        "",
    ),
    (
        "www secrets for the stable Worker",
        "WORKER_NAME=rediacc-www %s rediacc_ci.deploy.set_www_worker_secrets" % PY,
        None,
        B,
        "a stable target",
    ),
    (
        "preview secrets are never stable",
        "WORKER_NAME=pr-12-www %s rediacc_ci.deploy.set_preview_worker_secrets" % PY,
        None,
        A,
        "",
    ),
    (
        "promote_r2_to_stable, proven ASKED",
        "%s %s rediacc_ci.deploy.promote_r2_to_stable" % (ASK, PY),
        TR,
        A,
        "admitted",
    ),
    (
        "upload_to_r2 by script path",
        "python3 .ci/rediacc_ci/deploy/upload_to_r2.py",
        None,
        B,
        "a step of the release entry",
    ),
    (
        "write_release_sentinel from .ci",
        "cd .ci && python3 -m rediacc_ci.deploy.write_release_sentinel",
        None,
        B,
        "a step of the release entry",
    ),
    (
        "a release step under bws_env",
        "%s %s rediacc_ci.release.tag_submodules" % (BWS, PY),
        None,
        B,
        "tag_submodules",
    ),
    (
        "a release step with a proven ASKED",
        "%s %s rediacc_ci.release.create_github_release" % (ASK, PY),
        TR,
        B,
        "a step of the release entry",
    ),
    ("--help on a publish module", "%s rediacc_ci.deploy.upload_to_r2 --help" % PY, None, A, ""),
    ("an npm gate naming a deploy package", "npm run check:ci-proxy-configs", None, A, ""),
    ("pytest naming a module", "python3 -m pytest -k rediacc_ci.deploy.deploy_www", None, A, ""),
    ("reading a module", "sed -n 1,20p .ci/rediacc_ci/deploy/deploy_www.py", None, A, ""),
    # ------------------------------------------------------------- mentions are not runs
    ("echo of a publish verb", "echo 'wrangler deploy && gh release create v1'", None, A, ""),
    ("grep for a publish verb", "grep -rn 'docker push' .github", None, A, ""),
    (
        "a commit message naming verbs",
        "git commit -m 'drop docker push and wrangler deploy' -- a.txt",
        None,
        A,
        "",
    ),
    # ------------------------------------------------------------- the release clone
    ("redirect into the clone", "echo x > %s/a.txt" % CLONE, None, B, "redirect into"),
    (
        "absolute redirect into the clone",
        "echo x >> %s/%s/a.txt" % (REPO, CLONE),
        None,
        B,
        "redirect into",
    ),
    ("tee into the clone", "echo x | tee %s/a.txt" % CLONE, None, B, "release clone"),
    (
        "sed -i in the clone",
        "sed -i s/a/b/ %s/package.json" % CLONE,
        None,
        B,
        "-i on the release clone",
    ),
    ("cp onto the clone", "cp /tmp/a %s/a" % CLONE, None, B, "onto the release clone"),
    ("mv onto the clone", "mv /tmp/a %s/a" % CLONE, None, B, "release clone"),
    ("mv out of the clone", "mv %s/a /tmp/a" % CLONE, None, B, "mv on the release clone"),
    ("rm in the clone", "rm -rf %s" % CLONE, None, B, "rm on the release clone"),
    ("mkdir the clone", "mkdir -p %s" % CLONE, None, B, "mkdir"),
    ("touch in the clone", "touch %s/a" % CLONE, None, B, "touch"),
    ("chmod the clone", "chmod -R u+w .ci/cache/release", None, B, "chmod"),
    ("ln into the clone", "ln -s /tmp/x %s/x" % CLONE, None, B, "release clone"),
    ("xargs feeds rm the clone", "echo %s | xargs rm -rf" % CLONE, None, B, "rm"),
    ("a redirect after cd into the clone", "cd %s && echo x > a" % CLONE, None, B, "redirect"),
    ("git checkout in the clone", "git -C %s checkout -- ." % CLONE, None, B, "git checkout"),
    (
        "git commit after cd into the clone",
        "cd %s && git commit -m x" % CLONE,
        None,
        B,
        "git commit inside",
    ),
    ("git clone into the release dir", "git clone . %s" % CLONE, None, B, "release clone"),
    (
        "python -c writing the clone",
        "python3 -c \"open('%s/a','w').write('x')\"" % CLONE,
        None,
        B,
        "python3 code",
    ),
    (
        "python heredoc writing the clone",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s/a').write_text('x')\nEOF" % CLONE,
        None,
        B,
        "python3 code",
    ),
    (
        "python writing after cd into the clone",
        "cd %s && python3 -c \"open('a','w')\"" % CLONE,
        None,
        B,
        "writes inside",
    ),
    ("sh -c redirect into the clone", "sh -c 'echo x > %s/a'" % CLONE, None, B, "redirect into"),
    ("cat in the clone", "cat %s/package.json" % CLONE, None, A, ""),
    ("ls the release dir", "ls -la .ci/cache/release", None, A, ""),
    ("grep the clone", "grep -rn x %s" % CLONE, None, A, ""),
    ("git status in the clone", "git -C %s status --porcelain" % CLONE, None, A, ""),
    ("git log after cd into the clone", "cd %s && git log -1" % CLONE, None, A, ""),
    ("cp out of the clone", "cp %s/a /tmp/a" % CLONE, None, A, ""),
    (
        "python reading the clone",
        "python3 -c \"print(open('%s/a').read())\"" % CLONE,
        None,
        A,
        "",
    ),
    ("find in the release dir", "find .ci/cache/release -name package.json", None, A, ""),
    ("du the release dir", "du -sh .ci/cache/release", None, A, ""),
    ("echo naming the clone", "echo 'see .ci/cache/release/'", None, A, ""),
    (
        "the gates module writes the clone",
        "%s rediacc_ci.release.local_gates --clone %s" % (PY, CLONE),
        None,
        A,
        "",
    ),
    ("a sibling cache dir", "echo x > .ci/cache/releases-old/a", None, A, ""),
]

# Generated from the guard's own tables, so a module added there is covered here without an edit: every entry step is refused bare, every stable module needs the ask and is admitted with a proven one.
CASES.extend(
    (
        "bare -m %s" % module.rsplit(".", 1)[-1],
        "%s %s" % (PY, module),
        None,
        B,
        "a step of the release entry",
    )
    for module in G.STEP_MODULES
)
CASES.extend(
    ("bare -m %s" % module.rsplit(".", 1)[-1], "%s %s" % (PY, module), None, B, "(stable)")
    for module in G.STABLE_MODULES
)
CASES.extend(
    (
        "asked -m %s" % module.rsplit(".", 1)[-1],
        "%s %s %s" % (ASK, PY, module),
        TR,
        A,
        "admitted by RELEASE_ASKED",
    )
    for module in G.STABLE_MODULES
)


def _declares_dry_run(module):
    source = (REPO / ".ci" / pathlib.Path(*module.split("."))).with_suffix(".py")
    return source.is_file() and '"--dry-run"' in source.read_text(encoding="utf-8")


# --dry-run on a publish module passes when the module's own source declares it; otherwise the run is judged as if the flag were absent (an edge module is free either way, every other bare run is refused).
CASES.extend(
    (
        "-m %s --dry-run (declared: %s)" % (module.rsplit(".", 1)[-1], _declares_dry_run(module)),
        "%s %s --dry-run" % (PY, module),
        None,
        not _declares_dry_run(module) and module not in G.EDGE_MODULES,
        "",
    )
    for module in G.PUBLISH_MODULES
)

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id in ('DEFECT', 'MUTANTS') for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert outside.count(old) == 1, 'the mutant must name exactly one span outside its"
    " declaration: %%r' %% (old,)\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def run(command, transcript_path, broken=None):
    """(blocked, stderr) of one payload through the dispatcher, or through a copy of the guard with `broken` planted."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(REPO))
    env.pop("RELEASE_ASKED", None)
    doc = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(REPO)}
    if transcript_path:
        doc["transcript_path"] = transcript_path
    if broken:
        argv = [
            sys.executable,
            "-c",
            BROKEN_RUNNER % (str(HERE.parent.parent), str(GUARD), broken, str(GUARD)),
        ]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv,
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(REPO),
    )
    if proc.returncode not in (0, 2):
        raise SystemExit(
            "%s runner crashed (rc %d): %s"
            % ("broken" if broken else "guard", proc.returncode, proc.stderr[-1200:])
        )
    return proc.returncode == 2, proc.stderr


fails = 0
blocked = 0
for name, command, tr, want, needle in CASES:
    got, err = run(command, tr)
    blocked += got
    if needle.startswith("!"):
        ok = got == want and needle[1:] not in err
    else:
        ok = got == want and (not needle or needle in err)
    fails += not ok
    print(
        "%-62s want=%-8s got=%-8s %s"
        % (
            name[:62],
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok:
        print("    needle %r; stderr: %s" % (needle, err.strip().splitlines()[:6]))

print()
CONTROLS = [("DEFECT", G.DEFECT), *sorted(G.MUTANTS.items())]
# The case each control must flip, so a control cannot pass on an unrelated refusal.
MUST_FLIP = {
    "DEFECT": "wrangler deploy",
    "asked-always-true": "stable: ASKED matching no answer",
    "channel-before-separator": "entry: channel before the separator",
    "any-channel-admitted": "entry: stable channel",
    "account-target-ignored": "deploy_account eu, default production",
    "proxy-target-ignored": "deploy_proxy --target stable",
    "stable-config-unasked": "wrangler deploy on a stable config, no ASKED",
    "tag-push-ignored": "push a v tag",
    "release-dir-ignored": "rm in the clone",
}
for label, mutant in CONTROLS:
    must = MUST_FLIP[label]
    command, tr = next((c, t) for n, c, t, _w, _n in CASES if n == must)
    still, _err = run(command, tr, broken=mutant)
    if still:
        fails += 1
        print("*** FAIL *** %s control: planted %r; %r still refused" % (label, mutant[1], must))
    else:
        print("%s control: planted %r; %r flipped to allowed" % (label, mutant[1], must))

print()
if len(CASES) < 100 or blocked < 40 or len(CASES) - blocked < 40:
    fails += 1
    print("*** FAIL *** the suite shrank: %d case(s), %d refused" % (len(CASES), blocked))
print(
    "FAILURES: %d  (%d case(s): %d refused, %d admitted; %d control(s))"
    % (fails, len(CASES), blocked, len(CASES) - blocked, len(CONTROLS))
)
sys.exit(1 if fails else 0)
