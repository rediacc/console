# Derived registry (generated)

Every table below is rewritten from the tree by `scripts/gen/gen-docs.ts`. Nothing in a region is typed by hand, and `npx tsx scripts/gen/gen-docs.ts` (no flags) fails if any of it has drifted.

`npm run gen:docs` runs VERIFY mode, not the writer. Regenerating is `npx tsx scripts/gen/gen-docs.ts --write`, spelled out rather than given a key, because a one-word way to overwrite every generated region is a way to overwrite them without reading the diff. The gate that runs all of this in CI is `check:ci-pytest`, through
`.ci/rediacc_ci/tests/gates/test_gate_docs_gen.py`, which drives the generator in both directions: green on the tree as it stands, and red over a single perturbed row.

This file is the phase 0 home for those regions. It is deliberately NOT one of the documents a reader is sent to: `CLAUDE.md`, `docs/agent-reference/ci-gates.md`, `docs/agent-reference/suppressions.md` and `docs/agent-reference/TRAPS.md` each have exactly one writer during the tooling transformation, and phase 0 is not that writer. Those documents opt in later by carrying the same
markers, which needs no change to the generator: targets are discovered by scanning for the marker, not from a list.

The frozen companion to this file is `scripts/data/doc-registry-preport.json`, which records the row SET of every provider as it stood before the ports began. A count floor cannot catch a silent drop -- a floor of 300 still passes after 88 of 388 rows vanish, and count equality still passes when 88 are swapped for 88 others -- so membership is the only instrument that names what
was lost, and it only works if it was recorded first.

## Gates

<!-- >>> gen-docs: gates -->
<!-- Derived from the COMMITTED LOCK, never from scripts/ci-runner/manifest.ts. That file is a -->
<!-- single-writer file behind the root driver's merge queue for this whole program, and every -->
<!-- extra reader of it is one more thing the registry workstream has to carry across; two -->
<!-- readers were drained onto the lock the same day this provider was switched onto it. The -->
<!-- swap was proved a no-op on content: same row set, same count, no duplicates either side. -->

Scans: scripts/ci-runner/gates.lock.json, the committed projection of the manifest that `check:ci-gates-lock` keeps faithful.

