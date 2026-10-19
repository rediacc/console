# PLAN: one pinned aws CLI, resolved through one resolver, on every lane that calls R2
Status: executing
Depends-On: no-dep -- the resolver, pins and bootstrap rungs it builds on already exist on main
Priority: P2 -- local ops tools that need aws fail on every dev host; CI is unaffected today
Owner: session d778be9d
Updated: 2026-10-19
Finding: #6bc7c240
Owns: .ci/rediacc_ci/core/awscli.py, .ci/rediacc_ci/core/common.py, .ci/rediacc_ci/core/release_state_validator.py, .ci/rediacc_ci/core/toolchain.py, .ci/rediacc_ci/deploy/**, .ci/rediacc_ci/ops/scrub_sentinel.py, .ci/rediacc_ci/ops/cf_auth.py, .ci/rediacc_ci/housekeeping/cleanup_versions.py, .ci/rediacc_ci/quality/release_state.py, .ci/rediacc_ci/quality/aws_resolver.py, .ci/rediacc_ci/release/**, .ci/rediacc_ci/setup/tools.py, .ci/rediacc_ci/tests/test_core_awscli.py, .ci/rediacc_ci/tests/test_bootstrap_aws_resolver.py, .ci/rediacc_ci/tests/test_deploy_*.py, .ci/rediacc_ci/tests/pathmask.py, .ci/scripts/quality/check_aws_resolver.py, .ci/scripts/lib/toolchain.sh, .ci/bootstrap.sh, .ci/media/tools/upload-r2.sh, .devcontainer/toolchain.env, .devcontainer/Dockerfile, .ci/config/pins.json, .ci/config/python-env-registry.json, .ci/config/env-manifest.json, scripts/data/doc-registry.md, scripts/ci-runner/manifest.ts, package.json, conftest.py, .github/workflows/ci.yml, .github/workflows/ci-quality.yml, .github/workflows/promote-stable.yml
Concurrency: exclusive -- B5 rewrites every aws call site against B2's API, so B1-B4 land first, and B7 (the CI switch) waits for B6's differential.

## Finding

Measured 2026-10-19 while scrubbing the v1.3.2 sentinel (operator ruling ASKED:2026-10-19T10:52Z): `bws_env exec --profile r2-artifacts -- python3 -m rediacc_ci.ops.scrub_sentinel v1.3.2` printed `✗ Required command 'aws' is not available`. A shim running `.ci/cache/toolchain/uv-0.12.10/uvx --from awscli==1.36.0 aws` on the host's Python 3.14 failed `badly formed help string` (exit 255) on `s3api list-objects-v2`; it worked only with `uvx --python 3.12`.

- 23 non-test modules call `aws` (`git grep -lE '"aws"' -- .ci/rediacc_ci ':!.ci/rediacc_ci/tests'`), among them promote_r2_to_stable(_hotfix), write_once_guard_check, cleanup_versions, cf_auth (`aws iam`, .ci/rediacc_ci/ops/cf_auth.py:351) and release/{advance_contract_floor, assert_edge_tag_exists, assert_r2_sentinel, cd_preflight, reprobe_r2_sentinel}. Bash call sites: .github/workflows/ci.yml:1935 (inline `aws s3 rm`) and .ci/media/tools/upload-r2.sh.
- Three presence checks: `common.require_cmd` (shutil.which, .ci/rediacc_ci/core/common.py:302-314) in 9 modules, `shutil.which("aws")` (.ci/rediacc_ci/ops/scrub_sentinel.py:163), and a local `_require_cmd` (.ci/rediacc_ci/release/advance_contract_floor.py:170, .ci/rediacc_ci/release/reprobe_r2_sentinel.py:59). All exec a bare `"aws"` argv[0] (.ci/rediacc_ci/core/common.py:588, .ci/rediacc_ci/ops/scrub_sentinel.py:51-52).
- CI works only because the jobs run on `ubuntu-latest` "for the aws CLI" (.github/workflows/ci.yml:1067-1069, .github/workflows/ci-quality.yml:1873-1881): an unpinned aws at /usr/local/bin/aws (.ci/rediacc_ci/tests/pathmask.py:11).
- No install-table row names aws: .ci/rediacc_ci/setup/tools.py A2 (.ci/rediacc_ci/setup/tools.py:787-810) covers only `toolchain.TOOL_KEYS` (.ci/rediacc_ci/core/toolchain.py:136-146), so the gap is invisible by construction.

## Conventions followed

- Pins: one `KEY=value` per pin in `.devcontainer/toolchain.env`; Python tools carry a bare version and no sha, because uv verifies them from the index (.devcontainer/toolchain.env:32-33 and .devcontainer/toolchain.env:105-124).
- pins.json: pypi-sourced Python tools are `toolchain:<name>` leaves with `source.type: "pypi"` and `safety.mode: "release-age"` (`toolchain:ruff` .ci/config/pins.json:1474, `toolchain:mypy` .ci/config/pins.json:1506, `toolchain:pytest-xdist` .ci/config/pins.json:1613 with a gen-docs `derive`). An operator-chosen line uses `source.type: "none"` with a `BLOCKER:` reason (`toolchain:node` .ci/config/pins.json:1435).
- Bootstrap rungs: explicit `*_BIN`, then a PATH binary at the pin, then the repo cache (.ci/bootstrap.sh:49-56, resolvers .ci/bootstrap.sh:178-237); installs are uv tools under `.ci/cache/toolchain/uv-tools` (.ci/bootstrap.sh:111-116, `install_ruff` .ci/bootstrap.sh:374-390); the doctor prints one row per tool (.ci/bootstrap.sh:470-522); no version literal in .ci/**/*.sh (.ci/bootstrap.sh:58-61).
- `toolchain_probe_version` and `toolchain_pin_for` (.ci/scripts/lib/toolchain.sh:72-120) mirror `TOOL_KEYS` arm for arm.
- Docs: `bootstrapPins` (scripts/lib/doc-providers.ts:1084-1110) renders scripts/data/doc-registry.md:1041.

