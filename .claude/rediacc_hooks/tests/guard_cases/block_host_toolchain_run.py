"""The test tables of `block_host_toolchain_run`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

# The three docker worlds this guard's tail distinguishes, driven rather than described. Without them the differential only ever sees whichever devbox this machine happens to be running, and the two NOTE branches plus the refusal are a coin toss decided by another session's `devbox up`.
ENVS = [
    ("no-devbox", {}, {"docker": "#!/bin/sh\nexit 0\n"}),
    (
        "devbox-without-tool",
        {},
        {"docker": '#!/bin/sh\ncase "$1" in ps) echo rediacc-devbox-x ;; exec) exit 1 ;; esac\n'},
    ),
    (
        "devbox-with-tool",
        {},
        {"docker": '#!/bin/sh\ncase "$1" in ps) echo rediacc-devbox-x ;; exec) exit 0 ;; esac\n'},
    ),
]


EDGE_CASES = [
    # Already routed through the devbox, or driving the devbox itself.
    ("already routed", "./run.sh devbox exec -- npm run check:ci-python-lint"),
    ("a docker exec", "docker exec -u vscode box bash -lc 'ruff check .'"),
    # The npx arm fires on SHAPE, whatever the host has.
    ("npx ruff", "npx ruff format packages/cli"),
    ("npx --yes shfmt", "npx --yes shfmt -w run.sh"),
    ("npx on an npm package is not this guard's business", "npx tsx scripts/gen/gen-docs.ts"),
    # #0c331972: npm's own option grammar, so an option the guard never listed and the `x` alias still reach the tool.
    ("npx with a value option before the tool", "npx --logl silent --yes ruff check"),
    ("npm x -y ruff", "npm x -y ruff check"),
    ("npm exec -- shfmt", "npm exec -- shfmt -d run.sh"),
    ("npx -c runs a shell, not a package", "npx -c 'ruff check a.py'"),
    ("prose naming npm x ruff", "echo 'npm x -y ruff check'"),
    # The bare-tool arm.
    ("a bare shfmt", "shfmt -w run.sh"),
    ("a bare shellcheck", "shellcheck .ci/media/tools/upload-r2.sh"),
    ("a bare actionlint", "actionlint"),
    ("a bare tool after a separator", "cd packages/cli && shfmt -d ."),
    ("a tool named in prose", "echo 'run shfmt -w on it'"),
    # The gate-key arm, including the substring pair whose hash order decides $HIT.
    ("a gate key", "npm run check:ci-renet"),
    ("the longer gate key matches both", "npm run check:ci-renet-tiers"),
    # The host-bound arm.
    ("a host-bound pipeline", "shfmt -w private/growth/video_pipeline/run.sh"),
    ("a host-bound submodule", "shellcheck private/account/scripts/ops.sh"),
    # The python -m arm: a port's module is its target, and the same key handed to pytest is a mention.
    ("a python -m port", "PYTHONPATH=.ci python3 -m rediacc_ci.ops.scrub_sentinel v1.0.5"),
    ("a python -m port by script path", "python3 .ci/rediacc_ci/deploy/upload_to_r2.py"),
    ("a port named to pytest", "python3 -m pytest -k rediacc_ci.ops.scrub_sentinel"),
    # Parse-only shells and text bash never runs (2026-10-02): judged by run, not by text.
    ("a parse-only bash -n", "bash -n .ci/media/tools/upload-r2.sh"),
    ("a parse-only -o noexec", "sh -o noexec .ci/media/tools/upload-r2.sh"),
    ("a noexec shell's -c payload", "bash -n -c 'aws s3 ls'"),
    ("a tool named in a comment", "echo hi # then; aws s3 ls"),
    (
        "a heredoc comment, then a syntax check",
        (
            "python3 - <<'EOF'\n# aws matches the whole key\nEOF\n"
            "bash -n .ci/media/tools/upload-r2.sh"
        ),
    ),
    (
        "a script run after a parse-only one",
        "bash -n x.sh && bash .ci/media/tools/upload-r2.sh",
    ),
    ("a tool in a -c payload", "bash -c 'aws s3 ls'"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    ("npx ruff launched by find -exec", "find . -name '*.py' -exec npx ruff format {} +"),
    ("prose naming a launched npx ruff", "echo find . -name x -exec npx ruff format {} +"),
]