| Gate | Runs in CI as | Is gate | Slow | Gate test |
|---|---|---|---|---|
| build:packages | local-only | no | no | no |
| build:www | quality-www-build / Build www (produces dist/route-manifest.json) | no | yes | no |
| check:actions | quality-code / Action freshness | yes | no | no |
| check:ci-account-config-auth | quality-go / Check config token auth requires org membership | yes | no | no |
| check:ci-account-layer-isolation | quality-code / Check account route layer isolation | yes | yes | no |
| check:ci-account-no-admin-role | quality-go / Check no admin user role (must be root) | yes | no | no |
| check:ci-account-no-node-env-routes | quality-go / Assert no NODE_ENV branching in account routes | yes | no | no |
| check:ci-account-onboarding | quality-content / Validate account onboarding splash against canonical tutorials | yes | no | no |
| check:ci-account-portal | quality-packages / Check account portal (typecheck + build) | yes | yes | no |
| check:ci-account-probes | quality-static / Dev-stack liveness probes | yes | no | no |
| check:ci-account-scope-audit | quality-go / Check scope registry audit | yes | no | no |
| check:ci-account-server | quality-go / Run account integration tests | yes | yes | no |
| check:ci-actionlint | quality-code / Workflow lint (actionlint) | yes | no | no |
| check:ci-actions-allowlist | quality-static / Actions allowlist | yes | no | no |
| check:ci-actions-vars | quality-security / GitHub Actions variables | yes | no | no |
| check:ci-agent-browser-exit | quality-static / agent-browser exit status | yes | yes | no |
| check:ci-agent-hint-liveness | quality-content / Agent hints can actually fire | yes | no | no |
| check:ci-agent-model-roster | quality-content / Agent model roster matches its documented reasons | yes | no | no |
| check:ci-agent-session-archival | quality-branch / Agent session archival | yes | no | no |
| check:ci-allowlist-key-matching | quality-static / Allowlist key matching | yes | no | no |
| check:ci-anchor-integrity | quality-www-build / Redirects | yes | yes | no |
| check:ci-app-admin-perm | quality-code / App admin permission | yes | no | no |
| check:ci-audit-coverage | quality-static / Check audit logging coverage for CLI operations | yes | no | no |
| check:ci-aws-credential-bridge | quality-code / AWS credential bridge | yes | no | no |
| check:ci-backup-bucket-conformance | quality-code / Backup bucket conformance | yes | no | no |
| check:ci-backup-manifest-shape-parity | quality-code / Backup manifest shape parity | yes | no | no |
| check:ci-backup-protocol-conformance | quality-code / Backup protocol conformance | yes | no | no |
| check:ci-baseline-key-semantics | quality-content / Baseline key semantics | yes | no | no |
| check:ci-battery-clean-tree | quality-static / Battery clean-tree guard | yes | no | no |
| check:ci-bootstrap-idempotency | quality-code / Bootstrap paths install through the dependency stamp | yes | no | no |
| check:ci-breakpoint-drift | quality-code / Breakpoint drift | yes | no | no |
| check:ci-browser-smoke | quality-www-build / Browser smoke | yes | yes | no |
| check:ci-builder-env-contract | quality-code / Builder env contract | yes | no | no |
| check:ci-bws-map | quality-security / Bitwarden secret map | yes | no | no |
| check:ci-bws-rotation-notice | quality-security / BWS rotation notice | yes | no | no |
| check:ci-captcha-recovery | quality-www-build / Captcha recovery | yes | no | no |
| check:ci-ceph-image-pin | quality-code / Ceph image pin freshness | yes | no | no |
| check:ci-changed-selection | quality-code / Changed-file selection contract | yes | no | no |
| check:ci-checkout-cone | quality-static / Checkout cone covers what steps run | yes | no | no |
| check:ci-cli-contract | quality-packages / CLI contract | yes | yes | no |
| check:ci-cli-doc-coverage | quality-code / CLI docs stay in sync with their scripts' real flags | yes | no | no |
| check:ci-client-bundle-budget | quality-www-build / SEO | yes | yes | no |
| check:ci-client-i18n | quality-i18n / i18n | yes | no | no |
| check:ci-command-planes | quality-code / Command planes | yes | no | no |
| check:ci-command-tree | quality-code / Command tree | yes | yes | no |
| check:ci-compose-env | quality-static / Compose env | yes | no | no |
| check:ci-config-migrations | quality-packages / Check config-migration runner + fixtures | yes | no | no |
| check:ci-content-quality | quality-content / Check content for AI slop patterns | yes | yes | no |
| check:ci-control-in-string | quality-code / Controls are not written inside string literals | yes | no | no |
| check:ci-control-vacuity | quality-code / Control-first gates prove their plant landed | yes | no | no |
| check:ci-css-dom-refs | quality-content / CSS DOM references | yes | no | no |
| check:ci-cta-bolt | quality-www-build / CTA bolt | yes | yes | no |
| check:ci-dead-bash | quality-code / Dead bash | yes | yes | no |
| check:ci-dead-case-arms | test: .ci/rediacc_ci/tests/gates/test_gate_dead_case_arms.py | yes | no | no |
| check:ci-dead-css | quality-content / Dead CSS | yes | no | no |
| check:ci-dead-python | quality-static / Dead Python | yes | no | no |
| check:ci-dead-service-methods | quality-content / Dead service methods | yes | no | no |
| check:ci-dead-translation-keys | quality-i18n / i18n | yes | no | no |
| check:ci-decision-ids | quality-branch / Decision ids | yes | no | no |
| check:ci-design-tree | quality-code / Design tree | yes | no | no |
| check:ci-devbox-exec | quality-code / Devbox exec invocation | yes | no | no |
| check:ci-devcontainer-pins | quality-go / Check devcontainer pin upstream freshness | yes | no | no |
| check:ci-devcontainer-scripts | quality-code / Devcontainer script stderr visibility | yes | no | no |
| check:ci-dkim-notify | quality-content / DKIM notify DNS | yes | no | no |
| check:ci-doc-region-parity | quality-code / Doc region parity | yes | no | no |
| check:ci-docker-image-freshness | quality-content / Docker image freshness | yes | no | no |
| check:ci-docker-npm-pins | quality-code / Dockerfile npm pins | yes | no | no |
| check:ci-dockerfile-mirror-resilience | quality-static / Dockerfile mirror resilience | yes | no | no |
| check:ci-docs-browse-invariants | quality-content / Docs browse invariants | yes | no | no |
| check:ci-docs-copy-units | quality-content / Docs code-block copy units | yes | no | no |
| check:ci-docs-render-parity | quality-www-build / Docs render parity | yes | yes | no |
| check:ci-docs-structure-parity | quality-i18n / Docs structure parity | yes | no | no |
| check:ci-docs-thumb-coverage | quality-content / Docs thumbnail coverage | yes | no | no |
| check:ci-domain-partition | quality-code / scripts/ domain partition | yes | no | no |
| check:ci-drill-verdicts | quality-static / Drill verdict logic | yes | no | no |
| check:ci-e2e-case-blind | quality-content / E2E case-blind assertions | yes | no | no |
| check:ci-e2e-coverage | quality-content / Check E2E test coverage for all renet functions | yes | no | no |
| check:ci-e2e-skip-hygiene | quality-content / Check E2E skip hygiene (no collected-then-skipped suites) | yes | no | no |
| check:ci-editorconfig | quality-static / EditorConfig | yes | yes | no |
| check:ci-em-dash-surfaces | quality-i18n / i18n | yes | no | no |
| check:ci-embed-arch-parity | quality-go / Check embed arch parity | yes | no | no |
| check:ci-embed-asset-freshness | quality-go / Check embed-asset upstream freshness | yes | no | no |
| check:ci-embed-asset-versions | quality-go / Check embedded asset versions match their pins | yes | yes | no |
| check:ci-embed-credits | quality-go / Check embed credits consistency | yes | no | no |
| check:ci-enumeration-vacuity | quality-code / Enumeration vacuity | yes | no | no |
| check:ci-env-file-adoption | quality-static / Env file adoption | yes | no | no |
| check:ci-env-manifest | quality-static / Env manifest | yes | no | no |
| check:ci-environment-names | quality-static / Environment names | yes | no | no |
| check:ci-external-links | quality-content / External links | yes | yes | no |
| check:ci-fetch-integrity | quality-code / CI fetch integrity | yes | no | no |
| check:ci-fetch-retry | quality-code / Fetch retry | yes | no | no |
| check:ci-fixture-event-timestamps | quality-code / Fixture event timestamps | yes | no | no |
| check:ci-form-validation | test: .ci/rediacc_ci/tests/gates/test_gate_form_validation.py | yes | no | no |
| check:ci-format-scope | quality-code / Format command covers its config's scope | yes | yes | no |
| check:ci-gate-bind | quality-code / Gate binding | yes | no | no |
| check:ci-gate-cwd-independence | quality-code / Gate cwd independence | yes | no | no |
| check:ci-gate-id-convention | quality-static / Gate registration follows the gates/ convention | yes | no | no |
| check:ci-gate-manifest | quality-code / Gate manifest self-consistency | yes | no | no |
| check:ci-gate-prerequisites | quality-code / Gate prerequisites | yes | no | no |
| check:ci-gate-reachability-coverage | quality-static / Gate-reachability probe agrees with registrations | yes | no | no |
| check:ci-gate-test-real-file-plants | quality-code / Gate-test real-file plants | yes | no | no |
| check:ci-gates-lock | quality-code / Gates lock | yes | no | no |
| check:ci-gen-manifest | quality-code / Generated manifest regions | yes | no | no |
| check:ci-git-history-depth | quality-static / Git history depth | yes | no | no |
| check:ci-git-op-conditionals | quality-code / Git-op conditional guards | yes | no | no |
| check:ci-git-tool-safety | quality-code / Mediated git tool stays lease-only and dry-run by default | yes | no | no |
| check:ci-go-deps | quality-go / Check Go dependency freshness | yes | no | no |
| check:ci-go-module-sync | quality-go / Check Go module sync against the renet worktree | yes | no | no |
| check:ci-go-tool-path | quality-code / Go tool PATH | yes | no | no |
| check:ci-greenlight-closures | quality-code / Greenlight closure paths | yes | no | no |
| check:ci-guard-feature-completeness | quality-static / Guard feature completeness | yes | no | no |
| check:ci-guard-mention-anchoring | quality-code / Guard mention anchoring | yes | no | no |
| check:ci-guard-mutations | quality-packages / Guard mutations | yes | yes | no |
| check:ci-hint-corpus | quality-content / Behavioral hints can actually fire | yes | no | no |
| check:ci-hook-cross-os | quality-static / Hook cross-OS seams | yes | no | no |
| check:ci-hook-exec-baseline | quality-static / Hook exec baseline | yes | no | no |
| check:ci-hook-integrity | quality-code / Hook integrity | yes | no | no |
| check:ci-hooks-resolvable | quality-static / Hooks resolvable | yes | no | no |
| check:ci-host-toolchain-coverage | quality-code / Host toolchain runtime coverage | yes | no | no |
| check:ci-hydration-clean | test: .ci/rediacc_ci/tests/gates/test_gate_hydration_clean.py | yes | no | no |
| check:ci-i18n-account-email-templates | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-cli-help-render | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-cli-key-usage | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-command-parity | quality-i18n / i18n command parity | yes | no | no |
| check:ci-i18n-completeness | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-cross-locale | quality-i18n / i18n cross-locale | no | no | no |
| check:ci-i18n-cross-locale-core | quality-i18n / i18n cross-locale | yes | no | no |
| check:ci-i18n-docs-inline | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-docs-render-parity | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-docs-untranslated | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-hardcoded-strings | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-hashes | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-ledger-growth | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-locale-only | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-media | quality-i18n / Tutorial media | yes | no | no |
| check:ci-i18n-naturalization | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-page-locale-imports | quality-i18n / i18n | yes | yes | no |
| check:ci-i18n-placeholders | quality-i18n / i18n placeholders | yes | no | no |
| check:ci-i18n-untranslated | quality-i18n / i18n untranslated | yes | no | no |
| check:ci-i18n-value-types | quality-content / i18n value types match English | yes | no | no |
| check:ci-i18n-www-cli-docs | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-www-comparison-refs | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-www-content | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-www-content-accuracy | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-www-docs-cli-usage | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-www-landing-cli-usage | quality-i18n / i18n | yes | no | no |
| check:ci-i18n-www-translation-freshness | quality-i18n / i18n | yes | no | no |
| check:ci-illustration-contract | quality-content / Dead CSS | yes | no | no |
| check:ci-inner-timeout-reachable | quality-code / Inner kill timers are reachable | yes | no | no |
| check:ci-install-sh-config | quality-static / install.sh config tests | yes | no | no |
| check:ci-install-table | quality-static / Install table | yes | no | no |
| check:ci-job-aggregation | quality-code / CI job aggregation | yes | no | no |
| check:ci-jq-boolean-default | quality-code / jq boolean defaults | yes | no | no |
| check:ci-judged-rule-wiring | quality-code / Judged rule wiring | yes | no | no |
| check:ci-knip-blockers | quality-code / knip BLOCKER reasons | yes | no | no |
| check:ci-label-inventory | test: .ci/rediacc_ci/tests/gates/test_gate_label_inventory.py | yes | no | no |
| check:ci-label-refs | test: .ci/rediacc_ci/tests/gates/test_gate_label_references.py | yes | no | no |
| check:ci-landmarks | quality-www-build / Landmarks | yes | yes | no |
| check:ci-language-policy | quality-static / Language policy | yes | no | no |
| check:ci-layout-overflow | test: .ci/rediacc_ci/tests/gates/test_gate_layout_overflow.py | yes | no | no |
| check:ci-lint-rule-liveness | quality-content / Enabled lint rules can actually fire | yes | yes | no |
| check:ci-lint-rule-units | quality-content / Lint rule unit specs | yes | no | no |
| check:ci-lint-scope-coverage | quality-code / Every source file reaches a linter | yes | yes | no |
| check:ci-locale-config-divergence | quality-i18n / i18n cross-locale | yes | no | no |
| check:ci-locale-currency | quality-i18n / i18n | yes | no | no |
| check:ci-locale-de-contamination | quality-i18n / i18n cross-locale | yes | no | no |
| check:ci-locale-sources | quality-i18n / Locale sources | yes | no | no |
| check:ci-locale-tutorial-assets | quality-content / Validate per-locale tutorial video assets exist | yes | no | no |
| check:ci-lockfile | quality-code / Lockfile | yes | yes | no |
| check:ci-merge-method-prose | quality-code / Instruction files do not prescribe a rejected merge method | yes | no | no |
| check:ci-mutate-check | quality-static / Mutation runner self-test | yes | no | no |
| check:ci-native-rebuild | quality-code / Native modules rebuilt after every root install | yes | no | no |
| check:ci-naturalization-model-policy | quality-code / Naturalization model policy | yes | no | no |
| check:ci-nis2-quotes | quality-content / Verify NIS2 directive quotations match the official source | yes | no | no |
| check:ci-no-client-key-composition | quality-code / No client-side key composition | yes | no | no |
| check:ci-no-inline-python | quality-static / No inline Python in JS/TS | yes | no | no |
| check:ci-no-otlp-creds | build-renet / Assert no OTLP credentials baked into the built binaries | yes | yes | no |
| check:ci-npmrc | quality-code / Block legacy-peer-deps workarounds | yes | no | no |
| check:ci-overrides-reasons | quality-security / BLOCKER validator — package.json overrides | yes | no | no |
| check:ci-package-key-budget | quality-code / Package key budget | yes | no | no |
| check:ci-page-density | quality-www-build / Page density | yes | yes | no |
| check:ci-page-locale-imports | quality-i18n / Page locale imports | yes | no | no |
| check:ci-parity | quality-content / Validate parity between the local gate set and the CI quality surface | yes | no | no |
| check:ci-paths-origin | quality-code / Paths-origin provenance | yes | no | no |
| check:ci-pathspec-scope | quality-static / Pathspec scope | yes | no | no |
| check:ci-peer-deps | quality-code / Verify no peer dependency conflicts | yes | no | no |
| check:ci-pipefail-grep-q | quality-code / No racing pipefail/grep -q detectors | yes | yes | no |
| check:ci-plan-boxes | quality-branch / Plan checkbox ledger | yes | no | no |
| check:ci-plan-citations | quality-branch / Plan citations | yes | no | no |
| check:ci-plan-folders | quality-branch / Plan folders and retention | yes | no | no |
| check:ci-plan-housekeeping | quality-i18n / Plan file housekeeping | yes | no | no |
| check:ci-plan-implementation | quality-branch / Plan implementation clock | yes | no | no |
| check:ci-plan-record | quality-branch / Plan records | yes | no | no |
| check:ci-plant-proofs | quality-static / Control plant proofs | yes | no | no |
| check:ci-player-css-scope | quality-www-build / Player CSS scope | yes | yes | no |
| check:ci-policy-inventory | quality-static / Policy inventory | yes | no | no |
| check:ci-pool-writer-safety | quality-static / Pool-registered tests do not write the real tree | yes | no | no |
| check:ci-pr-epic-block | quality-code / PR epic block matches the published worklist | yes | no | no |
| check:ci-pr-head-ref-completeness | quality-code / PR_HEAD_REF completeness | yes | no | no |
| check:ci-pr-task-trailers | quality-code / Every commit names its epic | yes | no | no |
| check:ci-pricing-consistency | quality-content / Pricing consistency | yes | no | no |
| check:ci-probe-parity | quality-static / Capability-probe parity | yes | no | no |
| check:ci-profiler-coverage | test: .ci/rediacc_ci/tests/gates/test_gate_profiler_coverage.py | yes | no | no |
| check:ci-prose-style | quality-content / Check prose style (the work, not the person) | yes | yes | no |
| check:ci-proxy-cli-manifest | local-only | yes | no | no |
| check:ci-proxy-docker-prepull | local-only | yes | yes | no |
| check:ci-proxy-ensure-nfpm | local-only | yes | no | no |
| check:ci-proxy-go-unit | local-only | yes | yes | no |
| check:ci-proxy-license-e2e | local-only | yes | yes | no |
| check:ci-proxy-linux-packages | local-only | yes | no | no |
| check:ci-proxy-ops-host-check | local-only | yes | no | no |
| check:ci-proxy-rdc-update | local-only | yes | no | no |
| check:ci-pytest | quality-security / Python package tests | yes | yes | no |
| check:ci-python-control-plants | quality-static / Python control plants | yes | no | no |
| check:ci-python-env-registry | quality-static / Python env registry | yes | no | no |
| check:ci-python-gate-deps | quality-static / Python gate deps | yes | no | no |
| check:ci-python-lint | quality-static / Python lint + format (ruff) | yes | no | no |
| check:ci-python-types | quality-static / Python types (mypy) | yes | yes | no |
| check:ci-quality-complete | quality-wiring / Quality shard aggregation | yes | no | no |
| check:ci-quality-gates | quality-security / Quality-gate unit tests | no | no | no |
| check:ci-rdc-native | quality-static / rdc.sh wrapper budget and --native arms | yes | no | no |
| check:ci-rdc-sh-env | quality-static / rdc.sh env tests | yes | no | no |
| check:ci-recovery-context | quality-go / Check recovery functions get an uncancellable context | yes | no | no |
| check:ci-redirect-integrity | quality-www-build / Redirects | yes | yes | no |
| check:ci-redirects | quality-www-build / Redirects | no | yes | no |
| check:ci-regions-sync | test: .ci/rediacc_ci/tests/gates/test_gate_regions_sync.py | yes | no | no |
| check:ci-release-bump-skip | test: .ci/scripts/quality/check_release_bump_skip.py | yes | no | no |
| check:ci-release-key-canonical | quality-security / Release key canonical | yes | no | no |
| check:ci-release-signing-coverage | quality-security / Release signing coverage | yes | no | no |
| check:ci-renet | quality-go / Run renet quality | yes | yes | no |
| check:ci-renet-tiers | local-only | yes | no | no |
| check:ci-renet-types | quality-go / Check renet types freshness | yes | no | no |
| check:ci-resprofile | quality-branch / Resource profile (previous run's captures) | yes | no | no |
| check:ci-retention-knob-parity | quality-code / Retention knob parity | yes | no | no |
| check:ci-retired-commands | quality-content / Retired commands in docs | yes | no | no |
| check:ci-review-cap-coherence | quality-static / Review cap is measured coherently | yes | no | no |
| check:ci-review-prompt-render | quality-code / Review prompt render | yes | no | no |
| check:ci-review-turn-capacity | quality-static / Review turn budget cannot starve a routed review | yes | no | no |
| check:ci-rubric-calibration | quality-code / Rubric calibration | yes | no | no |
| check:ci-runner-advice | quality-static / Runner sizing advice | yes | no | no |
| check:ci-runner-selftest | quality-code / CI runner selftest | yes | no | no |
| check:ci-runtime-imports-are-deps | quality-code / Runtime imports are dependencies | yes | no | no |
| check:ci-scans-tracked-paths | quality-static / CI executes only tracked paths | yes | no | no |
| check:ci-schema-call-sites | quality-static / Schema call sites | yes | no | no |
| check:ci-schema-coverage | quality-code / Schema coverage | yes | no | no |
| check:ci-scope-completeness | quality-security / Scope completeness | yes | no | no |
| check:ci-scope-scripts-reachability | quality-security / Scope map, reachable scripts/ paths force full CI | yes | yes | no |
| check:ci-script-exec-bit | quality-code / Block non-executable invoked scripts | yes | yes | no |
| check:ci-search-index | quality-i18n / Search index | yes | no | no |
| check:ci-secret-reachability | quality-security / Secret reachability | yes | no | no |
| check:ci-secret-scope | quality-security / Secret scope | yes | no | no |
| check:ci-secret-supply | quality-static / Secret supply | yes | no | no |
| check:ci-security-audit | quality-security / Audit | yes | yes | no |
| check:ci-sentence-wrapping | quality-content / Sentence wrapping | yes | no | no |
| check:ci-seo | quality-www-build / SEO | no | yes | no |
| check:ci-seo-core | quality-www-build / SEO | yes | yes | no |
| check:ci-setup-idempotency | quality-code / Setup path idempotency | yes | no | no |
| check:ci-setup-port-parity | quality-static / Setup port parity | yes | no | no |
| check:ci-shape-duplication | quality-code / Shape duplication | yes | no | no |
| check:ci-shared-constant-duplication | quality-code / Shared constant duplication | yes | no | no |
| check:ci-shared-esm-resolvable | quality-packages / Shared ESM resolvable | yes | no | no |
| check:ci-shell-commands | quality-static / Shell commands exist on the runner image | yes | no | no |
| check:ci-shell-declared-commands | quality-code / CI scripts declare the binaries they execute | yes | no | no |
| check:ci-shell-format | quality-static / Shell format | yes | no | no |
| check:ci-shell-lint | quality-static / Shell lint | yes | yes | no |
| check:ci-shell-size | quality-code / Shell file size | yes | no | no |
| check:ci-silent-failures | quality-static / Silent-failure patterns | yes | no | no |
| check:ci-skill-size | quality-content / Self-improving skill size | yes | no | no |
| check:ci-solution-video-engine | quality-content / Validate solution narration engine is current | yes | no | no |
| check:ci-solution-videos | quality-content / Validate localized solution videos exist | yes | no | no |
| check:ci-ssr-locale | quality-www-build / SSR locale | yes | yes | no |
| check:ci-staging-tag-guard | quality-security / Staging tag guard | yes | no | no |
| check:ci-step-env-parity | quality-code / Step env parity | yes | no | no |
| check:ci-subscription-schema | quality-go / Check subscription schema consistency | yes | no | no |
| check:ci-suppression-liveness | quality-security / Suppression liveness — are our allowlist entries still needed? | yes | no | no |
| check:ci-svg-theme-reach | quality-content / SVG theme reach | yes | no | no |
| check:ci-swallowed-failures | quality-code / Swallowed failures | yes | no | no |
| check:ci-syncpack-reasons | quality-security / BLOCKER validator — syncpack versionGroups | yes | no | no |
| check:ci-syncpack-sources | quality-code / syncpack source coverage | yes | no | no |
| check:ci-test-account-web | quality-packages / Account portal unit tests | yes | yes | no |
| check:ci-test-file-orphans | quality-security / Test-file orphan check | yes | no | no |
| check:ci-test-gate-wiring | quality-content / Test-gate wiring | yes | no | no |
| check:ci-test-scripts-reachable | quality-code / Test suites are CI-reachable | yes | no | no |
| check:ci-timeout-headroom | quality-static / CI job timeout headroom | yes | no | no |
| check:ci-tmpfs-health | quality-code / Tmpfs health | yes | no | no |
| check:ci-toolchain-env-dockerfile-sync | quality-code / Toolchain env/Dockerfile sync | yes | no | no |
| check:ci-toolchain-pins | quality-code / Toolchain pins | yes | yes | no |
| check:ci-tracked-credentials | quality-security / Tracked credentials | yes | no | no |
| check:ci-tracked-sidecars | quality-static / Tracked runtime sidecars | yes | no | no |
| check:ci-trap-registry | quality-code / Trap registry dispositions | yes | no | no |
| check:ci-tree-shape | quality-static / Tree shape | yes | no | no |
| check:ci-tutorial-caption-sync | quality-content / Validate published tutorial word-timing sync (real ASR alignment, not estimated) | yes | no | no |
| check:ci-tutorial-card-fonts | quality-content / Validate tutorial card fonts cover every locale | yes | no | no |
| check:ci-tutorial-casts | quality-content / Block fallback hacks and error output in tutorial recordings | yes | no | no |
| check:ci-tutorial-cli-validity | quality-content / Tutorial CLI validity | yes | no | no |
| check:ci-tutorial-commands | quality-content / Validate tutorial storyboard commands against the live CLI | yes | no | no |
| check:ci-tutorial-healthcheck-headroom | quality-packages / Tutorial healthcheck headroom | yes | no | no |
| check:ci-tutorial-no-skips | quality-content / Tutorials cannot skip themselves | yes | no | no |
| check:ci-tutorial-noninteractive | quality-content / Validate tutorial commands are non-interactive | yes | no | no |
| check:ci-tutorial-parity | quality-content / Validate tutorial cast/storyboard/transcript/mdx parity | yes | no | no |
| check:ci-tutorial-render-queue | test: .ci/rediacc_ci/tests/gates/test_gate_tutorial_render_queue.py | yes | no | no |
| check:ci-typecheck-scope-coverage | quality-code / Typecheck scope coverage | yes | yes | no |
| check:ci-unverified-downloads | quality-security / Check every Dockerfile download is cryptographically verified | yes | no | no |
| check:ci-vendored-blocker-derivation | quality-static / Vendored blocker derivation | yes | no | no |
| check:ci-video-player-invariants | quality-content / Video player invariants | yes | no | no |
| check:ci-viewport-unit-mixing | quality-content / Dead CSS | yes | no | no |
| check:ci-w7p5a-real-run-blockers | quality-static / W7P5-a real-run blocklist | yes | no | no |
| check:ci-watch-recipe | quality-code / CI-watch recipe has one source | yes | no | no |
| check:ci-worker-secret-names | quality-code / Worker secret names | yes | no | no |
| check:ci-workflow-env-provision | quality-static / Workflow env provision | yes | no | no |
| check:ci-workflow-gates | quality-code / Workflow structural gates | yes | no | no |
| check:ci-workflow-invariants | test: .ci/rediacc_ci/tests/gates/test_gate_ci_workflow_invariants.py | yes | no | no |
| check:ci-workflow-orphan-step-keys | quality-code / Workflow orphan step keys | yes | no | no |
| check:ci-workflow-submodule-deps | quality-static / Workflow submodule deps | yes | no | no |
| check:ci-workflows | quality-code / Workflow banned patterns | yes | yes | no |
| check:ci-worklist-env-registry | quality-static / Worklist env registry | yes | no | no |
| check:ci-worklist-event-builders | quality-code / Worklist event builders | yes | no | no |
| check:ci-worklist-path-resolution | quality-code / Worklist path resolution | yes | no | no |
| check:ci-www-build-token | quality-code / www build token | yes | no | no |
| check:cli-docs | quality-i18n / i18n | yes | no | no |
| check:cli-examples | quality-code / CLI examples | yes | yes | no |
| check:deps | quality-content / External dependency freshness | yes | yes | no |
| check:format | quality-code / Format | yes | no | no |
| check:i18n | quality-i18n / i18n | no | yes | no |
| check:i18n:key-usage | quality-i18n / i18n | yes | yes | no |
| check:lint | quality-code / Lint | no | yes | no |
| check:lint:account | quality-code / Lint | yes | yes | no |
| check:lint:cli | quality-code / Lint | yes | yes | no |
| check:lint:tooling | quality-code / Lint | yes | yes | no |
| check:lint:web | quality-code / Lint | yes | yes | no |
| check:test-cli | quality-packages / Run CLI unit tests | yes | yes | no |
| check:test-e2e-unit | quality-packages / Run e2e-tests unit suite | yes | no | no |
| check:test-provisioning | quality-packages / Run provisioning unit tests | yes | no | no |
| check:test-shared | quality-packages / Run shared package tests | yes | no | no |
| check:test-workers | quality-www-build / Worker unit tests (workers/www) | yes | yes | no |
| check:test-www | quality-packages / Run www unit tests | yes | no | no |
| check:test:tutorial-player | quality-packages / Tutorial player release gate | yes | yes | no |
| check:types | quality-code / TypeScript | yes | yes | no |
| check:version | quality-code / Versions | yes | no | no |
| gate-test:blocker-golden-corpus | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-r2 | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:run-sh | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:runner-advice | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:toolchain | quality-security / Quality-gate unit tests | yes | no | yes |
| gen:docs | local-only | no | no | no |
| gen:gates-lock | local-only | no | no | no |
| lint:unused | quality-code / Unused exports (knip) | yes | yes | no |
| test:install-script | quality-static / Install-script tests | yes | no | no |
| test:write-once-guard | quality-static / Write-once guard tests | yes | no | no |

349 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## Hook guards

<!-- >>> gen-docs: hook-guards -->
<!-- Chains come from the `hooks` wiring in .claude/settings.json, not from a hand-kept chain -->
<!-- list: check-hook-integrity.sh's own comment records post-bash missing from its array -->
<!-- until 2026-08-28, which left two registered guards outside every inventory. A guard in a -->
<!-- wired directory that no event names is listed here with Reached = (nothing), which is the -->
<!-- interesting residue: a file beside the live guards that nothing can reach. -->

Scans: the `hooks` wiring in .claude/settings.json, closed transitively over the tracked files under .claude/hooks/ and .claude/rediacc_hooks/ (.claude/oracles/ excluded on purpose: those twins are wired to no event by design).

| Hook file | Events | Reached | Language |
|---|---|---|---|
| .claude/hooks/chain-head.sh | PostToolUse, PreToolUse | settings.json | sh |
| .claude/hooks/context/band-notice.py | (none) | via .claude/rediacc_hooks/lifecycle.py | py |
| .claude/hooks/context/ctx_budget.py | (none) | via .claude/hooks/context/band-notice.py | py |
| .claude/hooks/context/epoch-reset.py | (none) | via .claude/hooks/context/ctx_budget.py | py |
| .claude/hooks/context/onboard.py | (none) | via .claude/hooks/context/ctx_budget.py | py |
| .claude/hooks/context/precompact-floor.py | PreCompact | settings.json | py |
| .claude/hooks/context/test-context-bands.py | (none) | (nothing) | py |
| .claude/hooks/lib/sanctioned.py | (none) | via .claude/rediacc_hooks/guards/block_adhoc_sanctioned.py | py |
| .claude/hooks/post-bash/cancel_old_ci.py | (none) | via .claude/rediacc_hooks/lifecycle.py | py |
| .claude/hooks/post-bash/refresh_pr_body.py | (none) | via .claude/rediacc_hooks/lifecycle.py | py |
| .claude/hooks/profile/bash_env.sh | (none) | (nothing) | sh |
| .claude/hooks/profile/py/sitecustomize.py | (none) | via .claude/hooks/stop/wl_resprofile.py | py |
| .claude/hooks/stop/calibrate-judge-rules.py | (none) | (nothing) | py |
| .claude/hooks/stop/test-adhoc-watch.py | (none) | via .claude/rediacc_hooks/tests/test_hooks_delegates.py | py |
| .claude/hooks/stop/test-always-tier.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/test-backlog.py | (none) | via .claude/hooks/stop/test-planenforce.py | py |
| .claude/hooks/stop/test-bgsweep.py | (none) | (nothing) | py |
| .claude/hooks/stop/test-completion-evidence.py | (none) | (nothing) | py |
| .claude/hooks/stop/test-deflect.py | (none) | (nothing) | py |
| .claude/hooks/stop/test-judge-schema.py | (none) | via .claude/rediacc_hooks/tests/test_hooks_delegates.py | py |
| .claude/hooks/stop/test-plan-status-parse.py | (none) | via .claude/rediacc_hooks/guards/block_plan_without_tasks.py | py |
| .claude/hooks/stop/test-planenforce.py | (none) | via .claude/hooks/stop/wl_planenforce.py | py |
| .claude/hooks/stop/test-planfile.py | (none) | via .claude/hooks/stop/test-planenforce.py | py |
| .claude/hooks/stop/test-planindex.py | (none) | via .claude/hooks/stop/wl_planindex.py | py |
| .claude/hooks/stop/test-planrec.py | (none) | via .claude/rediacc_hooks/tests/test_wl_identity.py | py |
| .claude/hooks/stop/test-popup.py | (none) | via .claude/hooks/stop/wl_popup.py | py |
| .claude/hooks/stop/test-reggate-ledger.py | (none) | (nothing) | py |
| .claude/hooks/stop/test-teammate-idle.py | (none) | via .claude/rediacc_hooks/tests/test_hooks_delegates.py | py |
| .claude/hooks/stop/wl_admit.py | (none) | via .claude/rediacc_hooks/tests/test_hooks_delegates.py | py |
| .claude/hooks/stop/wl_agents.py | (none) | via .claude/rediacc_hooks/guards/block_settled_questions.py | py |
| .claude/hooks/stop/wl_backlog.py | (none) | via .claude/hooks/stop/test-planenforce.py | py |
| .claude/hooks/stop/wl_bgsweep.py | (none) | via .claude/rediacc_hooks/tests/test_wl_identity.py | py |
| .claude/hooks/stop/wl_bravedefault.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_checklist.py | (none) | via .claude/hooks/stop/worklist.py | py |
| .claude/hooks/stop/wl_checks.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_ci.py | (none) | via .claude/hooks/stop/test-adhoc-watch.py | py |
| .claude/hooks/stop/wl_claimcheck.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_classsweep.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_core.py | (none) | via .claude/hooks/context/onboard.py | py |
| .claude/hooks/stop/wl_deflect.py | (none) | via .claude/hooks/stop/wl_bgsweep.py | py |
| .claude/hooks/stop/wl_epic.py | (none) | via .claude/hooks/stop/worklist.py | py |
| .claude/hooks/stop/wl_git.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_hints.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_histfirst.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_judge.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_lineage.py | (none) | via .claude/hooks/stop/wl_core.py | py |
| .claude/hooks/stop/wl_liveness.py | (none) | via .claude/hooks/stop/test-teammate-idle.py | py |
| .claude/hooks/stop/wl_planenforce.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_planfid.py | (none) | via .claude/hooks/stop/test-planrec.py | py |
| .claude/hooks/stop/wl_planfile.py | (none) | via .claude/hooks/stop/test-planrec.py | py |
| .claude/hooks/stop/wl_planindex.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_planrec.py | (none) | via .claude/hooks/stop/test-planrec.py | py |
| .claude/hooks/stop/wl_popup.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_proc.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_profile.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_proofcheck.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_reggate.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_report.py | SubagentStop | settings.json | py |
| .claude/hooks/stop/wl_requests.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_resprofile.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_ressample.py | (none) | via .claude/hooks/stop/wl_profile.py | py |
| .claude/hooks/stop/wl_roundlog.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/wl_rules.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_shapedup.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/hooks/stop/wl_store.py | (none) | via .claude/hooks/context/ctx_budget.py | py |
| .claude/hooks/stop/wl_wait.py | (none) | via .claude/hooks/stop/wl_checks.py | py |
| .claude/hooks/stop/worklist.py | Stop, TeammateIdle | settings.json | py |
| .claude/hooks/stop/worklist_messages.py | (none) | via .claude/hooks/stop/wl_agents.py | py |
| .claude/hooks/trapguard/dispatch.py | (none) | via .claude/hooks/chain-head.sh | py |
| .claude/hooks/why-on-edit.py | (none) | via .claude/hooks/stop/test-planrec.py | py |
| .claude/rediacc_hooks/__init__.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/rediacc_hooks/dispatch.py | (none) | via .claude/hooks/chain-head.sh | py |
| .claude/rediacc_hooks/execcount.py | (none) | (nothing) | py |
| .claude/rediacc_hooks/guards/__init__.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/rediacc_hooks/guards/block_adhoc_sanctioned.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_admin_merge.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_agent_browser_repo_output.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_agent_state_shape.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_bash_write_to_running_script.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_binary_deploy.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_blanket_git_add.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_ci_polling.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_ci_reverse_poll.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_cli_bundle.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_commit_meta.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_compacted_plan_edit.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_destructive_git_restore.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_edit_of_running_script.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_git_amend.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_git_empty_commit.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_git_force_push.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_host_toolchain_run.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_inline_python.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_inline_workflow_run.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_long_sleep.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_merge_with_unpushed.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_nondraft_pr_create.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_nonstandard_branch_name.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_pathspecless_git_commit.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_plan_without_tasks.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_premature_ready.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_prose_style_commit.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_prose_style_edit.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_protected_files.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_push_to_protected_branch.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_raw_pr_body_edit.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_roundlog_truncate.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_roundlog_write.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_second_open_pr.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_self_matching_pgrep.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_settled_questions.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_shell_background_waiter.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_ssh_docker.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_ssh_file_write.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_stale_pr_branch_date.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_suppressions.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_unlinked_commit_author.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_unproven_bulk_transform.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_unsatisfiable_pid_wait.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_untagged_commit.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_unverified_push.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/block_worktree_add.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/test-block_destructive_git_restore.py | (none) | (nothing) | py |
| .claude/rediacc_hooks/guards/test-block_git_amend.py | (none) | (nothing) | py |
| .claude/rediacc_hooks/guards/test-block_host_toolchain_run.py | (none) | (nothing) | py |
| .claude/rediacc_hooks/guards/test-block_prose_style_commit.py | (none) | via .claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py | py |
| .claude/rediacc_hooks/guards/test-block_prose_style_edit.py | (none) | via .claude/rediacc_hooks/guards/block_prose_style_edit.py | py |
| .claude/rediacc_hooks/guards/test-block_push_to_protected_branch.py | (none) | via .claude/rediacc_hooks/tests/test_hooks_delegates.py | py |
| .claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py | (none) | via .claude/rediacc_hooks/guards/block_unproven_bulk_transform.py | py |
| .claude/rediacc_hooks/guards/test-block_unsatisfiable_pid_wait.py | (none) | via .claude/rediacc_hooks/guards/block_unsatisfiable_pid_wait.py | py |
| .claude/rediacc_hooks/guards/test-block_unverified_push.py | (none) | via .claude/rediacc_hooks/guards/test-block_unproven_bulk_transform.py | py |
| .claude/rediacc_hooks/guards/test-warn_staged_shape_duplication.py | (none) | via .claude/rediacc_hooks/guards/warn_staged_shape_duplication.py | py |
| .claude/rediacc_hooks/guards/warn_hook_change.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/warn_remote_drift.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/warn_staged_shape_duplication.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/warn_stale_index.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/guards/warn_submodule_deletions.py | (none) | via dispatch.py (glob) | py |
| .claude/rediacc_hooks/hookio.py | (none) | via .claude/hooks/post-bash/cancel_old_ci.py | py |
| .claude/rediacc_hooks/lifecycle.py | PostCompact, PostToolUse, SessionStart | settings.json | py |
| .claude/rediacc_hooks/proc.py | (none) | via .claude/hooks/post-bash/cancel_old_ci.py | py |
| .claude/rediacc_hooks/run_tests.py | (none) | via .claude/rediacc_hooks/hookio.py | py |
| .claude/rediacc_hooks/shellscan.py | (none) | via .claude/rediacc_hooks/guards/block_adhoc_sanctioned.py | py |
| .claude/rediacc_hooks/tests/__init__.py | (none) | via .claude/hooks/stop/test-judge-schema.py | py |
| .claude/rediacc_hooks/tests/corpus.py | (none) | via .claude/hooks/context/onboard.py | py |
| .claude/rediacc_hooks/tests/guardcorpus.py | (none) | via .claude/rediacc_hooks/tests/corpus.py | py |
| .claude/rediacc_hooks/tests/hookblocks.py | (none) | via .claude/rediacc_hooks/tests/test_hooks_fixtures.py | py |
| .claude/rediacc_hooks/tests/hookcases.py | (none) | via .claude/rediacc_hooks/tests/hookblocks.py | py |
| .claude/rediacc_hooks/tests/hooklabels.py | (none) | via .claude/rediacc_hooks/tests/hookblocks.py | py |
| .claude/rediacc_hooks/tests/test_dispatch.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_guards_differential.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_hooks_delegates.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_hooks_fixtures.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_hooks_procs.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_hooks_static.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_hooks_trapguard.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_hooks_wiring.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_post_bash_differential.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_proc.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_settings_collapse.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_shellscan_differential.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_advisories_rotation.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_agent_docs_and_focus.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_agent_session_archival.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_background_waits.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_cadence.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_checklists.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_ci_queue_and_mail.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_ci_status.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_core_blocking.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_drift_loops_freshness.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_event_store.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_first_touch.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_guide_and_deferrals.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_hints.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_identity.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_idle_and_evidence.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_lineage.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_migrate.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_plan_fidelity.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_poll_and_waiting.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_priority_ladder.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_regression_gate.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_report_inbox.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_report_queue.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_requests.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_state_document.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_stuck_and_blockers.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_triage_and_plans.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/test_wl_waiter_controls.py | (none) | via pytest (testpaths) | py |
| .claude/rediacc_hooks/tests/wlfix.py | (none) | via .claude/hooks/stop/wl_popup.py | py |

190 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## Suppression mechanisms

<!-- >>> gen-docs: suppressions -->
<!-- The predicate is "carries a BLOCKER: line and is not source or prose", so a new allowlist -->
<!-- appears here the moment it exists. There is deliberately no Readers column: a grep-derived -->
<!-- one was built and observed flipping mid-run when a peer session staged an unrelated file, -->
<!-- and this record has to stay diffable across waves in a shared checkout. -->

Scans: every tracked non-source, non-prose file carrying a `BLOCKER:` line.

| Mechanism | BLOCKER lines | Comment form |
|---|---|---|
| .ci/breakpoint/.breakpoint-drift-accept | 1 | prose only (no live entry) |
| .ci/config/actions-vars.json | 1 | JSON value |
| .ci/config/directive-quotes-allowlist.txt | 2 | prose only (no live entry) |
| .ci/config/docker-npm-pin-exclusions.json | 3 | JSON value |
| .ci/config/prose-style-rules.json | 7 | JSON value |
| .ci/config/secret-supply.json | 2 | JSON value |
| .ci/config/syncpack-source-exclusions.json | 8 | JSON value |
| .ci/policy/.audit-allowlist | 1 | prose only (no live entry) |
| .ci/policy/.audit-prod-allowlist | 6 | # comment |
| .ci/policy/.ci-parity-exempt | 10 | # comment |
| .ci/policy/.cli-i18n-orphan-allowlist | 6 | inline |
| .ci/policy/.dead-bash-allowlist | 13 | # comment |
| .ci/policy/.deps-upgrade-blocklist | 19 | inline |
| .ci/policy/.devcontainer-upgrade-blocklist | 1 | prose only (no live entry) |
| .ci/policy/.e2e-coverage-allowlist | 3 | # comment |
| .ci/policy/.embed-assets-upgrade-blocklist | 2 | # comment |
| .ci/policy/.go-deps-upgrade-blocklist | 4 | # comment |
| .ci/policy/.host-toolchain-exceptions | 1 | prose only (no live entry) |
| .ci/policy/.language-policy-allowlist | 19 | # comment |
| .ci/policy/.plan-housekeeping-allowlist | 1 | prose only (no live entry) |
| .ci/policy/.profiler-coverage-allowlist | 4 | # comment |
| .ci/policy/.runner-advice-allowlist | 1 | prose only (no live entry) |
| .ci/policy/.unverified-download-allowlist | 4 | # comment |
| .ci/policy/.w7p5a-real-run-blocklist | 20 | # comment |
| .ci/policy/.w7p5a-real-run-leg-blocklist | 7 | # comment |
| .ci/policy/hook-exec-baseline.json | 1 | JSON value |
| .ci/shadow/w7p2-go-deps.observations.jsonl | 2 | inline |
| .ci/shadow/w7p2-plan-housekeeping.observations.jsonl | 5 | inline |
| .ci/shadow/w7p2-profiler-coverage.observations.jsonl | 3 | inline |
| .ci/shadow/w7p5a-status.json | 28 | JSON value |
| .ci/shadow/w7p5b-blocker-validator.observations.jsonl | 2 | inline |
| .syncpackrc-reasons.json | 8 | JSON value |
| agent/ledgers/plan-investigation.jsonl | 2 | inline |
| knip.jsonc | 26 | // comment |
| package.json | 28 | JSON value |
| scripts/ci-runner/gates.lock.json | 23 | JSON value |
| scripts/data/shape-duplication-seed-advisory.json | 3 | JSON value |
| scripts/data/shape-duplication-seed.json | 10 | JSON value |

38 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## The .ci tree

<!-- >>> gen-docs: ci-tree -->
<!-- Tracked paths only. An untracked file is not yet part of the repository's contract, and a -->
<!-- record other waves diff against must not move when someone's scratch file appears. -->

Scans: every tracked path under .ci/, grouped by directory.

| Directory | Files | Extensions |
|---|---|---|
| .ci | 2 | .md 1, .sh 1 |
| .ci/breakpoint | 5 | (none) 1, .conf 1, .md 1, .sh 1, .sha256 1 |
| .ci/breakpoint/docker | 1 | (none) 1 |
| .ci/breakpoint/lib | 2 | .sh 2 |
| .ci/breakpoint/scripts | 20 | .sh 20 |
| .ci/breakpoint/workflow | 1 | .yml 1 |
| .ci/config | 34 | .json 27, .txt 4, .conf 1, .sh 1, .yaml 1 |
| .ci/docker | 1 | .sh 1 |
| .ci/docker/ci | 1 | .yml 1 |
| .ci/docker/render | 1 | (none) 1 |
| .ci/docker/service | 2 | .sh 1, .yml 1 |
| .ci/docker/web | 4 | .conf 2, (none) 1, .sh 1 |
| .ci/docs | 2 | .md 2 |
| .ci/keys | 1 | .asc 1 |
| .ci/legacy | 1 | .sh 1 |
| .ci/lib | 4 | .sh 4 |
| .ci/media | 11 | .sh 11 |
| .ci/media/tools | 2 | .sh 2 |
| .ci/media/tts | 2 | (none) 1, .toml 1 |
| .ci/policy | 23 | (none) 19, .json 3, .md 1 |
| .ci/prompts | 1 | .md 1 |
| .ci/rediacc_ci | 13 | .py 13 |
| .ci/rediacc_ci/build | 18 | .py 18 |
| .ci/rediacc_ci/ci | 18 | .py 18 |
| .ci/rediacc_ci/ci_signal | 2 | .py 2 |
| .ci/rediacc_ci/core | 27 | .py 27 |
| .ci/rediacc_ci/deploy | 29 | .py 29 |
| .ci/rediacc_ci/dev | 3 | .py 3 |
| .ci/rediacc_ci/diagnostics | 2 | .py 2 |
| .ci/rediacc_ci/docker | 6 | .py 6 |
| .ci/rediacc_ci/env | 2 | .py 2 |
| .ci/rediacc_ci/housekeeping | 7 | .py 7 |
| .ci/rediacc_ci/infra | 12 | .py 12 |
| .ci/rediacc_ci/ops | 3 | .py 3 |
| .ci/rediacc_ci/pr | 2 | .py 2 |
| .ci/rediacc_ci/private | 9 | .py 9 |
| .ci/rediacc_ci/proxies | 10 | .py 10 |
| .ci/rediacc_ci/quality | 100 | .py 100 |
| .ci/rediacc_ci/release | 25 | .py 25 |
| .ci/rediacc_ci/review | 6 | .py 6 |
| .ci/rediacc_ci/security | 10 | .py 10 |
| .ci/rediacc_ci/setup | 12 | .py 12 |
| .ci/rediacc_ci/tests | 283 | .py 283 |
| .ci/rediacc_ci/tests/data | 2 | .json 1, .yml 1 |
| .ci/rediacc_ci/tests/gates | 173 | .py 172, .fixture 1 |
| .ci/rediacc_ci/tests/goldens/actionlint | 17 | .golden 17 |
| .ci/rediacc_ci/tests/goldens/allowlist/bash-pairs | 17 | .golden 17 |
| .ci/rediacc_ci/tests/goldens/allowlist/corpus | 17 | .list 17 |
| .ci/rediacc_ci/tests/goldens/allowlist/reasons | 2 | .golden 2 |
| .ci/rediacc_ci/tests/goldens/allowlist/ts-records | 17 | .golden 17 |
| .ci/rediacc_ci/tests/goldens/announce-gate-skips | 13 | .golden 13 |
| .ci/rediacc_ci/tests/goldens/app-admin-perm | 7 | .golden 7 |
| .ci/rediacc_ci/tests/goldens/assert-channel-for-event | 27 | .golden 27 |
| .ci/rediacc_ci/tests/goldens/assert-install-methods-complete | 12 | .golden 12 |
| .ci/rediacc_ci/tests/goldens/branch | 2 | .golden 2 |
| .ci/rediacc_ci/tests/goldens/build-json | 11 | .golden 11 |
| .ci/rediacc_ci/tests/goldens/build-linux-packages | 14 | .golden 14 |
| .ci/rediacc_ci/tests/goldens/build-server | 16 | .golden 16 |
| .ci/rediacc_ci/tests/goldens/build-www | 9 | .golden 9 |
| .ci/rediacc_ci/tests/goldens/buildx-push-web | 18 | .golden 18 |
| .ci/rediacc_ci/tests/goldens/bws-env | 10 | .golden 10 |
| .ci/rediacc_ci/tests/goldens/cancel-older-runs | 28 | .golden 28 |
| .ci/rediacc_ci/tests/goldens/check-commands | 12 | .golden 12 |
| .ci/rediacc_ci/tests/goldens/ci-stop | 7 | .golden 7 |
| .ci/rediacc_ci/tests/goldens/ci-workflow-invariants | 19 | .golden 19 |
| .ci/rediacc_ci/tests/goldens/claude-attribution | 2 | .golden 2 |
| .ci/rediacc_ci/tests/goldens/claude-hooks | 2 | .golden 2 |
| .ci/rediacc_ci/tests/goldens/cleanup-cf-preview | 22 | .golden 22 |
| .ci/rediacc_ci/tests/goldens/cleanup-github-deployments | 14 | .golden 14 |
| .ci/rediacc_ci/tests/goldens/cleanup-pr-environments | 17 | .golden 17 |
| .ci/rediacc_ci/tests/goldens/cleanup-staging | 20 | .golden 20 |
| .ci/rediacc_ci/tests/goldens/cleanup-stale-d1 | 19 | .golden 19 |
| .ci/rediacc_ci/tests/goldens/collect-drill-diagnostics | 5 | .golden 5 |
| .ci/rediacc_ci/tests/goldens/compose-healthcheck-smoke-test | 62 | .golden 62 |
| .ci/rediacc_ci/tests/goldens/create-complete | 12 | .golden 12 |
| .ci/rediacc_ci/tests/goldens/create-e2e-env | 98 | .golden 98 |
| .ci/rediacc_ci/tests/goldens/create-manifest | 22 | .golden 22 |
| .ci/rediacc_ci/tests/goldens/decide-release-mode | 4 | .golden 4 |
| .ci/rediacc_ci/tests/goldens/derive-image-tag | 40 | .golden 40 |
| .ci/rediacc_ci/tests/goldens/derive-shadow-pass-list | 15 | .golden 15 |
| .ci/rediacc_ci/tests/goldens/dev-www | 9 | .golden 9 |
| .ci/rediacc_ci/tests/goldens/dispatch-watchdog | 48 | .golden 48 |
| .ci/rediacc_ci/tests/goldens/docker-prepull | 13 | .golden 13 |
| .ci/rediacc_ci/tests/goldens/docker-pull-ghcr | 20 | .golden 20 |
| .ci/rediacc_ci/tests/goldens/docker-run-in-image | 28 | .golden 28 |
| .ci/rediacc_ci/tests/goldens/gate-controls | 7 | .golden 7 |
| .ci/rediacc_ci/tests/goldens/gate-controls-tally | 5 | .golden 5 |
| .ci/rediacc_ci/tests/goldens/generate-cli-manifest | 36 | .golden 36 |
| .ci/rediacc_ci/tests/goldens/git-op-conditionals | 10 | .golden 10 |
| .ci/rediacc_ci/tests/goldens/hook-integrity | 3 | .golden 3 |
| .ci/rediacc_ci/tests/goldens/install-cli-global | 15 | .golden 15 |
| .ci/rediacc_ci/tests/goldens/install-script | 9 | .golden 9 |
| .ci/rediacc_ci/tests/goldens/label-inventory | 13 | .golden 13 |
| .ci/rediacc_ci/tests/goldens/label-references | 6 | .golden 6 |
| .ci/rediacc_ci/tests/goldens/pack-cli-npm | 15 | .golden 15 |
| .ci/rediacc_ci/tests/goldens/profiler-panel | 22 | .golden 22 |
| .ci/rediacc_ci/tests/goldens/proxy-cli-manifest | 2 | .golden 2 |
| .ci/rediacc_ci/tests/goldens/proxy-docker-prepull | 2 | .golden 2 |
| .ci/rediacc_ci/tests/goldens/python-lint | 8 | .golden 8 |
| .ci/rediacc_ci/tests/goldens/resolve-backfill-commit | 5 | .golden 5 |
| .ci/rediacc_ci/tests/goldens/resolved-threads | 6 | .golden 6 |
| .ci/rediacc_ci/tests/goldens/retag-image | 32 | .golden 32 |
| .ci/rediacc_ci/tests/goldens/retry-failed-runs | 22 | .golden 22 |
| .ci/rediacc_ci/tests/goldens/review-comments | 11 | .golden 11 |
| .ci/rediacc_ci/tests/goldens/review-report-replies | 9 | .golden 9 |
| .ci/rediacc_ci/tests/goldens/review-turn-capacity | 9 | .golden 9 |
| .ci/rediacc_ci/tests/goldens/run-account | 24 | .golden 24 |
| .ci/rediacc_ci/tests/goldens/run-external-gate | 21 | .golden 21 |
| .ci/rediacc_ci/tests/goldens/run-renet | 19 | .golden 19 |
| .ci/rediacc_ci/tests/goldens/scope-scripts-reachability | 7 | .golden 7 |
| .ci/rediacc_ci/tests/goldens/scope-shadow | 11 | .golden 11 |
| .ci/rediacc_ci/tests/goldens/set-image-tags | 10 | .golden 10 |
| .ci/rediacc_ci/tests/goldens/shellcheck | 17 | .golden 17 |
| .ci/rediacc_ci/tests/goldens/shfmt | 11 | .golden 11 |
| .ci/rediacc_ci/tests/goldens/staging-tag-guard | 12 | .golden 12 |
| .ci/rediacc_ci/tests/goldens/standing-orders-brief | 18 | .golden 18 |
| .ci/rediacc_ci/tests/goldens/validate-stage-artifacts | 3 | .golden 3 |
| .ci/rediacc_ci/tests/goldens/verify-ssh | 16 | .golden 16 |
| .ci/rediacc_ci/tests/goldens/version-bump | 28 | .golden 28 |
| .ci/rediacc_ci/tests/goldens/w7p5-go-deps-probe-failure | 6 | .golden 6 |
| .ci/rediacc_ci/tests/goldens/wait-for-vm-ssh | 16 | .golden 16 |
| .ci/rediacc_ci/tests/goldens/write-once-guard | 7 | .golden 7 |
| .ci/rediacc_ci/version | 5 | .py 5 |
| .ci/scripts/build | 11 | .sh 11 |
| .ci/scripts/build/sea-inject | 7 | .mjs 7 |
| .ci/scripts/ci | 15 | .cjs 8, .sh 6, .py 1 |
| .ci/scripts/ci/profiler | 2 | .awk 1, .sh 1 |
| .ci/scripts/deploy | 26 | .sh 26 |
| .ci/scripts/docker | 5 | .py 4, .sh 1 |
| .ci/scripts/docs | 2 | .mjs 2 |
| .ci/scripts/housekeeping | 2 | .py 1, .sh 1 |
| .ci/scripts/infra | 6 | .sh 6 |
| .ci/scripts/lib | 5 | .sh 5 |
| .ci/scripts/pr | 1 | .sh 1 |
| .ci/scripts/private | 6 | .sh 6 |
| .ci/scripts/private/license-mint | 3 | .go 1, .mod 1, .sum 1 |
| .ci/scripts/quality | 155 | .py 148, .sh 4, .json 2, .mjs 1 |
| .ci/scripts/quality/lib | 1 | .py 1 |
| .ci/scripts/release | 15 | .sh 15 |
| .ci/scripts/review | 4 | .sh 4 |
| .ci/scripts/review/prompts | 2 | .md 2 |
| .ci/scripts/security | 2 | .sh 2 |
| .ci/scripts/setup | 2 | .sh 2 |
| .ci/scripts/test | 14 | .sh 13, .ts 1 |
| .ci/scripts/test/fixtures/mutate-check | 2 | .py 1, .sh 1 |
| .ci/scripts/test/gates | 5 | .sh 5 |
| .ci/scripts/test/lib | 3 | .sh 3 |
| .ci/scripts/test/manual | 1 | .sh 1 |
| .ci/scripts/test/proxies | 8 | .sh 8 |
| .ci/scripts/version | 3 | .sh 3 |
| .ci/shadow | 282 | .jsonl 281, .json 1 |
| .ci/tutorials | 21 | .sh 20, .md 1 |
| .ci/tutorials/apps/demo-pgadmin | 2 | (none) 1, .yml 1 |
| .ci/tutorials/apps/heartbeat | 2 | (none) 1, .yaml 1 |
| .ci/tutorials/apps/heartbeat/app | 2 | .json 1, .mjs 1 |
| .ci/tutorials/apps/secrets-demo | 2 | (none) 1, .yml 1 |
| .ci/tutorials/lib | 4 | .sh 4 |

157 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->
## Hook wiring, folded

The per-file detail is the `hook-guards` table above; this is the same wiring folded to one row per event. It moved here from CLAUDE.md in W11 P5b: the detail and the summary belong beside each other, and CLAUDE.md keeps a pointer rather than a second table.

<!-- >>> gen-docs: hook-summary -->

Scans: the `hooks` wiring in .claude/settings.json, folded to one row per event, with the unreached residue.

| Hook event | Matchers | Hook files |
|---|---|---|
| PostCompact | 1 | 1 |
| PostToolUse | 2 | 2 |
| PreCompact | 1 | 1 |
| PreToolUse | 3 | 1 |
| SessionStart | 1 | 1 |
| Stop | 1 | 1 |
| SubagentStop | 1 | 1 |
| TeammateIdle | 1 | 1 |
| (all events) | 11 | 5 |
| (tracked hook files nothing reaches) | - | 11 |

10 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## Entry points

Which implementation serves which `./run.sh` verb. `PORTED_VERBS` is the seam the tooling port moves a verb across, so this table is the port's progress and prose would be stale within a week of the first move.

<!-- >>> gen-docs: bootstrap -->

Scans: `run.sh`, its `PORTED_VERBS` table, the legacy dispatcher and the pins `.ci/bootstrap.sh` installs, folded to one row per entry point.

| Entry point | Serves | Count | Names |
|---|---|---|---|
| `./run.sh` | router arms (bash, in the router itself) | 2 | `provision`, `www` |
| `python3 -m rediacc_ci` | verbs listed in `PORTED_VERBS` | 2 | `dev`, `setup` |
| `.ci/legacy/run-legacy.sh` | every verb the router does not serve itself | 9 | `account`, `clean`, `devbox`, `drill`, `fix`, `quality`, `rotation`, `service`, `worktree` |
| `.ci/bootstrap.sh` | pinned tools, from `.devcontainer/toolchain.env` | 3 | `PYTEST_VERSION=9.1.1`, `PYTEST_XDIST_VERSION=3.8.0`, `UV_VERSION=0.12.10` |

4 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## The CI/CD job graph

Every non-reusable workflow that calls a reusable one, folded to one row per topological stage of its `needs:` graph. This is the chain CLAUDE.md used to draw by hand.

<!-- >>> gen-docs: job-graph -->

Scans: every `.github/workflows/*.yml` that calls a reusable workflow, folded to one row per topological stage of its `needs:` graph.

| Workflow | Stage | Jobs | Calls |
|---|---|---|---|
| `cd-v2.yml` | 0 | `init` | - |
| `cd-v2.yml` | 1 | `publish` | - |
| `cd-v2.yml` | 2 | `deploy-account-edge`, `deploy-marketing-edge` | `cd-deploy-account.yml`, `cd-deploy-worker.yml` |
| `cd-v2.yml` | 3 | `smoke-test` | - |
| `cd-v2.yml` | 4 | `validate-install-published` | `ct-install-methods.yml` |
| `cd-v2.yml` | 5 | `tag-and-release` | - |
| `cd-v2.yml` | 6 | `deploy-account-stable`, `deploy-marketing-stable` | `cd-deploy-account.yml`, `cd-deploy-worker.yml` |
| `ci.yml` | 0 | `initialize` | - |
| `ci.yml` | 1 | `breakpoint-lifecycle`, `build-renet`, `cancel-watchdog`, `check-release-state`, `label-guide`, `quality`, `run-sh-tests` | `ci-build-renet.yml`, `ci-quality.yml` |
| `ci.yml` | 2 | `build-cli`, `build-docker-fast`, `package-tests`, `review-gate` | `ci-build-cli.yml`, `ci-build-docker.yml` |
| `ci.yml` | 3 | `build-docker`, `elite-run-test`, `ops-tests`, `stripe-sandbox`, `tests`, `update-flow-test` | `ci-build-docker.yml`, `ci-ops-test.yml`, `ct-tests.yml`, `ct-update-flow.yml` |
| `ci.yml` | 4 | `stage-artifacts` | `cd-stage.yml` |
| `ci.yml` | 5 | `deploy-preview`, `validate-install`, `validate-promote` | `ct-install-methods.yml` |
| `ci.yml` | 6 | `smoke-test-preview` | - |
| `ci.yml` | 7 | `ci-complete` | - |
| `ci.yml` | 8 | `finalize-release-sentinel` | - |
| `ci.yml` | 9 | `pipeline-sentinel` | - |
| `claude-review.yml` | 0 | `review` | `claude-review-reusable.yml` |
| `promote-stable.yml` | 0 | `promote` | - |
| `promote-stable.yml` | 1 | `deploy-account-stable`, `deploy-marketing-stable` | `cd-deploy-account.yml`, `cd-deploy-worker.yml` |
| `promote-stable.yml` | 2 | `verify-stable` | - |

21 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## Media directories and their R2 prefixes

The union of both sync scripts and `packages/www/.gitignore`. A directory that is gitignored and named by NEITHER script is the row to read: it is in no checkout and in no bucket.

<!-- >>> gen-docs: media -->

Scans: the two R2 sync scripts and `packages/www/.gitignore`, one row per media directory in their union.

| Local path | R2 prefix | Push | Restore | Tracked files |
|---|---|---|---|---|
| `packages/www/public/assets/tutorials/audio/` | `tutorials/audio/` | yes | yes | 0 |
| `packages/www/public/assets/tutorials/video/` | `tutorials/video/` | yes | yes | 0 |
| `packages/www/public/assets/videos/` | `videos/` | yes | yes | 1 |
| `packages/www/public/assets/videos/solutions/` | `videos/solutions/` | via `public/assets/videos/` | via `public/assets/videos/` | 0 |
| `packages/www/public/media/` | (mirrored nowhere) | no | no | 0 |

5 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## The `.json` inventory

Requirement 15 asked for the `.json` files to be "organised", which is unfalsifiable until somebody says what organised means. `docs/ci-overhaul/08-driver-contract.md` supplied a predicate and three counts, and two of the three counts were wrong within a day. The counts below are derived, so they cannot be.

`Discovered by` is the highest-priority non-prose file that WRITES the path down, in a fixed order, not the full reader set: `suppressions` above records why a grep-derived reader column was removed. `(convention)` is the interesting residue and the driver contract's KEEP case -- nothing in the tree names the file, so the only thing that can be finding it is a third-party tool's
own convention.

<!-- >>> gen-docs: json-inventory -->
<!-- Prose is excluded from the namer corpus, and so are the three data homes themselves: a -->
<!-- plan that mentions biome.json cannot open it, and .ci/config/bws-unrequested.json naming -->
<!-- regions.json is a policy list voting on its neighbour rather than a thing that reads it. -->
<!-- scripts/ci-runner/gates.lock.json is excluded BY NAME: it is generated, so "repoint it -->
<!-- there" is advice the next `gen:gates-lock` undoes. Globs and template literals count as -->
<!-- names, or all seven nis2 manifests read as (convention) when a template literal builds -->
<!-- them -- a false (convention) is the reading that says "nothing will break if you move it". -->

Scans: every tracked `.json`/`.jsonc` file in the four homes the driver contract names (the repository root, `.ci/config`, `scripts/data`, `.ci/policy`), against the non-prose files that write its path down, globs and template literals included.

| File | Home | Discovered by | Configurable path? |
|---|---|---|---|
| `.syncpackrc-reasons.json` | root | code: `.ci/scripts/ci/scope-map.cjs` | no -- hardcoded in `.ci/scripts/ci/scope-map.cjs` |
| `.syncpackrc.json` | root | wiring: `package.json` | yes -- repoint in `package.json` |
| `biome.json` | root | code: `.ci/rediacc_ci/tests/gates/test_gate_tree_shape.py` | no -- hardcoded in `.ci/rediacc_ci/tests/gates/test_gate_tree_shape.py` |
| `css-custom-data.json` | root | wiring: `.vscode/settings.json` | yes -- repoint in `.vscode/settings.json` |
| `knip.jsonc` | root | code: `.ci/rediacc_ci/tests/gates/test_gate_knip_blockers.py` | no -- hardcoded in `.ci/rediacc_ci/tests/gates/test_gate_knip_blockers.py` |
| `package-lock.json` | root | wiring: `.github/actions/setup-workspace/action.yml` | yes -- repoint in `.github/actions/setup-workspace/action.yml` |
| `package.json` | root | wiring: `.github/workflows/ci-quality.yml` | yes -- repoint in `.github/workflows/ci-quality.yml` |
| `regions.json` | root | wiring: `.github/workflows/cd-deploy-account.yml` | yes -- repoint in `.github/workflows/cd-deploy-account.yml` |
| `tsconfig.json` | root | wiring: `.github/workflows/ci.yml` | yes -- repoint in `.github/workflows/ci.yml` |
| `.ci/config/actions-allowlist.json` | .ci/config | code: `.ci/scripts/quality/check_actions_allowlist.py` | no -- hardcoded in `.ci/scripts/quality/check_actions_allowlist.py` |
| `.ci/config/actions-vars.json` | .ci/config | code: `.ci/rediacc_ci/quality/actions_vars.py` | no -- hardcoded in `.ci/rediacc_ci/quality/actions_vars.py` |
| `.ci/config/agent-session-archival.json` | .ci/config | code: `.ci/rediacc_ci/quality/agent_session_archival.py` | no -- hardcoded in `.ci/rediacc_ci/quality/agent_session_archival.py` |
| `.ci/config/bulk-transform-proof-baseline.json` | .ci/config | code: `.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py` | no -- hardcoded in `.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py` |
| `.ci/config/bws-secret-map.json` | .ci/config | wiring: `.github/actions/bws-secrets/action.yml` | yes -- repoint in `.github/actions/bws-secrets/action.yml` |
| `.ci/config/bws-unrequested.json` | .ci/config | code: `.ci/rediacc_ci/tests/gates/test_gate_bws_map.py` | no -- hardcoded in `.ci/rediacc_ci/tests/gates/test_gate_bws_map.py` |
| `.ci/config/carried-reds.json` | .ci/config | code: `.claude/oracles/pre-bash/block-unverified-push.sh` | no -- hardcoded in `.claude/oracles/pre-bash/block-unverified-push.sh` |
| `.ci/config/commit-identity.json` | .ci/config | code: `.ci/rediacc_ci/quality/commit_identity.py` | no -- hardcoded in `.ci/rediacc_ci/quality/commit_identity.py` |
| `.ci/config/docker-npm-pin-exclusions.json` | .ci/config | code: `.ci/scripts/quality/check_allowlist_key_matching.py` | no -- hardcoded in `.ci/scripts/quality/check_allowlist_key_matching.py` |
| `.ci/config/env-local-allowlist.json` | .ci/config | code: `.ci/scripts/quality/check_bws_map.py` | no -- hardcoded in `.ci/scripts/quality/check_bws_map.py` |
| `.ci/config/env-manifest.json` | .ci/config | code: `.ci/rediacc_ci/quality/actions_vars.py` | no -- hardcoded in `.ci/rediacc_ci/quality/actions_vars.py` |
| `.ci/config/language-policy-baseline.json` | .ci/config | code: `.ci/rediacc_ci/quality/python_env_registry.py` | no -- hardcoded in `.ci/rediacc_ci/quality/python_env_registry.py` |
| `.ci/config/plan-boxes.json` | .ci/config | code: `.ci/rediacc_ci/quality/plan_lifecycle.py` | no -- hardcoded in `.ci/rediacc_ci/quality/plan_lifecycle.py` |
| `.ci/config/plan-implementation.json` | .ci/config | code: `.ci/scripts/quality/check_plan_implementation.py` | no -- hardcoded in `.ci/scripts/quality/check_plan_implementation.py` |
| `.ci/config/plan-lifecycle.json` | .ci/config | code: `.ci/rediacc_ci/quality/plan_housekeeping.py` | no -- hardcoded in `.ci/rediacc_ci/quality/plan_housekeeping.py` |
| `.ci/config/plant-proof-baseline.json` | .ci/config | code: `.ci/rediacc_ci/quality/plant_proofs.py` | no -- hardcoded in `.ci/rediacc_ci/quality/plant_proofs.py` |
| `.ci/config/prose-style-baseline.json` | .ci/config | code: `.ci/rediacc_ci/quality/prose_style.py` | no -- hardcoded in `.ci/rediacc_ci/quality/prose_style.py` |
| `.ci/config/prose-style-rules.json` | .ci/config | code: `.ci/rediacc_ci/quality/prose_style.py` | no -- hardcoded in `.ci/rediacc_ci/quality/prose_style.py` |
| `.ci/config/python-env-registry.json` | .ci/config | code: `.ci/rediacc_ci/deploy/set_account_worker_secrets.py` | no -- hardcoded in `.ci/rediacc_ci/deploy/set_account_worker_secrets.py` |
| `.ci/config/python-types-baseline.json` | .ci/config | code: `.ci/rediacc_ci/quality/python_types.py` | no -- hardcoded in `.ci/rediacc_ci/quality/python_types.py` |
| `.ci/config/release-age.json` | .ci/config | code: `.ci/rediacc_ci/core/release_age.py` | no -- hardcoded in `.ci/rediacc_ci/core/release_age.py` |
| `.ci/config/rubric-calibration.json` | .ci/config | code: `.ci/rediacc_ci/quality/rubric_calibration.py` | no -- hardcoded in `.ci/rediacc_ci/quality/rubric_calibration.py` |
| `.ci/config/secret-reachability.json` | .ci/config | code: `.ci/rediacc_ci/tests/gates/test_gate_bws_map.py` | no -- hardcoded in `.ci/rediacc_ci/tests/gates/test_gate_bws_map.py` |
| `.ci/config/secret-scope-baseline.json` | .ci/config | code: `.ci/rediacc_ci/quality/python_env_registry.py` | no -- hardcoded in `.ci/rediacc_ci/quality/python_env_registry.py` |
| `.ci/config/secret-supply.json` | .ci/config | code: `.ci/rediacc_ci/quality/actions_vars.py` | no -- hardcoded in `.ci/rediacc_ci/quality/actions_vars.py` |
| `.ci/config/syncpack-source-exclusions.json` | .ci/config | code: `.ci/scripts/quality/check_language_policy.py` | no -- hardcoded in `.ci/scripts/quality/check_language_policy.py` |
| `.ci/config/tracked-credentials-baseline.json` | .ci/config | code: `.ci/rediacc_ci/quality/python_env_registry.py` | no -- hardcoded in `.ci/rediacc_ci/quality/python_env_registry.py` |
| `scripts/data/css-dom-refs-baseline.json` | scripts/data | code: `scripts/ci-runner/manifest.ts` | no -- hardcoded in `scripts/ci-runner/manifest.ts` |
| `scripts/data/dead-css-baseline.json` | scripts/data | code: `scripts/ci-runner/manifest.ts` | no -- hardcoded in `scripts/ci-runner/manifest.ts` |
| `scripts/data/dead-translation-keys-baseline.json` | scripts/data | code: `scripts/ci-runner/manifest.ts` | no -- hardcoded in `scripts/ci-runner/manifest.ts` |
| `scripts/data/doc-registry-preport.json` | scripts/data | code: `.ci/rediacc_ci/tests/gates/test_gate_docs_gen.py` | no -- hardcoded in `.ci/rediacc_ci/tests/gates/test_gate_docs_gen.py` |
| `scripts/data/docker-image-freshness-baseline.json` | scripts/data | code: `scripts/ci-runner/manifest.ts` | no -- hardcoded in `scripts/ci-runner/manifest.ts` |
| `scripts/data/domain-layout-baseline.json` | scripts/data | code: `scripts/gates/check-baseline-key-semantics.ts` | no -- hardcoded in `scripts/gates/check-baseline-key-semantics.ts` |
| `scripts/data/domains.json` | scripts/data | code: `.ci/rediacc_ci/ops/__init__.py` | no -- hardcoded in `.ci/rediacc_ci/ops/__init__.py` |
| `scripts/data/em-dash-surfaces-baseline.json` | scripts/data | code: `.ci/rediacc_ci/tests/gates/test_gate_shrink_only_composition.py` | no -- hardcoded in `.ci/rediacc_ci/tests/gates/test_gate_shrink_only_composition.py` |
| `scripts/data/enumeration-vacuity-baseline.json` | scripts/data | code: `scripts/gates/check-baseline-key-semantics.ts` | no -- hardcoded in `scripts/gates/check-baseline-key-semantics.ts` |
| `scripts/data/hook-audit-scope.json` | scripts/data | code: `.ci/rediacc_ci/quality/hook_integrity.py` | no -- hardcoded in `.ci/rediacc_ci/quality/hook_integrity.py` |
| `scripts/data/hook-coverage-baseline.json` | scripts/data | code: `.ci/rediacc_ci/quality/hook_integrity.py` | no -- hardcoded in `.ci/rediacc_ci/quality/hook_integrity.py` |
| `scripts/data/hook-inventory-baseline.json` | scripts/data | code: `.ci/rediacc_ci/quality/dead_python.py` | no -- hardcoded in `.ci/rediacc_ci/quality/dead_python.py` |
| `scripts/data/locale-de-contamination-baseline.json` | scripts/data | code: `scripts/ci-runner/manifest.ts` | no -- hardcoded in `scripts/ci-runner/manifest.ts` |
| `scripts/data/nis2-directive-2022-2555-de.manifest.json` | scripts/data | code: `scripts/gates/check-directive-quotes.ts` | no -- hardcoded in `scripts/gates/check-directive-quotes.ts` |
| `scripts/data/nis2-directive-2022-2555-en.manifest.json` | scripts/data | code: `scripts/gates/check-directive-quotes.ts` | no -- hardcoded in `scripts/gates/check-directive-quotes.ts` |
| `scripts/data/nis2-directive-2022-2555-es.manifest.json` | scripts/data | code: `scripts/gates/check-directive-quotes.ts` | no -- hardcoded in `scripts/gates/check-directive-quotes.ts` |
| `scripts/data/nis2-directive-2022-2555-et.manifest.json` | scripts/data | code: `scripts/gates/check-directive-quotes.ts` | no -- hardcoded in `scripts/gates/check-directive-quotes.ts` |
| `scripts/data/nis2-directive-2022-2555-fr.manifest.json` | scripts/data | code: `scripts/gates/check-directive-quotes.ts` | no -- hardcoded in `scripts/gates/check-directive-quotes.ts` |
| `scripts/data/nis2-directive-2022-2555-it.manifest.json` | scripts/data | code: `scripts/gates/check-directive-quotes.ts` | no -- hardcoded in `scripts/gates/check-directive-quotes.ts` |
| `scripts/data/nis2-directive-2022-2555-pt.manifest.json` | scripts/data | code: `scripts/gates/check-directive-quotes.ts` | no -- hardcoded in `scripts/gates/check-directive-quotes.ts` |
| `scripts/data/package-key-budget-baseline.json` | scripts/data | code: `.ci/scripts/quality/check_docker_npm_pins.py` | no -- hardcoded in `.ci/scripts/quality/check_docker_npm_pins.py` |
| `scripts/data/sentence-wrapping-baseline.json` | scripts/data | code: `scripts/ci-runner/manifest.ts` | no -- hardcoded in `scripts/ci-runner/manifest.ts` |
| `scripts/data/shape-duplication-seed-advisory.json` | scripts/data | code: `.claude/hooks/stop/test-judge-schema.py` | no -- hardcoded in `.claude/hooks/stop/test-judge-schema.py` |
| `scripts/data/shape-duplication-seed.json` | scripts/data | code: `.ci/scripts/ci/scope-map.cjs` | no -- hardcoded in `.ci/scripts/ci/scope-map.cjs` |
| `scripts/data/shell-declared-commands-baseline.json` | scripts/data | code: `scripts/ci-runner/manifest.ts` | no -- hardcoded in `scripts/ci-runner/manifest.ts` |
| `scripts/data/static-nowrap-baseline.json` | scripts/data | code: `scripts/ci-runner/manifest.ts` | no -- hardcoded in `scripts/ci-runner/manifest.ts` |
| `.ci/policy/hook-exec-baseline.json` | .ci/policy | code: `.ci/rediacc_ci/policy_paths.py` | no -- hardcoded in `.ci/rediacc_ci/policy_paths.py` |
| `.ci/policy/tree-shape.json` | .ci/policy | code: `.ci/rediacc_ci/policy_paths.py` | no -- hardcoded in `.ci/rediacc_ci/policy_paths.py` |
| `.ci/policy/worklist-env-registry.json` | .ci/policy | code: `.ci/rediacc_ci/policy_paths.py` | no -- hardcoded in `.ci/rediacc_ci/policy_paths.py` |

65 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## Environment variables

Every environment variable this repository reads or supplies, and which shard it belongs to. The shards are keyed on WHO SUPPLIES THE VALUE and WHO MAY READ IT. Their definitions run to a paragraph apiece and stay in `.ci/config/env-manifest.json` rather than being copied into a column that would repeat one of them on every row.

The manifest is not typed by hand either: `check:ci-env-manifest` re-derives the union from five sources (tracked env files, workflow and action `KEY:` maps, `process.env`, `os.environ` by AST rather than by regex, and the Bitwarden secret map) and reds when the file and the tree disagree in either direction. So this table is a projection of a projection, and neither hop has a
hand-kept list in it.

One row per NAME, never a value. A row per shard carrying that shard's count would be smaller and would go blind to exactly the change worth catching: one variable leaving as another arrives keeps every count identical.

`Also recorded` is the manifest's residue, hung off the variable it is about: a collision (two variables that share one spelling), a note recording a contradiction the gate cannot resolve, and the test files that hold a tombstone down. A `-` means the manifest says nothing further.

<!-- >>> gen-docs: env-manifest -->
<!-- Names, shards and residue only. Not one value is read or printed: the secret shard is -->
<!-- names supplied by a vault, and a table of names is a map of the seams while a table of -->
<!-- values would be the leak. -->

Scans: the shard classification in `.ci/config/env-manifest.json`, the committed projection `check:ci-env-manifest` re-derives from five sources and holds faithful in both directions, one row per variable NAME and never a value.

| Variable | Shard | Also recorded |
|---|---|---|
| `ACCOUNT_BACKUP_S3_ACCESS_KEY_ID` | secret | - |
| `ACCOUNT_BACKUP_S3_ENDPOINT` | secret | - |
| `ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY` | secret | - |
| `ACCOUNT_ED25519_PRIVATE_KEY` | secret | - |
| `ACCOUNT_ED25519_PUBLIC_KEY` | secret | - |
| `ACCOUNT_ENTRY` | ci-runner | - |
| `ACCOUNT_JWT_SECRET` | secret | - |
| `ACCOUNT_SERVER_API_KEY` | secret | - |
| `ACCOUNT_X25519_PRIVATE_KEY` | secret | - |
| `ACCOUNT_X25519_PUBLIC_KEY` | secret | - |
| `ACTIONLINT_VERSION` | toolchain | - |
| `ACTIONS_ALLOWLIST_MIN` | gate-seam | - |
| `ACTIONS_ALLOWLIST_ROOT` | gate-seam | - |
| `ACTION_REFS_MIN_FILES` | gate-seam | - |
| `AGENT_BROWSER_VERSION` | toolchain | - |
| `AGENT_SESSION_ARCHIVAL_ROOT` | gate-seam | - |
| `AGE_FAIL_DAYS` | gate-seam | - |
| `AGE_WARN_DAYS` | gate-seam | - |
| `AGG_BIN` | toolchain | - |
| `ALLOW_STALE` | ci-runner | - |
| `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` | secret | - |
| `APK_RSA_PRIVATE_KEY` | secret | - |
| `APPDATA` | machine-local | - |
| `APP_TOKEN` | tombstone | - |
| `APP_VERSION` | ci-runner | - |
| `ARG_BUNDLE` | ci-runner | - |
| `ARG_CONNECT_TIMEOUT` | ci-runner | - |
| `ARG_VERIFY` | ci-runner | - |
| `ATTEMPTS` | ci-runner | - |
| `AUTOPILOT_ALLOW_PUSH` | tombstone | - |
| `AUTOPILOT_ALLOW_STATE` | tombstone | - |
| `AUTOPILOT_ALLOW_SUBMODULES` | tombstone | - |
| `AUTOPILOT_APPLIER_ALLOWLIST` | tombstone | - |
| `AUTOPILOT_AUTHOR_ALLOWLIST` | tombstone | - |
| `AUTOPILOT_BP_ALIGN_AUTOPILOT_FILE` | tombstone | - |
| `AUTOPILOT_BP_ALIGN_BREAKPOINT_FILE` | tombstone | - |
| `AUTOPILOT_EFFORT` | tombstone | - |
| `AUTOPILOT_ENABLED` | tombstone | - |
| `AUTOPILOT_GIT_EMAIL` | tombstone | - |
| `AUTOPILOT_GIT_NAME` | tombstone | - |
| `AUTOPILOT_LABEL` | tombstone | - |
| `AUTOPILOT_MAX_ROUNDS` | tombstone | - |
| `AWS_ACCESS_KEY_ID` | secret | - |
| `AWS_DEFAULT_REGION` | ci-runner | - |
| `AWS_IAM_ADMIN_ACCESS_KEY_ID` | secret | - |
| `AWS_IAM_ADMIN_SECRET_ACCESS_KEY` | secret | - |
| `AWS_MAX_ATTEMPTS` | ci-runner | - |
| `AWS_RETRY_MODE` | ci-runner | - |
| `AWS_SECRET_ACCESS_KEY` | secret | - |
| `AWS_SES_ACCESS_KEY_ID` | secret | - |
| `AWS_SES_ACCESS_KEY_ID_ASIA` | secret | - |
| `AWS_SES_ACCESS_KEY_ID_EU` | secret | - |
| `AWS_SES_ACCESS_KEY_ID_US` | secret | - |
| `AWS_SES_CONFIGURATION_SET` | secret | - |
| `AWS_SES_FROM` | secret | - |
| `AWS_SES_HOST` | secret | - |
| `AWS_SES_REGION` | secret | - |
| `AWS_SES_REGION_EU` | secret | - |
| `AWS_SES_SECRET_ACCESS_KEY` | secret | - |
| `AWS_SES_SECRET_ACCESS_KEY_ASIA` | secret | - |
| `AWS_SES_SECRET_ACCESS_KEY_EU` | secret | - |
| `AWS_SES_SECRET_ACCESS_KEY_US` | secret | - |
| `BACKUP_BUCKET_EDGE` | ci-runner | - |
| `BACKUP_BUCKET_STABLE` | ci-runner | - |
| `BACKUP_STORAGE_SUITE` | harness | - |
| `BATTERY_CLEAN_TREE_ROOT` | gate-seam | - |
| `BINARY_PATH` | ci-runner | - |
| `BOT` | tombstone | - |
| `BP_ACCESS_EMAILS` | harness | - |
| `BP_ACTOR` | harness | - |
| `BP_DESKTOP` | harness | - |
| `BP_DURATION` | harness | - |
| `BP_LABEL` | harness | - |
| `BP_MODE` | harness | - |
| `BP_ORIGIN` | harness | - |
| `BP_RUNNER` | harness | - |
| `BP_SEND_EMAIL` | harness | - |
| `BP_SERVICES` | harness | - |
| `BP_TUNNEL_MODE` | harness | - |
| `BRANCH` | gate-seam | - |
| `BRANCH_MAX_AGE_DAYS` | ci-runner | - |
| `BREAKPOINT_DEBUG_SHELL` | harness | - |
| `BREAKPOINT_DESKTOP` | harness | - |
| `BRIDGE_TEST_SKIP_RESET` | harness | - |
| `BRIDGE_TIMEOUT` | harness | - |
| `BUCKET` | ci-runner | - |
| `BWS_ACCESS_TOKEN` | secret | - |
| `BWS_BIN` | toolchain | - |
| `BWS_ENV_ROOT` | gate-seam | - |
| `BWS_MAP_ROOT` | gate-seam | - |
| `BWS_MIN_CALLERS` | gate-seam | - |
| `BWS_MIN_MAP_ENTRIES` | gate-seam | - |
| `BWS_ROTATE_ENV_FILE` | harness | - |
| `BWS_ROTATE_GITMODULES` | harness | - |
| `BWS_ROTATE_MIN_SECRETS` | harness | - |
| `BWS_ROTATE_SECRET_MAP` | harness | - |
| `CAMPAIGN` | tombstone | - |
| `CC_MUTABLE` | harness | - |
| `CEPH_MODE` | harness | - |
| `CEPH_OSD_MEMORY_TARGET` | harness | - |
| `CEPH_POOL_PG_NUM` | harness | - |
| `CF_EMAIL` | secret | - |
| `CF_GLOBAL_API_KEY` | secret | - |
| `CHANNEL` | ci-runner | - |
| `CHECKS_TOKEN` | secret | - |
| `CHECK_DEPS_FORCE_PROBE_FAILURE` | gate-seam | - |
| `CHECK_NAME` | gate-seam | - |
| `CHOWN_PATH` | ci-runner | - |
| `CI` | ci-runner | - |
| `CI_ARCH` | ci-runner | - |
| `CI_DOCKER_DIR` | ci-runner | - |
| `CI_JOBS` | ci-runner | - |
| `CI_JOB_AGGREGATION_ASSERT` | gate-seam | - |
| `CI_JOB_AGGREGATION_WORKFLOW` | gate-seam | - |
| `CI_MODE` | ci-runner | - |
| `CI_OS` | ci-runner | - |
| `CI_PARITY_MANIFEST` | gate-seam | - |
| `CI_PARITY_ROOT` | gate-seam | - |
| `CI_PROFILE` | ci-runner | - |
| `CI_PROFILE_DIR` | ci-runner | - |
| `CI_PROFILE_RUN` | ci-runner | - |
| `CI_RUNNER_BASE` | ci-runner | - |
| `CI_RUNNER_CACHE` | ci-runner | - |
| `CI_RUNNER_MANIFEST` | ci-runner | - |
| `CI_RUN_ID` | ci-runner | - |
| `CI_SHA` | ci-runner | - |
| `CI_TEMP` | ci-runner | - |
| `CI_TRACE_MAX_READ_FAILURES` | ci-runner | - |
| `CI_TRACE_POLL_S` | ci-runner | - |
| `CI_TRACE_TIMEOUT_S` | ci-runner | - |
| `CLAUDECODE` | product-runtime | - |
| `CLAUDE_AGENT_TYPE` | harness | - |
| `CLAUDE_ARGS_SENT` | ci-runner | - |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | harness | - |
| `CLAUDE_CODE_SESSION_ID` | harness | - |
| `CLAUDE_CONFIG_DIR` | harness | - |
| `CLAUDE_PID` | harness | - |
| `CLAUDE_PROJECT_DIR` | harness | - |
| `CLAUDE_REVIEW_GATE_SCRIPT_DIR` | gate-seam | - |
| `CLAUDE_TRANSCRIPT_PATH` | harness | - |
| `CLI_SUITE` | harness | - |
| `CLI_VERSION` | ci-runner | - |
| `CLOUDFLARE_ACCOUNT_ID` | secret | - |
| `CLOUDFLARE_API_TOKEN` | secret | - |
| `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN` | secret | - |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | secret | - |
| `CLOUDFLARE_R2_ENDPOINT` | secret | - |
| `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID` | secret | - |
| `CLOUDFLARE_R2_MEDIA_ENDPOINT` | secret | - |
| `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY` | secret | - |
| `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | secret | - |
| `CLOUDFLARE_TURNSTILE_SECRET_KEY` | secret | - |
| `CLOUDFLARE_ZONE_ID` | secret | - |
| `CLUSTER_LICENSING_SUITE` | harness | - |
| `COLUMNS` | machine-local | - |
| `COMMENT_ID` | tombstone | - |
| `COMMIT_AUTHOR` | ci-runner | - |
| `COMMIT_IDENTITY_FILE` | gate-seam | - |
| `COMMIT_SHA` | ci-runner | - |
| `CONFIRMATION` | ci-runner | - |
| `CONSOLE_ROOT_DIR` | gate-seam | - |
| `COPILOT_CLI` | product-runtime | - |
| `CRIU_EXPECTED` | harness | - |
| `CSI_SANITY_BASE` | harness | - |
| `CSI_SANITY_IMG` | harness | - |
| `CTX_BAND_DUMP` | harness | - |
| `CTX_BAND_STATE_DIR` | harness | - |
| `CURSOR_TRACE_ID` | product-runtime | - |
| `DATABASE_PATH` | harness | - |
| `DB_HOST` | product-runtime | - |
| `DB_PORT` | product-runtime | - |
| `DEAD_BASH_ROOT` | gate-seam | - |
| `DEAD_CASE_CODE_DIRS` | gate-seam | - |
| `DEAD_CASE_MEDIA_DIRS` | gate-seam | - |
| `DEAD_CASE_TEST_DIRS` | gate-seam | - |
| `DEBUG` | harness | collision: dead in the rdc CLI, live in packages/e2e-tests/.env.example |
| `DECISION_IDS_BASE` | gate-seam | - |
| `DECISION_IDS_REGISTER` | gate-seam | - |
| `DECISION_IDS_ROOT` | gate-seam | - |
| `DEPLOY_WORKERS_ONLY` | ci-runner | - |
| `DESKTOP_RESOLUTION` | harness | - |
| `DETECT_BUMP_MAX_COMMITS` | ci-runner | - |
| `DEVBOX_OFFSET_STUDIO` | harness | - |
| `DEVCONTAINER_BLOCKLIST_FILE` | gate-seam | - |
| `DEVCONTAINER_DOCKERFILE` | gate-seam | - |
| `DEVCONTAINER_FRESHNESS_FIXTURE` | gate-seam | - |
| `DISKS_PATH` | harness | - |
| `DISPATCH_ACTOR` | tombstone | - |
| `DISPATCH_MAX_ROUNDS` | tombstone | - |
| `DISPATCH_MODEL` | tombstone | - |
| `DISPATCH_PR` | tombstone | - |
| `DISPATCH_REF` | ci-runner | - |
| `DISPATCH_RELEASE_DRY_RUN` | ci-runner | - |
| `DOCKERHUB_PASSWORD` | secret | - |
| `DOCKERHUB_TOKEN` | secret | - |
| `DOCKERHUB_USERNAME` | secret | - |
| `DOCKER_HOST` | machine-local | - |
| `DOCKER_NPM_PINS_MIN` | gate-seam | - |
| `DOCKER_NPM_PINS_MIN_WORKFLOWS` | gate-seam | - |
| `DOCKER_NPM_PINS_ROOT` | gate-seam | - |
| `DOCKER_REGISTRY` | product-runtime | - |
| `DOCKER_TAG` | ci-runner | - |
| `DOCS_RENDER_PARITY_ROOT` | gate-seam | - |
| `DRILL_EXPECT_NO_KEYRING` | harness | - |
| `DRY_RUN` | ci-runner | - |
| `DST_PREFIX` | ci-runner | - |
| `DUAL_GROUP` | harness | - |
| `E2E_ACCOUNT_API_TOKEN` | secret | - |
| `E2E_CLI_BIN` | harness | - |
| `E2E_CLUSTER_NAME` | harness | - |
| `E2E_CLUSTER_REPO` | harness | - |
| `E2E_COV_ALLOWLIST` | gate-seam | - |
| `E2E_COV_E2E_DIR` | gate-seam | - |
| `E2E_COV_FUNCTIONS_FILE` | gate-seam | - |
| `E2E_COV_REGISTRY` | gate-seam | - |
| `E2E_COV_WORKFLOWS_DIR` | gate-seam | - |
| `E2E_EXPECT_NO_CLUSTER_VMS` | harness | - |
| `E2E_HYGIENE_ROOT` | gate-seam | - |
| `E2E_SSH_KEY` | secret | - |
| `E2E_SSH_USER` | harness | - |
| `EDGE_DATE` | ci-runner | - |
| `EDGE_RETRIES` | ci-runner | - |
| `EDGE_RETRY_SLEEP` | ci-runner | - |
| `EDGE_VERSION` | ci-runner | - |
| `EDITOR` | machine-local | - |
| `EFFORT` | tombstone | - |
| `EMBED_BLOCKLIST_FILE` | gate-seam | - |
| `EMBED_CREDITS_DOCKERFILE` | gate-seam | - |
| `EMBED_CREDITS_GO_FILE` | gate-seam | - |
| `EMBED_CREDITS_JSON_FILE` | gate-seam | - |
| `EMBED_FRESHNESS_FIXTURE` | gate-seam | - |
| `EMBED_PARITY_LOCKFILE` | gate-seam | - |
| `ENABLE_HTTPS` | harness | - |
| `ENUM_VACUITY_MIN` | gate-seam | - |
| `ENV_MANIFEST_OVERRIDE_FILE` | gate-seam | - |
| `ENV_NAMES_MIN` | gate-seam | - |
| `ENV_NAMES_ROOT` | gate-seam | - |
| `EVENT_NAME` | ci-runner | - |
| `EXECUTION_FILE` | ci-runner | - |
| `EXTERNAL_CALLERS_FILE` | gate-seam | - |
| `EXTERNAL_QUALITY_MODE` | ci-runner | - |
| `FAKE_BIN_DIR` | gate-seam | - |
| `FAKE_BIN_RECORDS` | gate-seam | - |
| `FFMPEG_BIN` | toolchain | - |
| `FFPROBE_BIN` | toolchain | - |
| `FLASK_DEBUG` | product-runtime | - |
| `FORCE` | ci-runner | - |
| `FORCE_FULL_CI` | ci-runner | - |
| `FORMAT_SCOPE_ROOT` | gate-seam | - |
| `FULL_CI` | secret | - |
| `FULL_CI_LABEL` | ci-runner | - |
| `FULL_INTEGRATION` | harness | - |
| `FULL_SUITE` | ci-runner | - |
| `GATEWAY_PORT` | harness | - |
| `GATE_HARNESS_PROBE` | gate-seam | - |
| `GATE_PATHS_SCAN_FLOOR` | gate-seam | - |
| `GATE_SKIP_MODE` | ci-runner | - |
| `GATE_SKIP_WORKFLOW` | gate-seam | - |
| `GATE_STEP_LOCK_MAP` | ci-runner | - |
| `GEMINI_CLI` | product-runtime | - |
| `GENERATION` | ci-runner | - |
| `GEN_MANIFEST_DEBUG` | ci-runner | - |
| `GH_APP_TOKEN` | secret | - |
| `GH_BIN` | toolchain | - |
| `GH_REPO` | ci-runner | - |
| `GH_TOKEN` | secret | - |
| `GITHUB_ACTIONS` | ci-runner | - |
| `GITHUB_ACTOR` | ci-runner | - |
| `GITHUB_APP_CLIENT_SECRET` | secret | - |
| `GITHUB_APP_ID` | secret | - |
| `GITHUB_APP_PRIVATE_KEY` | secret | - |
| `GITHUB_BASE_REF` | ci-runner | - |
| `GITHUB_ENV` | ci-runner | - |
| `GITHUB_EVENT_NAME` | ci-runner | - |
| `GITHUB_EVENT_PATH` | ci-runner | - |
| `GITHUB_HEAD_REF` | ci-runner | - |
| `GITHUB_JOB` | ci-runner | - |
| `GITHUB_OUTPUT` | ci-runner | - |
| `GITHUB_PAT` | secret | - |
| `GITHUB_REF` | ci-runner | - |
| `GITHUB_REF_NAME` | ci-runner | - |
| `GITHUB_REF_TYPE` | ci-runner | - |
| `GITHUB_REPOSITORY` | ci-runner | - |
| `GITHUB_RUN_ATTEMPT` | ci-runner | - |
| `GITHUB_RUN_ID` | ci-runner | - |
| `GITHUB_SHA` | ci-runner | - |
| `GITHUB_STATE` | ci-runner | - |
| `GITHUB_STEP_SUMMARY` | ci-runner | - |
| `GITHUB_TOKEN` | secret | - |
| `GITHUB_WORKSPACE` | ci-runner | - |
| `GIT_BOT_EMAIL` | secret | - |
| `GIT_BOT_NAME` | secret | - |
| `GIT_EDITOR` | machine-local | - |
| `GL_CLOSURE_PATHS` | gate-seam | - |
| `GL_ROOT` | gate-seam | - |
| `GNUPGHOME` | machine-local | - |
| `GOTOOLCHAIN` | toolchain | - |
| `GO_VERSION` | toolchain | - |
| `GROUP_B_BRIDGE` | harness | - |
| `GROUP_B_NET` | harness | - |
| `GROUP_B_NET_BASE` | harness | - |
| `GROUP_B_WORKER` | harness | - |
| `HEAD_BRANCH` | tombstone | - |
| `HEAD_REF` | ci-runner | - |
| `HEAD_SHA` | ci-runner | - |
| `HEARTBEAT_INTERVAL_MS` | product-runtime | - |
| `HOME` | machine-local | - |
| `HOOK_EXEC_COUNTER_DIR` | gate-seam | - |
| `HOOK_LABEL_DIR` | harness | - |
| `HTTPS_PORT` | harness | - |
| `HTTP_PORT` | harness | - |
| `IMAGE_PATH` | ci-runner | - |
| `IMAGE_TAG` | ci-runner | - |
| `INLINE_MAX_LOGIC` | gate-seam | - |
| `INPUT_CI_RUN_ID` | ci-runner | - |
| `INPUT_SHA` | ci-runner | - |
| `IN_FLIGHT_VERSION` | ci-runner | - |
| `IS_BOT` | ci-runner | - |
| `JOB_STATUS` | ci-runner | - |
| `K8S_MODE` | harness | - |
| `KEEP_CLUSTER` | harness | - |
| `KEEP_GROUPS` | harness | - |
| `LABEL` | tombstone | - |
| `LABEL_GUIDE_LABELS_FILE` | gate-seam | - |
| `LABEL_INVENTORY_LABELS_FILE` | gate-seam | - |
| `LABEL_INVENTORY_LIVE_FILE` | gate-seam | - |
| `LABEL_INVENTORY_LIVE_JSON_FILE` | gate-seam | - |
| `LABEL_INVENTORY_MIN_DECLARED` | gate-seam | - |
| `LABEL_INVENTORY_PROBE_FILE` | gate-seam | - |
| `LABEL_INVENTORY_VERIFY_ALLOWLIST` | gate-seam | - |
| `LABEL_REFS_LABELS_FILE` | gate-seam | - |
| `LABEL_REFS_MIN_DISTINCT` | gate-seam | - |
| `LABEL_REFS_SCAN_DIRS` | gate-seam | - |
| `LANG` | machine-local | - |
| `LANGUAGE_POLICY_ALLOWLIST` | gate-seam | - |
| `LANGUAGE_POLICY_BASELINE` | gate-seam | - |
| `LANGUAGE_POLICY_ROOT` | gate-seam | - |
| `LANGUAGE_POLICY_VALIDATOR` | gate-seam | - |
| `LC_ALL` | machine-local | - |
| `LOCALAPPDATA` | machine-local | - |
| `LOCAL_CI_DIR` | harness | - |
| `LOCAL_LIB_DIR` | harness | - |
| `LOCAL_ROOT_DIR` | harness | - |
| `MACHINE_NAME` | harness | - |
| `MAP` | ci-runner | - |
| `MATRIX_DOMAIN` | ci-runner | - |
| `MATRIX_EDGE_DOMAIN` | ci-runner | - |
| `MATRIX_EDGE_WORKER_NAME` | ci-runner | - |
| `MATRIX_ID` | ci-runner | - |
| `MATRIX_SECRET_SUFFIX` | secret | - |
| `MATRIX_WORKER_NAME` | ci-runner | - |
| `MAX_ATTEMPTS` | ci-runner | - |
| `MAX_DELETES_PER_RUN` | ci-runner | - |
| `MAX_ROUNDS` | tombstone | - |
| `MEDIA_COVERAGE_FILE` | gate-seam | - |
| `MERGE_SHA` | ci-runner | - |
| `MIN_TURNS_PER_KLOC` | gate-seam | - |
| `MODE` | ci-runner | - |
| `MODEL` | tombstone | - |
| `MSYS2_ROOT` | machine-local | - |
| `MSYSTEM` | machine-local | - |
| `MYPY_BIN` | toolchain | - |
| `MYPY_VERSION` | toolchain | - |
| `NEXT_VERSION` | ci-runner | - |
| `NFPM_APK_KEY_FILE` | secret | - |
| `NFPM_ARCH` | ci-runner | - |
| `NFPM_DEB_KEY_FILE` | secret | - |
| `NFPM_DEB_PASSPHRASE` | secret | - |
| `NFPM_RPM_KEY_FILE` | secret | - |
| `NFPM_RPM_PASSPHRASE` | secret | - |
| `NIGHTLY_CONCLUSION` | ci-runner | - |
| `NIGHTLY_EVENT` | ci-runner | - |
| `NIGHTLY_RUN_ID` | ci-runner | - |
| `NIGHTLY_URL` | ci-runner | - |
| `NODE_COMPILE_CACHE` | toolchain | - |
| `NODE_ENV` | harness | - |
| `NODE_OPTIONS` | toolchain | - |
| `NODE_VERSION` | toolchain | - |
| `NODE_VERSION_MIN` | toolchain | - |
| `NOTICE` | ci-runner | - |
| `NO_COLOR` | machine-local | - |
| `NPM_DIR` | ci-runner | - |
| `NPM_VERSION` | toolchain | - |
| `OBS_OTLP_CREDENTIALS` | secret | - |
| `OBS_OTLP_CREDENTIALS_ASIA` | secret | - |
| `OBS_OTLP_CREDENTIALS_EU` | secret | - |
| `OBS_OTLP_CREDENTIALS_US` | secret | - |
| `OBS_OTLP_PASSWORD` | secret | - |
| `OBS_OTLP_USERNAME` | secret | - |
| `ONBOARD_NOTICE` | harness | - |
| `OPS_RESET_TIMEOUT_MS` | product-runtime | - |
| `OTEL_ENDPOINT` | secret | - |
| `OUTPUT_FILE` | ci-runner | - |
| `OUT_DIR` | ci-runner | - |
| `PAGE_LOCALE_IMPORTS_ROOT` | gate-seam | - |
| `PATH` | machine-local | - |
| `PENDING_RERUN` | ci-runner | - |
| `PGPASSWORD` | secret | - |
| `PI_GO_FAIL` | gate-seam | - |
| `PI_GO_JSON` | gate-seam | - |
| `PKG_BINARY_NAME` | ci-runner | - |
| `PKG_DESCRIPTION` | ci-runner | - |
| `PKG_HOMEPAGE` | ci-runner | - |
| `PKG_MAINTAINER` | ci-runner | - |
| `PKG_NAME` | ci-runner | - |
| `PKG_PRIORITY` | ci-runner | - |
| `PKG_REPO_MIN_DEBS` | ci-runner | - |
| `PKG_SECTION` | ci-runner | - |
| `PLAN_BOXES_BASE` | gate-seam | - |
| `PLAN_BOXES_MIN_OPEN` | gate-seam | - |
| `PLAN_BOXES_MIN_PLANS` | gate-seam | - |
| `PLAN_BOXES_ROOT` | gate-seam | - |
| `PLAN_CITATIONS_BASE` | gate-seam | - |
| `PLAN_CITATIONS_MAX_SHOWN` | gate-seam | - |
| `PLAN_CITATIONS_OBJECT_MIN` | gate-seam | - |
| `PLAN_CITATIONS_ROOT` | gate-seam | - |
| `PLAN_FOLDERS_MIN_PLANS` | gate-seam | - |
| `PLAN_FOLDERS_ROOT` | gate-seam | - |
| `PLAN_HK_ALLOWLIST` | gate-seam | - |
| `PLAN_HK_CONFIG` | gate-seam | - |
| `PLAN_HK_MIN_FILES` | gate-seam | - |
| `PLAN_HK_ROOT` | gate-seam | - |
| `PLAN_RECORD_CENSUS_DAYS` | gate-seam | - |
| `PLAN_RECORD_CENSUS_EVERY_RUN` | gate-seam | - |
| `PLAN_RECORD_MIN_PLANS` | gate-seam | - |
| `PLAN_RECORD_ROOT` | gate-seam | - |
| `PLATFORM` | ci-runner | - |
| `PLAYER_CSS_ROOT` | gate-seam | - |
| `POINTER_BUMP_ONLY` | ci-runner | - |
| `POLICY_INVENTORY_ROOT` | gate-seam | - |
| `POOL_SAFETY_GATES_DIR` | gate-seam | - |
| `POOL_SAFETY_LOCK` | gate-seam | - |
| `POOL_SAFETY_PORTS_DIR` | gate-seam | - |
| `POSTGRES_DB` | product-runtime | - |
| `POSTGRES_USER` | product-runtime | - |
| `PR` | tombstone | - |
| `PREVIEW_URL` | ci-runner | - |
| `PREVIEW_URL_OVERRIDE` | ci-runner | - |
| `PRE_SHA` | tombstone | - |
| `PROBE_INTERVAL_SECONDS` | ci-runner | - |
| `PROFILER_COVERAGE_ACTION_DIR` | gate-seam | - |
| `PROFILER_COVERAGE_ALLOWLIST` | gate-seam | - |
| `PROFILER_COVERAGE_COVERING_ACTIONS` | gate-seam | - |
| `PROFILER_COVERAGE_MIN_JOBS` | gate-seam | - |
| `PROFILER_COVERAGE_MIN_LINUX` | gate-seam | - |
| `PROFILER_COVERAGE_MIN_WORKFLOWS` | gate-seam | - |
| `PROFILER_COVERAGE_WORKFLOW_DIR` | gate-seam | - |
| `PROFILER_COVERAGE_WRAPPER_DIRS` | gate-seam | - |
| `PROFILER_RUNNER_LABEL` | ci-runner | - |
| `PROGRAMFILES` | machine-local | - |
| `PROVISION_CEPH_CLUSTER` | harness | - |
| `PR_BASE_REF` | ci-runner | - |
| `PR_HEAD_REF` | ci-runner | - |
| `PR_HEAD_SHA` | ci-runner | - |
| `PR_NUMBER` | ci-runner | - |
| `PUBLIC_SITE_URL` | product-runtime | - |
| `PUBLIC_VIDEO_CDN_BASE_URL` | product-runtime | - |
| `PUBLISH_DOCKER_REGISTRY` | ci-runner | - |
| `PWD` | machine-local | - |
| `PYTEST_BIN` | toolchain | - |
| `PYTEST_JOBS` | harness | - |
| `PYTEST_RUN_TIMEOUT_S` | harness | - |
| `PYTEST_VERSION` | toolchain | - |
| `PYTEST_XDIST_VERSION` | toolchain | - |
| `PYTHONPATH` | toolchain | - |
| `PYYAML_VERSION` | toolchain | - |
| `PY_CONTROL_PLANTS_ROOT` | gate-seam | - |
| `QUICK_LANE_FLOOR` | gate-seam | - |
| `QWEN_TTS_ATTN_IMPL` | harness | - |
| `QWEN_TTS_BATCH_SIZE` | harness | - |
| `QWEN_TTS_CLONE_MODEL_ID` | harness | - |
| `QWEN_TTS_CUSTOM_SPEAKER` | harness | - |
| `QWEN_TTS_DEVICE` | harness | - |
| `QWEN_TTS_DTYPE` | harness | - |
| `QWEN_TTS_MAX_CONCURRENCY` | harness | - |
| `QWEN_TTS_MODEL_ID` | harness | - |
| `QWEN_TTS_PYTHON_BIN` | toolchain | - |
| `QWEN_TTS_SAMPLE_RATE_HZ` | harness | - |
| `QWEN_TTS_TUTORIAL_INSTRUCT_PROMPT` | harness | - |
| `QWEN_TTS_USE_VOICE_CLONE_PROMPT` | harness | - |
| `QWEN_TTS_VOICE_REFERENCE_TEXT` | harness | - |
| `R2_JURISDICTION` | product-runtime | - |
| `R2_TOKEN_AUTH_API` | secret | - |
| `RDC_ALLOW_DOWNGRADE` | tombstone | - |
| `RDC_BENCH` | tombstone | note |
| `RDC_BINARY` | harness | - |
| `RDC_DEBUG_RENET_PROVISION` | tombstone | - |
| `RDC_DISABLE_AUTOUPDATE` | tombstone | - |
| `RDC_PROD` | tombstone | - |
| `RDC_RENET_LICENSE` | ci-runner | - |
| `RDC_SKIP_ROUTER_RESTART` | tombstone | - |
| `RDC_SKIP_SETUP_CHECK` | tombstone | - |
| `RDC_TIMING_CHART` | tombstone | - |
| `RDC_TUTORIAL_HWENC` | product-runtime | - |
| `RDC_UPDATE_CHANNEL` | tombstone | - |
| `RDC_UPDATE_INTERVAL_HOURS` | tombstone | - |
| `REASON` | tombstone | - |
| `RECEIPT_LANE` | ci-runner | - |
| `RECEIPT_PATH` | ci-runner | - |
| `REDIACC_ACCOUNT_SERVER` | product-runtime | - |
| `REDIACC_AGENT` | product-runtime | - |
| `REDIACC_ALLOW_CLUSTER_OPS` | product-runtime | - |
| `REDIACC_ALLOW_CONFIG_EDIT` | product-runtime | - |
| `REDIACC_ALLOW_DIRTY_RENET` | product-runtime | - |
| `REDIACC_ALLOW_DOWNGRADE` | product-runtime | - |
| `REDIACC_ALLOW_GRAND_REPO` | product-runtime | - |
| `REDIACC_API_TOKEN` | tombstone | tombstone proof: `packages/cli/src/__tests__/env-tombstones.test.ts` |
| `REDIACC_CI_ROOT` | gate-seam | note |
| `REDIACC_CONFIG` | product-runtime | - |
| `REDIACC_CONFIG_PASSWORD` | secret | - |
| `REDIACC_DAEMON_DEBUG` | tombstone | - |
| `REDIACC_DATASTORE` | product-runtime | - |
| `REDIACC_DATASTORE_USER` | product-runtime | - |
| `REDIACC_DEBUG` | product-runtime | - |
| `REDIACC_DEFAULT_OUTPUT` | product-runtime | - |
| `REDIACC_DEV_PORT_BASE` | harness | - |
| `REDIACC_DISABLE_AUTOUPDATE` | product-runtime | - |
| `REDIACC_DOCKER_GROUP_REEXEC` | product-runtime | - |
| `REDIACC_ENVIRONMENT` | tombstone | note |
| `REDIACC_EXECUTOR_TOKEN` | tombstone | - |
| `REDIACC_GUARD_DIFF_FULL` | gate-seam | - |
| `REDIACC_HOOK_SETTINGS` | harness | - |
| `REDIACC_KEY_USAGE_PROBE` | gate-seam | - |
| `REDIACC_LANG` | product-runtime | - |
| `REDIACC_MASTER_PASSWORD` | secret | - |
| `REDIACC_NO_COLOR` | tombstone | - |
| `REDIACC_NO_DAEMON` | product-runtime | - |
| `REDIACC_NO_DOCKER` | harness | - |
| `REDIACC_PID_WAIT_PROCFS` | harness | - |
| `REDIACC_PROC_BACKEND` | gate-seam | - |
| `REDIACC_PROVISION_LOCK_TIMEOUT_MS` | product-runtime | - |
| `REDIACC_PROXY_URL` | product-runtime | - |
| `REDIACC_REGION` | tombstone | tombstone proof: `packages/cli/src/__tests__/env-tombstones.test.ts` |
| `REDIACC_SKIP_FILE_WRITE_GUARD` | product-runtime | - |
| `REDIACC_SKIP_MACHINE_ACTIVATION` | product-runtime | - |
| `REDIACC_SKIP_ROUTER_RESTART` | product-runtime | - |
| `REDIACC_SKIP_SETUP_CHECK` | product-runtime | - |
| `REDIACC_SMOKE_NO_DOCKER` | harness | - |
| `REDIACC_SSH_LINGER_MS` | product-runtime | - |
| `REDIACC_STARTUP_TIMEOUT` | harness | - |
| `REDIACC_SUBSCRIPTION_TOKEN` | tombstone | - |
| `REDIACC_SUBSCRIPTION_TOKEN_FILE` | tombstone | - |
| `REDIACC_TEAM` | tombstone | tombstone proof: `packages/cli/src/__tests__/env-tombstones.test.ts` |
| `REDIACC_TELEMETRY_DISABLED` | product-runtime | - |
| `REDIACC_TELEMETRY_ENDPOINT` | product-runtime | - |
| `REDIACC_TEST_API_URL` | harness | - |
| `REDIACC_TEST_EMAIL` | harness | - |
| `REDIACC_TEST_ENV_APPLY` | gate-seam | - |
| `REDIACC_TEST_PASSWORD` | secret | - |
| `REDIACC_TEST_TIMEOUT` | harness | - |
| `REDIACC_TIMEOUT_BIN` | harness | - |
| `REDIACC_TOKEN` | secret | - |
| `REDIACC_TOOLCHAIN_LOADED` | toolchain | - |
| `REDIACC_UPDATE_CHANNEL` | product-runtime | - |
| `REDIACC_UPDATE_INTERVAL_HOURS` | product-runtime | - |
| `REDIACC_VIA_DAEMON` | product-runtime | - |
| `REDIACC_VSCODE_PATH` | product-runtime | - |
| `REDIACC_YES` | product-runtime | - |
| `REGIONS_BAKED_FILE` | gate-seam | - |
| `REGIONS_ROOT_FILE` | gate-seam | - |
| `RELEASES_BASE_URL` | ci-runner | - |
| `RELEASES_BUCKET` | ci-runner | - |
| `RELEASE_BUILD` | ci-runner | - |
| `RELEASE_DECIDE_SCRIPT` | gate-seam | - |
| `RELEASE_GPG_PASSPHRASE` | secret | - |
| `RELEASE_GPG_PRIVATE_KEY` | secret | - |
| `RELEASE_GPG_PUBLIC_KEY_FILE` | ci-runner | - |
| `RELEASE_GPG_REVOCATION_CERT` | secret | - |
| `RELEASE_KEY_ROOT` | gate-seam | - |
| `RELEASE_MODE` | ci-runner | - |
| `RELEASE_SIGNING_REQUIRED` | ci-runner | - |
| `RENET_BINARY` | toolchain | - |
| `RENET_BINARY_PATH` | harness | - |
| `RENET_DATA_DIR` | harness | - |
| `RENET_DIR` | gate-seam | - |
| `RENET_DOCKER_IMAGE` | harness | - |
| `RENET_EXPECT_NO_ACCOUNT_SERVER` | harness | - |
| `RENET_ROOT` | harness | - |
| `RENET_TAG` | ci-runner | - |
| `RENET_VERSION` | ci-runner | - |
| `REPO` | tombstone | - |
| `REPO_CHANNEL` | ci-runner | - |
| `REQUESTED` | ci-runner | - |
| `REQUIRED_CHECK` | ci-runner | - |
| `REQUIRED_STREAK` | ci-runner | - |
| `RERUN_EXECUTED` | ci-runner | - |
| `RESPROFILE_ROOT` | gate-seam | - |
| `RESULT_BREAKPOINT_LIFECYCLE` | ci-runner | - |
| `RESULT_BUILD_CLI` | ci-runner | - |
| `RESULT_BUILD_DOCKER` | ci-runner | - |
| `RESULT_BUILD_DOCKER_FAST` | ci-runner | - |
| `RESULT_CHECK_RELEASE_STATE` | ci-runner | - |
| `RESULT_DEPLOY_PREVIEW` | ci-runner | - |
| `RESULT_ELITE_RUN_TEST` | ci-runner | - |
| `RESULT_INITIALIZE` | ci-runner | - |
| `RESULT_LABEL_GUIDE` | ci-runner | - |
| `RESULT_LINUX_ARM64` | ci-runner | - |
| `RESULT_LINUX_X64` | ci-runner | - |
| `RESULT_MACOS_ARM64` | ci-runner | - |
| `RESULT_MACOS_X64` | ci-runner | - |
| `RESULT_OPS_TESTS` | ci-runner | - |
| `RESULT_PACKAGE_TESTS` | ci-runner | - |
| `RESULT_QUALITY` | ci-runner | - |
| `RESULT_REVIEW_GATE` | ci-runner | - |
| `RESULT_RUN_SH_TESTS` | ci-runner | - |
| `RESULT_SMOKE_TEST_PREVIEW` | ci-runner | - |
| `RESULT_STAGE_ARTIFACTS` | ci-runner | - |
| `RESULT_STRIPE_SANDBOX` | ci-runner | - |
| `RESULT_TESTS` | ci-runner | - |
| `RESULT_UPDATE_FLOW_TEST` | ci-runner | - |
| `RESULT_VALIDATE_INSTALL` | ci-runner | - |
| `RESULT_VALIDATE_PROMOTE` | ci-runner | - |
| `RESULT_WINDOWS_ARM64` | ci-runner | - |
| `RESULT_WINDOWS_X64` | ci-runner | - |
| `RETIRE_MIN_WORKFLOWS` | gate-seam | - |
| `RETIRE_ROOT` | gate-seam | - |
| `RETRY_REPO` | ci-runner | - |
| `REVIEW_EPIC` | ci-runner | - |
| `REVIEW_EPIC_PREFIX` | gate-seam | - |
| `REVIEW_MODEL` | ci-runner | - |
| `REVIEW_OUTCOME` | ci-runner | - |
| `REVIEW_STATUS_GATE_SCRIPT` | gate-seam | - |
| `REVIEW_STATUS_HYGIENE_DIR` | gate-seam | - |
| `ROOT_EMAIL` | secret | - |
| `ROUND` | tombstone | - |
| `RSV_FLOOR_FILE` | gate-seam | - |
| `RSV_GRANDFATHER_BEFORE` | gate-seam | - |
| `RUFF_BIN` | toolchain | - |
| `RUFF_VERSION` | toolchain | - |
| `RULESET_REPO` | tombstone | - |
| `RUNNER_ADVICE_ALLOWLIST` | gate-seam | - |
| `RUNNER_ADVICE_BASELINE` | gate-seam | - |
| `RUNNER_ADVICE_WORKFLOW_DIR` | gate-seam | - |
| `RUNNER_LABEL` | ci-runner | - |
| `RUNNER_TEMP` | ci-runner | - |
| `RUN_ALL_GATES_DIR` | gate-seam | - |
| `RUN_ALL_JOBS` | gate-seam | - |
| `RUN_ID` | ci-runner | - |
| `RUN_URL` | tombstone | - |
| `RUSTFS_ACCESS_KEY` | secret | - |
| `RUSTFS_SECRET_KEY` | secret | - |
| `SCOPE_MODE` | ci-runner | - |
| `SCOPE_SHADOW_OUT` | gate-seam | - |
| `SCOPE_SHADOW_TIMEOUT` | gate-seam | - |
| `SECRET_RENAME_MIN_FILES` | gate-seam | - |
| `SECRET_SCOPE_ROOT` | gate-seam | - |
| `SELLER_ADDRESS_LINE1` | secret | - |
| `SELLER_ADDRESS_LINE2` | secret | - |
| `SELLER_CITY` | secret | - |
| `SELLER_COUNTRY` | secret | - |
| `SELLER_EMAIL` | secret | - |
| `SELLER_NAME` | secret | - |
| `SELLER_POSTAL_CODE` | secret | - |
| `SELLER_REGISTRATION_NUMBER` | secret | - |
| `SELLER_VAT_NUMBER` | secret | - |
| `SERVICE_STATUS_NOW` | gate-seam | - |
| `SHAPE_PROBE_CACHE` | gate-seam | - |
| `SHARD_INDEX` | ci-runner | - |
| `SHARD_OF` | ci-runner | - |
| `SHELLCHECK_VERSION` | toolchain | - |
| `SHELL_MAX_LINES` | gate-seam | - |
| `SHFMT_MIN_FILES` | gate-seam | - |
| `SHFMT_VERSION` | toolchain | - |
| `SHIM_GOLDEN` | gate-seam | - |
| `SHIM_NPM_EXIT` | gate-seam | - |
| `SHIM_NPX_EXIT` | gate-seam | - |
| `SIG` | tombstone | - |
| `SIGNING_COVERAGE_BUILDER` | gate-seam | - |
| `SIGNING_COVERAGE_ROOT` | gate-seam | - |
| `SIG_COUNT` | tombstone | - |
| `SKIP_RELEASE` | ci-runner | - |
| `SMOKE_TEST_TOKEN` | secret | - |
| `SMTP_FROM` | secret | - |
| `SMTP_HOST` | secret | - |
| `SMTP_PASSWORD` | secret | - |
| `SMTP_PORT` | secret | - |
| `SMTP_USER` | secret | - |
| `SOAK_DAYS` | ci-runner | - |
| `SOME_ROOT` | gate-seam | note |
| `SOURCE_DATE_EPOCH` | ci-runner | - |
| `SRC_PREFIX` | ci-runner | - |
| `SSH_KEY` | secret | - |
| `SSH_USER` | harness | - |
| `STAGING_GUARD_ROOT` | gate-seam | - |
| `STAGING_GUARD_TARGET` | gate-seam | - |
| `STATE_isPost` | ci-runner | note |
| `STATE_log` | ci-runner | - |
| `STATE_out` | ci-runner | - |
| `STATE_pid` | ci-runner | - |
| `STATE_skip` | ci-runner | - |
| `STATE_start` | ci-runner | - |
| `STATE_strict` | ci-runner | - |
| `STEPS` | tombstone | - |
| `STEPS_JSON` | ci-runner | - |
| `STOPHOOK_CHILD` | harness | - |
| `STRIPE_PUBLISHABLE_KEY` | secret | - |
| `STRIPE_SANDBOX_PUBLISHABLE_KEY` | secret | - |
| `STRIPE_SANDBOX_SECRET_KEY` | secret | - |
| `STRIPE_SANDBOX_WEBHOOK_SECRET` | secret | - |
| `STRIPE_SANDBOX_WEBHOOK_SECRET_ID` | secret | - |
| `STRIPE_SECRET_KEY` | secret | - |
| `STRIPE_WEBHOOK_SECRET` | secret | - |
| `STRIPE_WEBHOOK_SECRET_ASIA` | secret | - |
| `STRIPE_WEBHOOK_SECRET_EU` | secret | - |
| `STRIPE_WEBHOOK_SECRET_ID` | secret | - |
| `STRIPE_WEBHOOK_SECRET_US` | secret | - |
| `STUCK_THRESHOLD_MIN` | ci-runner | - |
| `SUBSCRIPTION_SCHEMA_OUT` | gate-seam | - |
| `SUDO_USER` | machine-local | - |
| `SUFFIX` | ci-runner | - |
| `SUPPRESSION_LIVENESS_ROOT` | gate-seam | - |
| `SWALLOWED_SCAN_DIRS` | gate-seam | - |
| `SWALLOWED_SCAN_ROOT` | gate-seam | - |
| `SYNCPACK_SOURCES_MIN` | gate-seam | - |
| `SYNCPACK_SOURCES_ROOT` | gate-seam | - |
| `TAG` | ci-runner | - |
| `TARGET` | ci-runner | - |
| `TARGET_RUN_ID` | ci-runner | - |
| `TEMPLATE` | tombstone | - |
| `TIMEOUT_SECS` | ci-runner | - |
| `TMPDIR` | machine-local | - |
| `TOKEN` | secret | - |
| `TRACE` | gate-seam | - |
| `TRACKED_CRED_ROOT` | gate-seam | - |
| `TRACK_PROGRESS` | ci-runner | - |
| `TRANSLATION_FRESHNESS_CHANGED_FILES` | gate-seam | - |
| `TRAPGUARD_PROBE_PATH` | gate-seam | - |
| `TRAP_FLOOR` | gate-seam | - |
| `TREE_SHAPE_MIN_AGENT` | gate-seam | - |
| `TREE_SHAPE_MIN_ROOT` | gate-seam | - |
| `TREE_SHAPE_MIN_ROOT_DIRS` | gate-seam | - |
| `TREE_SHAPE_ROOT` | gate-seam | - |
| `TREE_SNAPSHOT` | gate-seam | - |
| `TURNSTILE_SITE_KEY` | secret | - |
| `TUTORIAL_BACKUP_HOST` | harness | - |
| `TUTORIAL_CHAR_DELAY` | harness | - |
| `TUTORIAL_LOG_DIR` | harness | - |
| `TUTORIAL_MACHINE_IP` | harness | - |
| `TUTORIAL_PLAYER_GATE_PORT` | gate-seam | - |
| `TUTORIAL_RDC_CMD` | harness | - |
| `TUTORIAL_S3_ENDPOINT` | harness | - |
| `TUTORIAL_SSH_KEY` | secret | - |
| `TWIN_PARITY_ALWAYS_DRIVE` | gate-seam | - |
| `UNVERIFIED_DOWNLOAD_ALLOWLIST` | gate-seam | - |
| `USER` | machine-local | - |
| `USERPROFILE` | machine-local | - |
| `UV_SHA256_DARWIN_AARCH64` | toolchain | - |
| `UV_SHA256_DARWIN_X86_64` | toolchain | - |
| `UV_SHA256_LINUX_AARCH64` | toolchain | - |
| `UV_SHA256_LINUX_X86_64` | toolchain | - |
| `UV_VERSION` | toolchain | - |
| `VARIANT` | ci-runner | - |
| `VENDORED_BLOCKER_ROOT` | gate-seam | - |
| `VERSION` | ci-runner | - |
| `VISUAL` | machine-local | - |
| `VITEST` | product-runtime | - |
| `VITE_CI_MODE` | product-runtime | - |
| `VITE_TURNSTILE_SITE_KEY` | product-runtime | - |
| `VM_BRIDGE` | harness | - |
| `VM_CEPH_NODES` | harness | - |
| `VM_CONTROL` | harness | - |
| `VM_IMAGE` | harness | - |
| `VM_NET` | harness | - |
| `VM_NET_BASE` | harness | - |
| `VM_NET_OFFSET` | harness | - |
| `VM_RAM_CEPH` | harness | - |
| `VM_RAM_WORKER` | harness | - |
| `VM_WORKERS` | harness | - |
| `WATCHDOG_CLAUDE_MODEL` | ci-runner | - |
| `WATCHDOG_DEADLINE_SECONDS` | ci-runner | - |
| `WATCHDOG_EXCLUDE_PATTERNS` | ci-runner | - |
| `WATCHDOG_HELD_CANCEL_MAX_SECONDS` | ci-runner | - |
| `WATCHDOG_INSTALL_VALIDATION_PATTERNS` | ci-runner | - |
| `WATCHDOG_LOG_CAPTURE_DIR` | ci-runner | - |
| `WATCHDOG_NO_RETRY_PATTERNS` | ci-runner | - |
| `WATCHDOG_PENDING_RERUN` | ci-runner | - |
| `WATCHDOG_PR_NUMBER` | ci-runner | - |
| `WATCHDOG_RETRY_ALLOWLIST_PATTERNS` | ci-runner | - |
| `WATCHDOG_SKIP_RERUN` | ci-runner | - |
| `WATCHDOG_TARGET_RUN_ID` | ci-runner | - |
| `WATCHDOG_WAIT_PATTERNS` | ci-runner | - |
| `WEB_TAG` | ci-runner | - |
| `WFG_PROBE` | gate-seam | - |
| `WHY_ON_EDIT_CAP` | harness | - |
| `WHY_ON_EDIT_SEEN_MAX` | harness | - |
| `WHY_ON_EDIT_SIMILAR` | harness | - |
| `WINDIR` | machine-local | - |
| `WORKER2_IP` | harness | - |
| `WORKERS_ONLY` | ci-runner | - |
| `WORKER_IDLE_BLOCK_MIN` | harness | - |
| `WORKER_IP` | harness | - |
| `WORKER_NAME` | ci-runner | - |
| `WORKFLOW_DIR` | gate-seam | - |
| `WORKFLOW_FILE` | gate-seam | - |
| `WORKFLOW_INLINE_ONLY` | gate-seam | - |
| `WORKLIST_AGENTS_DIR` | harness | - |
| `WORKLIST_AGENT_ADOPT_MAX_MIN` | harness | - |
| `WORKLIST_AGENT_BRANCH` | harness | - |
| `WORKLIST_AGENT_HINT` | harness | - |
| `WORKLIST_AGENT_HINT_MAX_PER_SESSION` | harness | - |
| `WORKLIST_AGENT_HINT_MIN_MARGIN` | harness | - |
| `WORKLIST_AGENT_HINT_MIN_SCORE` | harness | - |
| `WORKLIST_AGENT_HINT_REFRESH_MIN` | harness | - |
| `WORKLIST_AGENT_PUSHBACK` | harness | - |
| `WORKLIST_AGENT_STATE_MAX_CHARS` | harness | - |
| `WORKLIST_AGENT_STATE_STALE_MIN` | harness | - |
| `WORKLIST_ALWAYS_FULL_MAX` | harness | - |
| `WORKLIST_ARCHIVE_HOURS` | harness | - |
| `WORKLIST_BACKLOG_MAX_PER_SESSION` | harness | - |
| `WORKLIST_BACKOFF_NOTE_MIN` | harness | - |
| `WORKLIST_BGSWEEP_AGE_MIN` | harness | - |
| `WORKLIST_BG_OUTPUT_DIR` | harness | - |
| `WORKLIST_BG_REPORT_MIN` | harness | - |
| `WORKLIST_BG_STALE_MIN` | harness | - |
| `WORKLIST_BIG_OPEN_FLOOR` | harness | - |
| `WORKLIST_BIG_TOP_N` | harness | - |
| `WORKLIST_BRAVE_MAX_FIRES` | harness | - |
| `WORKLIST_BRAVE_TTL_MIN` | harness | - |
| `WORKLIST_BRIEF_STALE_MIN` | harness | - |
| `WORKLIST_BULK_FILE_THRESHOLD` | harness | - |
| `WORKLIST_CADENCE` | harness | - |
| `WORKLIST_CADENCE_MAX` | harness | - |
| `WORKLIST_CI_CACHE_FINAL_S` | harness | - |
| `WORKLIST_CI_CACHE_LIVE_S` | harness | - |
| `WORKLIST_CI_FORCE_MIN_AGE` | harness | - |
| `WORKLIST_CI_FORCE_PER_STOP` | harness | - |
| `WORKLIST_CI_MAX_BLOCKS` | harness | - |
| `WORKLIST_CI_QUEUE_CACHE_S` | harness | - |
| `WORKLIST_CI_QUEUE_DEPTH` | harness | - |
| `WORKLIST_CI_QUEUE_MIN` | harness | - |
| `WORKLIST_CI_RETRY_PATTERNS` | harness | - |
| `WORKLIST_DEAD_HOURS` | harness | - |
| `WORKLIST_DEFER_AUDIT_BATCH` | harness | - |
| `WORKLIST_DEFER_AUDIT_MIN` | harness | - |
| `WORKLIST_DEFER_EXEC_PER_STOP` | harness | - |
| `WORKLIST_DEFER_WINDOW_MIN` | harness | - |
| `WORKLIST_DESIGN_DOCS` | harness | - |
| `WORKLIST_DOCS_DRIFT_MAX` | harness | - |
| `WORKLIST_EPICS_LEDGER` | harness | - |
| `WORKLIST_FOCUS` | harness | - |
| `WORKLIST_GUIDE_MAX` | harness | - |
| `WORKLIST_HANDOFF_STALE_HOURS` | harness | - |
| `WORKLIST_HARNESS_PID` | harness | - |
| `WORKLIST_HINTS_FILE` | harness | - |
| `WORKLIST_IDLE_EDGE_EPSILON_S` | harness | - |
| `WORKLIST_INTENT_DEFAULT_MIN` | harness | - |
| `WORKLIST_INTENT_MAX_MIN` | harness | - |
| `WORKLIST_JUDGE` | harness | - |
| `WORKLIST_JUDGE_BUDGET_USD` | harness | - |
| `WORKLIST_JUDGE_CACHE_MIN` | harness | - |
| `WORKLIST_JUDGE_MODEL` | harness | - |
| `WORKLIST_JUDGE_TIMEOUT_S` | harness | - |
| `WORKLIST_JUSTIFY_AGE_MIN` | harness | - |
| `WORKLIST_JUSTIFY_PER_STOP` | harness | - |
| `WORKLIST_LADDER_INVESTIGATE_MIN` | harness | - |
| `WORKLIST_LADDER_PING_MIN` | harness | - |
| `WORKLIST_LADDER_RESOLVE_MIN` | harness | - |
| `WORKLIST_LIVE_MIN` | harness | - |
| `WORKLIST_MIGRATE_PLANS_SHOW` | harness | - |
| `WORKLIST_MIGRATE_PLAN_MIN_OPEN` | harness | - |
| `WORKLIST_OUTQ_MAX` | harness | - |
| `WORKLIST_PHANTOM_MIN` | harness | - |
| `WORKLIST_PLANFID_MIN_TASKS` | harness | - |
| `WORKLIST_PLANFID_RATIO` | harness | - |
| `WORKLIST_PLANFID_RECALL_FLOOR` | harness | - |
| `WORKLIST_PLANFID_SCAN_CAP` | harness | - |
| `WORKLIST_PLANFID_TASK_MATCH` | harness | - |
| `WORKLIST_PLANFID_UMBRELLA_WORDS` | harness | - |
| `WORKLIST_PLANFILE_MAX_BYTES` | harness | - |
| `WORKLIST_PLANFILE_MAX_READ` | harness | - |
| `WORKLIST_PLANFILE_PLANS_SHOW` | harness | - |
| `WORKLIST_PLANFILE_SHOW` | harness | - |
| `WORKLIST_PLANFILE_STALE_SHOW` | harness | - |
| `WORKLIST_PLAN_DRIFT_MAX` | harness | - |
| `WORKLIST_PLAN_DRIFT_MIN` | harness | - |
| `WORKLIST_PLAN_ORIENT_BYTES` | harness | - |
| `WORKLIST_PLAN_ORIENT_FILES` | harness | - |
| `WORKLIST_POLL_FULL_MAX_MIN` | harness | - |
| `WORKLIST_POLL_SCHEDULE_RE` | harness | - |
| `WORKLIST_POLL_WINDOW_S` | harness | - |
| `WORKLIST_POPUP_PROBABILITY` | harness | - |
| `WORKLIST_PROFILE` | harness | - |
| `WORKLIST_PROGRAM_SURFACE` | harness | - |
| `WORKLIST_PROJECTS_DIR` | harness | - |
| `WORKLIST_PROOFCHECK_MAX_FIRES` | harness | - |
| `WORKLIST_PROOFCHECK_TTL_MIN` | harness | - |
| `WORKLIST_PUBLISH_REF` | harness | - |
| `WORKLIST_PUBLISH_ROOT` | harness | - |
| `WORKLIST_QUIET_WAKES` | harness | - |
| `WORKLIST_RECORD_BLOB_RATIO` | harness | - |
| `WORKLIST_RECORD_MAX_BYTES` | harness | - |
| `WORKLIST_RECORD_PER_BOX_BYTES` | harness | - |
| `WORKLIST_REGGATE_CAP` | harness | - |
| `WORKLIST_REGGATE_DEBT_GRACE_MIN` | harness | - |
| `WORKLIST_REGGATE_TICK_FLOOD` | harness | - |
| `WORKLIST_REGGATE_TIMEOUT_S` | harness | - |
| `WORKLIST_REGISTRY_OVERRIDE_FILE` | gate-seam | - |
| `WORKLIST_REPORTS_DIR` | harness | - |
| `WORKLIST_REPORT_INDEX_READ_MAX_BYTES` | harness | - |
| `WORKLIST_REPORT_REFRESH_MIN` | harness | - |
| `WORKLIST_REPORT_RETENTION_DAYS` | harness | - |
| `WORKLIST_REPORT_SCAN_IDLE_MIN` | harness | - |
| `WORKLIST_REPORT_SCAN_LIVE_MIN` | harness | - |
| `WORKLIST_REPORT_SCAN_LOOKBACK_DAYS` | harness | - |
| `WORKLIST_REPORT_SILENT_FLOOR` | harness | - |
| `WORKLIST_REPORT_SURFACE_MAX` | harness | - |
| `WORKLIST_REPORT_TRANSCRIPT_MAX_BYTES` | harness | - |
| `WORKLIST_REQUEST_DEAD_MIN` | harness | - |
| `WORKLIST_REQUEST_GRACE_MIN` | harness | - |
| `WORKLIST_REQUEST_STALE_MIN` | harness | - |
| `WORKLIST_REVIEW_MAX_BLOCKS` | harness | - |
| `WORKLIST_ROSTER_MAX` | harness | - |
| `WORKLIST_SESSION_ID` | harness | - |
| `WORKLIST_SHAPEDUP_WIDE_CAP` | harness | - |
| `WORKLIST_SHAPE_MAX_FIRES` | harness | - |
| `WORKLIST_SHAPE_TTL_MIN` | harness | - |
| `WORKLIST_SOLO_MIN` | harness | - |
| `WORKLIST_SOURCE_OVERRIDE_FILE` | gate-seam | - |
| `WORKLIST_STORE_DIR` | harness | - |
| `WORKLIST_STUCK_ROUNDS` | harness | - |
| `WORKLIST_STUCK_SUPERVISED_MAX_MIN` | harness | - |
| `WORKLIST_SUBMODULE_DECIDED_LATCH_MIN` | harness | - |
| `WORKLIST_SUBMODULE_LATCH_MIN` | harness | - |
| `WORKLIST_SWEEP_MAX_FIRES` | harness | - |
| `WORKLIST_SWEEP_TTL_MIN` | harness | - |
| `WORKLIST_TAIL_BYTES` | harness | - |
| `WORKLIST_TASKS_DIR` | harness | - |
| `WORKLIST_TEAMMATE_FRESH_MIN` | harness | - |
| `WORKLIST_TEAMMATE_TAIL_BYTES` | harness | - |
| `WORKLIST_TICK_EVIDENCE_MAX` | harness | - |
| `WORKLIST_TICK_EVIDENCE_MIN` | harness | - |
| `WORKLIST_UNREAD_INVARIANT_MIN` | harness | - |
| `WORKLIST_UNREAD_ROTATE_MIN` | harness | - |
| `WORKLIST_WAITER_GRACE_NUDGES` | harness | - |
| `WORKLIST_WAITER_NUDGE_S` | harness | - |
| `WORKLIST_WAITER_STALE_S` | harness | - |
| `WORKLIST_WAIT_SCAN_S` | harness | - |
| `WORKLIST_WAIT_TICK_S` | harness | - |
| `WORKLIST_WAIT_TIMEOUT_MIN` | harness | - |
| `WORKLIST_WHY_MAX_CHARS` | harness | - |
| `WORKLIST_WHY_MAX_RECORDS` | harness | - |
| `WR_CONCLUSION` | ci-runner | - |
| `WR_EVENT` | ci-runner | - |
| `WR_HEAD_BRANCH` | ci-runner | - |
| `WR_HEAD_SHA` | ci-runner | - |
| `WR_HTML_URL` | ci-runner | - |
| `WR_RUN_ID` | ci-runner | - |
| `WSL_DISTRO_NAME` | machine-local | - |
| `X` | gate-seam | note |
| `X25519_PUBLIC_KEY` | tombstone | tombstone proof: `packages/cli/src/__tests__/env-tombstones.test.ts`, `packages/cli/src/services/__tests__/account-client.test.ts` |
| `XDG_CACHE_HOME` | machine-local | - |
| `XDG_CONFIG_HOME` | machine-local | - |
| `XDG_RUNTIME_DIR` | machine-local | - |
| `XDG_STATE_HOME` | machine-local | - |
| `_WL_SITEPROFILE` | harness | - |

955 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->