## Decisions

1. awscli v1 from PyPI, not v2: v2 is not on PyPI and needs per-OS installers, four sha256 pins and a new driver path; v1 reuses the uv tool path, the pypi driver and release-age. CI moves from the runner's v2 to v1, gated by B6 and B7.
2. Pin the interpreter: `AWSCLI_PYTHON_VERSION=3.12` as a `none`-source leaf with a BLOCKER reason, installed with `UV_PYTHON_INSTALL_DIR=.ci/cache/toolchain/uv-python` and `UV_PYTHON_PREFERENCE=only-managed`, so neither the host's 3.14 nor ~/.local is involved.
3. Resolver rungs (core/awscli.py, mirrored by bootstrap `resolve_aws`): `AWS_BIN` (set but not executable is a refusal), then `aws` on PATH taken as found with no version probe (36 test files put a fake `aws` on PATH, and a probe would add a call to their ledgers), then `.ci/cache/toolchain/uv-tools/bin/aws` at `AWSCLI_VERSION` only. The doctor shows PATH drift beside the pin.
4. CI uses the pin: production R2 writes happen in CI, and the runner's aws changes with each image refresh. Exported `AWS_BIN` beats the runner's PATH aws; the aws jobs can then move to `ubuntu-slim`. Staged as B7, after B6.

## Revision 2026-10-19: pin the latest v2 (operator ruling)

Operator /ask ASKED:2026-10-19T13:30Z: "Ride PR #600 now", and on the version question ("why it pins? Isn't the new version better?") the ruling "Pin latest v2". This revision overrides Decisions 1 and 2 and the v1 wording inside the boxes below; the box text itself stays byte for byte, because check:ci-plan-boxes keys a box on its text.

- The pin is awscli **v2**, the newest release past the 24 h release-age window, never v1 from PyPI and never a Python pin. `AWSCLI_PYTHON_VERSION` and the `toolchain:awscli-python` leaf are dropped.
- Install source: AWS's versioned installers, verified 2026-10-19 to answer HTTP 200: `https://awscli.amazonaws.com/awscli-exe-linux-x86_64-<v>.zip`, `awscli-exe-linux-aarch64-<v>.zip` and `AWSCLIV2-<v>.pkg` (macOS). Each is pinned by a sha256 in `.devcontainer/toolchain.env` (`AWSCLI_SHA256_LINUX_X86_64`, `AWSCLI_SHA256_LINUX_AARCH64`, `AWSCLI_SHA256_DARWIN`), the shape `UV_SHA256_*` already uses (toolchain.env:156-159).
- B1: the `toolchain:awscli` leaf takes its version from the aws/aws-cli release tags (2.x.y) and records one sha256 site per asset, like `toolchain:uv` (source github-release or tag, release-age, `sites` per asset). If the pins driver cannot fetch those assets, extend the toolchain driver in the same box rather than hand-editing the shas.
- B3: `install_aws` downloads the platform's versioned installer, verifies its sha256, and installs into `.ci/cache/toolchain/aws-cli/<v>/` (Linux: `./aws/install --install-dir ... --bin-dir ...`; macOS: `pkgutil --expand-full` of the .pkg), so no root and no system path is touched. The resolver's cache rung is `.ci/cache/toolchain/aws-cli/<v>/bin/aws`.
- B4: the Dockerfile installs the same pinned zip with its sha256 check.
- B6: the probe that parses `aws --version` reads `aws-cli/2.x.y`. The simulate_promotion differential stays: it now checks the pinned v2 against the runner's v2 rather than v1 against v2.
- B7: CI keeps v2 and runs the pinned one through `AWS_BIN`; moving the aws jobs to ubuntu-slim stays in scope.

## Boxes

- [ ] B1 Pins: `AWSCLI_VERSION` (newest past the release-age window) and `AWSCLI_PYTHON_VERSION=3.12` in toolchain.env with rationale comments; pins.json leaves `toolchain:awscli` (pypi, release-age, gen-docs derive) and `toolchain:awscli-python` (none, BLOCKER); seed through `npm run pins -- bump toolchain:awscli`. Acceptance: `check:ci-pin-registry`, `check:ci-toolchain-pins`, `check:ci-toolchain-env-dockerfile-sync` rc 0.
- [ ] B2 Resolver `.ci/rediacc_ci/core/awscli.py`: `AWS = "aws"` (the logical argv[0], so dry-run and differential output stay byte-identical), `resolve()`, `require()` (refusal names `bash .ci/bootstrap.sh install aws`), `argv()`, `run()`; `"aws": "AWSCLI_VERSION"` in `TOOL_KEYS` with matching `aws)` arms in toolchain.sh.
- [ ] B3 Bootstrap: `resolve_aws`, `install_aws` (uv tool install at the pinned Python, verified by a probe), an optional `aws` doctor row (ABSENT is yellow, never rc), arms `install aws` and `which aws`; `write_pytest_wrapper` still runs last.
- [ ] B4 Install table, devcontainer, isolation: an `aws` Tool row in setup/tools.py; the Dockerfile installs the pin beside :425-431; root conftest.py pops `AWS_BIN` at session start.
- [ ] B5 Route every call site: argv heads become `awscli.AWS`, execs `awscli.run`/`awscli.argv`, presence checks `awscli.require()`; bash uses `"${AWS_BIN:-aws}"`; tests that drop aws also set `AWS_BIN=<tmp>/absent`.
- [ ] B6 Gate and tests: `check:ci-aws-resolver` (AST scan: no literal `"aws"` argv head, no `require_cmd`/`which` of `"aws"`, a module naming `awscli.AWS` calls the resolver, no bare `aws s3|s3api|iam` in workflows or .ci shell; fails under 20 discovered modules; `--selftest` plants one violation per rule), wired in package.json, manifest.ts and ci-quality.yml; `test_core_awscli.py` (rung order, a missing AWS_BIN refuses, an off-pin cache binary is rejected, the finding's repro passes preflight); `test_bootstrap_aws_resolver.py`; a `simulate_promotion` differential against a scratch R2 prefix under the pin, checking whether R2 accepts botocore's default CRC checksums (else `AWS_REQUEST_CHECKSUM_CALCULATION=when_required` in `awscli.run`).
- [ ] B7 CI on the pin: each aws job (ci.yml cd-preflight, upload, promote; ci-quality quality-i18n; promote-stable.yml) caches and installs the pin and exports `AWS_BIN`; `runs-on` moves to `ubuntu-slim`; the added time is measured.

## Regenerated artifacts

- scripts/data/doc-registry.md (`npx tsx scripts/gen/gen-docs.ts --write`).
- .ci/config/python-env-registry.json (`--write-baseline --allow-new .ci/rediacc_ci/core/awscli.py:AWS_BIN`).
- .ci/config/env-manifest.json (`npm run env:register`).
- The pins journal, written by `npm run pins -- bump toolchain:awscli`.

## Verification

```
bash .ci/bootstrap.sh install aws && bash .ci/bootstrap.sh doctor
bws_env exec --profile r2-artifacts -- python3 -m rediacc_ci.ops.scrub_sentinel v1.3.2   # no "Required command 'aws'"
.ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_core_awscli.py .ci/rediacc_ci/tests/test_bootstrap_aws_resolver.py .ci/rediacc_ci/tests/test_deploy_*.py
npm run check:ci-aws-resolver && npm run check:ci-toolchain-pins && npm run check:ci-pin-registry
npm run check:ci-toolchain-env-dockerfile-sync && npm run check:ci-python-env-registry && npm run check:ci-env-manifest
npx tsx scripts/gen/gen-docs.ts --check
# plant: subprocess.run(["aws", "s3", "ls"]) in scrub_sentinel.py -> check:ci-aws-resolver rc 1; revert -> rc 0
```
