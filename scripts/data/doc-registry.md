# Derived registry (generated)

Every table below is rewritten from the tree by `scripts/gen-docs.ts`. Nothing in a region is
typed by hand, and `npx tsx scripts/gen-docs.ts` (no flags) fails if any of it has drifted.

`npm run gen:docs` runs the VERIFY mode, not the writer. Regenerating is
`npx tsx scripts/gen-docs.ts --write`, spelled out rather than given a key, because a one-word
way to overwrite every generated region is a way to overwrite them without reading the diff.
The gate that runs all of this in CI is `gate-test:docs-gen`
(`.ci/scripts/test/gates/test-docs-gen.sh`), which drives the generator in both directions:
green on the tree as it stands, and red over a single perturbed row.

This file is the phase 0 home for those regions. It is deliberately NOT one of the documents a
reader is sent to: `CLAUDE.md`, `docs/agent-reference/ci-gates.md`,
`docs/agent-reference/suppressions.md` and `docs/agent-reference/TRAPS.md` each have exactly one
writer during the tooling transformation, and phase 0 is not that writer. Those documents opt in
later by carrying the same markers, which needs no change to the generator: targets are
discovered by scanning for the marker, not from a list.

The frozen companion to this file is `scripts/data/doc-registry-preport.json`, which records the
row SET of every provider as it stood before the ports began. A count floor cannot catch a
silent drop -- a floor of 300 still passes after 88 of 388 rows vanish, and count equality still
passes when 88 are swapped for 88 others -- so membership is the only instrument that names what
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
| check:ci-agent-browser-exit | quality-static / agent-browser exit status | yes | yes | no |
| check:ci-agent-hint-liveness | quality-content / Agent hints can actually fire | yes | no | no |
| check:ci-allowlist-key-matching | quality-static / Allowlist key matching | yes | no | no |
| check:ci-anchor-integrity | quality-www-build / Redirects | yes | yes | no |
| check:ci-app-admin-perm | quality-code / App admin permission | yes | no | no |
| check:ci-audit-coverage | quality-static / Check audit logging coverage for CLI operations | yes | no | no |
| check:ci-autopilot-bp-align | test: .ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh | yes | no | no |
| check:ci-autopilot-workflow | test: .ci/scripts/test/gates/test-autopilot-workflow-invariants.sh | yes | no | no |
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
| check:ci-captcha-recovery | quality-www-build / Captcha recovery | yes | no | no |
| check:ci-ceph-image-pin | quality-code / Ceph image pin freshness | yes | no | no |
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
| check:ci-control-vacuity | quality-code / Control-first gates prove their plant landed | yes | no | no |
| check:ci-css-dom-refs | quality-content / CSS DOM references | yes | no | no |
| check:ci-cta-bolt | quality-www-build / CTA bolt | yes | yes | no |
| check:ci-dead-bash | quality-code / Dead bash | yes | yes | no |
| check:ci-dead-case-arms | test: .ci/scripts/test/gates/test-dead-case-arms.sh | yes | no | no |
| check:ci-dead-css | quality-content / Dead CSS | yes | no | no |
| check:ci-dead-service-methods | quality-content / Dead service methods | yes | no | no |
| check:ci-dead-translation-keys | quality-i18n / i18n | yes | no | no |
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
| check:ci-environment-names | quality-static / Environment names | yes | no | no |
| check:ci-external-links | quality-content / External links | yes | yes | no |
| check:ci-fetch-integrity | quality-code / CI fetch integrity | yes | no | no |
| check:ci-fetch-retry | quality-code / Fetch retry | yes | no | no |
| check:ci-fixture-event-timestamps | quality-code / Fixture event timestamps | yes | no | no |
| check:ci-form-validation | test: .ci/scripts/test/gates/test-form-validation.sh | yes | no | no |
| check:ci-format-scope | quality-code / Format command covers its config's scope | yes | yes | no |
| check:ci-gate-bind | quality-code / Gate binding | yes | no | no |
| check:ci-gate-cwd-independence | quality-code / Gate cwd independence | yes | no | no |
| check:ci-gate-id-convention | quality-static / Gate registration follows the gates/ convention | yes | no | no |
| check:ci-gate-manifest | quality-code / Gate manifest self-consistency | yes | no | no |
| check:ci-gate-prerequisites | quality-code / Gate prerequisites | yes | no | no |
| check:ci-gate-reachability-coverage | quality-static / Gate-reachability probe agrees with registrations | yes | no | no |
| check:ci-gates-lock | quality-code / Gates lock | yes | no | no |
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
| check:ci-hook-integrity | quality-code / Hook integrity | yes | no | no |
| check:ci-hook-worklist-suite | quality-packages / Stop-hook worklist suite | yes | yes | no |
| check:ci-hooks-resolvable | quality-static / Hooks resolvable | yes | no | no |
| check:ci-host-toolchain-coverage | quality-code / Host toolchain runtime coverage | yes | no | no |
| check:ci-hydration-clean | test: .ci/scripts/test/gates/test-hydration-clean.sh | yes | no | no |
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
| check:ci-i18n-page-locale-imports | quality-i18n / i18n | yes | no | no |
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
| check:ci-install-sh-config | quality-static / install.sh config tests | yes | no | no |
| check:ci-jq-boolean-default | quality-code / jq boolean defaults | yes | no | no |
| check:ci-judged-rule-wiring | quality-code / Judged rule wiring | yes | no | no |
| check:ci-knip-blockers | quality-code / knip BLOCKER reasons | yes | no | no |
| check:ci-label-inventory | test: .ci/scripts/test/gates/test-label-inventory.sh | yes | no | no |
| check:ci-label-refs | test: .ci/scripts/test/gates/test-label-references.sh | yes | no | no |
| check:ci-landmarks | quality-www-build / Landmarks | yes | yes | no |
| check:ci-layout-overflow | test: .ci/scripts/test/gates/test-layout-overflow.sh | yes | no | no |
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
| check:ci-pathspec-scope | quality-static / Pathspec scope | yes | no | no |
| check:ci-peer-deps | quality-code / Verify no peer dependency conflicts | yes | no | no |
| check:ci-pipefail-grep-q | quality-code / No racing pipefail/grep -q detectors | yes | yes | no |
| check:ci-plan-boxes | quality-branch / Plan checkbox ledger | yes | no | no |
| check:ci-plan-citations | quality-branch / Plan citations | yes | no | no |
| check:ci-plan-housekeeping | quality-i18n / Plan file housekeeping | yes | no | no |
| check:ci-plan-record | quality-branch / Plan records | yes | no | no |
| check:ci-player-css-scope | quality-www-build / Player CSS scope | yes | yes | no |
| check:ci-pool-writer-safety | quality-static / Pool-registered tests do not write the real tree | yes | no | no |
| check:ci-pr-epic-block | quality-code / PR epic block matches the published worklist | yes | no | no |
| check:ci-pr-head-ref-completeness | quality-code / PR_HEAD_REF completeness | yes | no | no |
| check:ci-pr-task-trailers | quality-code / Every commit names its epic | yes | no | no |
| check:ci-pricing-consistency | quality-content / Pricing consistency | yes | no | no |
| check:ci-probe-parity | quality-static / Capability-probe parity | yes | no | no |
| check:ci-profiler-coverage | test: .ci/scripts/test/gates/test-profiler-coverage.sh | yes | no | no |
| check:ci-pytest | quality-static / Python package tests | yes | no | no |
| check:ci-python-gate-deps | quality-static / Python gate deps | yes | no | no |
| check:ci-python-lint | quality-static / Python lint + format (ruff) | yes | no | no |
| check:ci-quality-gates | quality-security / Quality-gate unit tests | no | no | no |
| check:ci-rdc-sh-env | quality-static / rdc.sh env tests | yes | no | no |
| check:ci-recovery-context | quality-go / Check recovery functions get an uncancellable context | yes | no | no |
| check:ci-redirect-integrity | quality-www-build / Redirects | yes | yes | no |
| check:ci-redirects | quality-www-build / Redirects | no | yes | no |
| check:ci-regions-sync | test: .ci/scripts/test/gates/test-regions-sync.sh | yes | no | no |
| check:ci-release-bump-skip | test: .ci/scripts/quality/check-release-bump-skip.sh | yes | no | no |
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
| check:ci-scope-scripts-reachability | quality-security / Scope map — reachable scripts/ paths force full CI | yes | yes | no |
| check:ci-script-exec-bit | quality-code / Block non-executable invoked scripts | yes | yes | no |
| check:ci-search-index | quality-i18n / Search index | yes | no | no |
| check:ci-secret-reachability | quality-security / Secret reachability | yes | no | no |
| check:ci-secret-scope | quality-security / Secret scope | yes | no | no |
| check:ci-security-audit | quality-security / Audit | yes | yes | no |
| check:ci-sentence-wrapping | quality-content / Sentence wrapping | yes | no | no |
| check:ci-seo | quality-www-build / SEO | no | yes | no |
| check:ci-seo-core | quality-www-build / SEO | yes | yes | no |
| check:ci-setup-idempotency | quality-code / Setup path idempotency | yes | no | no |
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
| check:ci-subscription-schema | quality-go / Check subscription schema consistency | yes | no | no |
| check:ci-suppression-liveness | quality-security / Suppression liveness — are our allowlist entries still needed? | yes | no | no |
| check:ci-svg-theme-reach | quality-content / SVG theme reach | yes | no | no |
| check:ci-syncpack-reasons | quality-security / BLOCKER validator — syncpack versionGroups | yes | no | no |
| check:ci-syncpack-sources | quality-code / syncpack source coverage | yes | no | no |
| check:ci-test-account-web | quality-packages / Account portal unit tests | yes | yes | no |
| check:ci-test-file-orphans | quality-security / Test-file orphan check | yes | no | no |
| check:ci-test-gate-wiring | quality-content / Test-gate wiring | yes | no | no |
| check:ci-test-scripts-reachable | quality-code / Test suites are CI-reachable | yes | no | no |
| check:ci-timeout-headroom | quality-static / CI job timeout headroom | yes | no | no |
| check:ci-toolchain-env-dockerfile-sync | quality-code / Toolchain env/Dockerfile sync | yes | no | no |
| check:ci-toolchain-pins | quality-code / Toolchain pins | yes | yes | no |
| check:ci-tracked-credentials | quality-security / Tracked credentials | yes | no | no |
| check:ci-tracked-sidecars | quality-static / Tracked runtime sidecars | yes | no | no |
| check:ci-trap-registry | quality-code / Trap registry dispositions | yes | no | no |
| check:ci-tutorial-caption-sync | quality-content / Validate published tutorial word-timing sync (real ASR alignment, not estimated) | yes | no | no |
| check:ci-tutorial-card-fonts | quality-content / Validate tutorial card fonts cover every locale | yes | no | no |
| check:ci-tutorial-casts | quality-content / Block fallback hacks and error output in tutorial recordings | yes | no | no |
| check:ci-tutorial-cli-validity | quality-content / Tutorial CLI validity | yes | no | no |
| check:ci-tutorial-commands | quality-content / Validate tutorial storyboard commands against the live CLI | yes | no | no |
| check:ci-tutorial-healthcheck-headroom | quality-packages / Tutorial healthcheck headroom | yes | no | no |
| check:ci-tutorial-no-skips | quality-content / Tutorials cannot skip themselves | yes | no | no |
| check:ci-tutorial-noninteractive | quality-content / Validate tutorial commands are non-interactive | yes | no | no |
| check:ci-tutorial-parity | quality-content / Validate tutorial cast/storyboard/transcript/mdx parity | yes | no | no |
| check:ci-tutorial-render-queue | test: .ci/scripts/test/gates/test-tutorial-render-queue.sh | yes | no | no |
| check:ci-typecheck-scope-coverage | quality-code / Typecheck scope coverage | yes | yes | no |
| check:ci-unverified-downloads | quality-security / Check every Dockerfile download is cryptographically verified | yes | no | no |
| check:ci-video-player-invariants | quality-content / Video player invariants | yes | no | no |
| check:ci-viewport-unit-mixing | quality-content / Dead CSS | yes | no | no |
| check:ci-watch-recipe | quality-code / CI-watch recipe has one source | yes | no | no |
| check:ci-worker-secret-names | quality-code / Worker secret names | yes | no | no |
| check:ci-workflow-env-provision | quality-static / Workflow env provision | yes | no | no |
| check:ci-workflow-gates | quality-code / Workflow structural gates | yes | no | no |
| check:ci-workflow-invariants | test: .ci/scripts/test/gates/test-ci-workflow-invariants.sh | yes | no | no |
| check:ci-workflow-orphan-step-keys | quality-code / Workflow orphan step keys | yes | no | no |
| check:ci-workflow-submodule-deps | quality-static / Workflow submodule deps | yes | no | no |
| check:ci-workflows | quality-code / Workflow banned patterns | yes | yes | no |
| check:ci-worklist-event-builders | quality-code / Worklist event builders | yes | no | no |
| check:ci-worklist-path-resolution | quality-code / Worklist path resolution | yes | no | no |
| check:ci-www-build-token | quality-code / www build token | yes | no | no |
| check:cli-docs | quality-i18n / i18n | yes | no | no |
| check:cli-examples | quality-code / CLI examples | yes | yes | no |
| check:deps | quality-content / External dependency freshness | yes | yes | no |
| check:format | quality-code / Format | yes | no | no |
| check:i18n | quality-i18n / i18n | no | yes | no |
| check:i18n:key-usage | quality-i18n / i18n | yes | no | no |
| check:lint | quality-code / Lint | no | yes | no |
| check:lint:account | quality-code / Lint | yes | yes | no |
| check:lint:cli | quality-code / Lint | yes | yes | no |
| check:lint:tooling | quality-code / Lint | yes | yes | no |
| check:lint:web | quality-code / Lint | yes | yes | no |
| check:test-cli | quality-packages / Run CLI unit tests | yes | yes | no |
| check:test-shared | quality-packages / Run shared package tests | yes | no | no |
| check:test-workers | quality-www-build / Worker unit tests (workers/www) | yes | yes | no |
| check:test-www | quality-packages / Run www unit tests | yes | no | no |
| check:test:tutorial-player | quality-packages / Tutorial player release gate | yes | yes | no |
| check:types | quality-code / TypeScript | yes | yes | no |
| check:version | quality-code / Versions | yes | no | no |
| gate-test:actions-release-age | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:age-check | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:assert-edge-tag-exists | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:autopilot-breakpoint-alignment | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:autopilot-guide-comment | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:autopilot-harness | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:autopilot-no-bypass | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:autopilot-workflow-invariants | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:backfill-commit-resolve | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:blocker-golden-corpus | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:blocker-validator | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:breakpoint-drift | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:breakpoint-mode-selection | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:breakpoint-naming | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:breakpoint-pins | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:breakpoint-portability | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:breakpoint-secret-exposure | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:breakpoint-teardown | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:bws-env | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:bws-map | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:channel-for-event | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:ci-compat-prose | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:ci-complete-tiers | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:ci-job-aggregation | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:ci-parity | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:ci-runner | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:ci-trace-branch | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:ci-workflow-invariants | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:claude-hooks | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:client-bundle-budget | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:commit-identity | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:dead-bash | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:dead-case-arms | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:detect-bump-type | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:devbox-hostname | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:devbox-probes | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:devcontainer-pin-freshness | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:dispatch-release | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:doc-region-parity | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:docs-gen | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:e2e-coverage | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:edge-verify-retries | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:embed-arch-parity | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:embed-asset-freshness | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:embed-credits | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:emit-advisory | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:external-gate-wrapper | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:fetch-depth-safety | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:form-validation | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:gate-anti-vacuity | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:gate-header | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:gate-lanes | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:gate-paths-exist | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:gate-skip-announcer | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:generate-tag-inputs | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:go-deps-probe-failure | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:go-module-sync | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:greenlight | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:greenlight-closure-trace | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:housekeeping-phases | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:hydration-clean | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:installmethods-args | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:installmethods-container-version | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:installmethods-linuxpkg-idiom | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:installmethods-manifest | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:knip-blockers | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:label-guide-comment | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:label-inventory | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:label-references | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:layout-overflow | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:mark-production | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-args | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-bridge | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-cuda | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-docs | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-entry | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-helpers | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-pool | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-portable | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-r2 | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-shims | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:media-venv | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:nightly-retry-filters | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:nightly-status-report | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:overrides-reasons | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:plan-housekeeping | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:policy-liveness-floors | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:policy-path | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:positional-detector | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:preview-readiness | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:preview-worker-reaping | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:profiler-coverage | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:profiler-report | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:rebase-resolve | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:regions-sync | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:release-state-consistency | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:releaseversion-attestation | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:releaseversion-build-version | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:releaseversion-cd-retry-assert | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:releaseversion-closure-untagged | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:releaseversion-inject-env | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:releaseversion-tag-fetch | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:renet-deadcode | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:resprofile | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:review-labels | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:review-status | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:run-all-parallel | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:run-sh | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:runner-advice | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:schema-coverage | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:scope-baseline-attest | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:scope-engine | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:scope-gate-outputs | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:scrub-sentinel-empty | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:shadow-gate | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:shell-counter-increment | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:shrink-only-composition | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:simulate-promotion-serverside | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:skip-plan-reconcile | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:skip-release-channel-pointer | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:slim-timeout | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:stage-artifacts-channel | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:stop-hook-stdin | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:suppression-liveness | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:swallowed-failures | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:toolchain | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:trap-registry | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:tutorial-render-queue | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:untagged-commit-branch | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:unverified-downloads | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:vacuity-floors | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:verify-version | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-binary-exec-guard | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-classifier-chain | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-designed-failure | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-log-capture | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:watchdog-monitor-ordering | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-no-retry-cancel | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-observer-exclusion | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-retry-allowlist | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-schedule-exemption | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:watchdog-supersession | quality-security / Quality-gate unit tests | yes | no | yes |
| gate-test:workflow-contracts | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:workflow-env-shell-vars | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:workflow-inline | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:workflow-pr-environment | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:worklist-hooks | quality-security / Quality-gate unit tests | yes | yes | yes |
| gate-test:worktree-devbox-teardown | quality-security / Quality-gate unit tests | yes | no | yes |
| gen:docs | local-only | no | no | no |
| gen:gates-lock | local-only | no | no | no |
| lint:unused | quality-code / Unused exports (knip) | yes | yes | no |
| test:install-script | quality-static / Install-script tests | yes | no | no |
| test:write-once-guard | quality-static / Write-once guard tests | yes | no | no |

445 row(s). Generated by `npx tsx scripts/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## Hook guards

<!-- >>> gen-docs: hook-guards -->
<!-- Chains come from the `hooks` wiring in .claude/settings.json, not from a hand-kept chain -->
<!-- list: check-hook-integrity.sh's own comment records post-bash missing from its array -->
<!-- until 2026-08-28, which left two registered guards outside every inventory. A guard in a -->
<!-- wired directory that no event names is listed here with Reached = (nothing), which is the -->
<!-- interesting residue: a file beside the live guards that nothing can reach. -->

Scans: the `hooks` wiring in .claude/settings.json, closed transitively over the tracked files under .claude/hooks/.

| Hook file | Events | Reached | Language |
|---|---|---|---|
| context/band-notice.py | PostToolUse | settings.json | py |
| context/ctx_budget.py | (none) | via context/band-notice.py | py |
| context/epoch-reset.py | PostCompact | settings.json | py |
| context/onboard.py | PostCompact, PostToolUse, SessionStart | settings.json | py |
| context/precompact-floor.py | PreCompact | settings.json | py |
| context/test-context-bands.py | (none) | via test-hooks.sh | py |
| lib/sanctioned.py | (none) | via pre-bash/block-adhoc-sanctioned.sh | py |
| post-bash/cancel-old-ci.sh | PostToolUse | settings.json | sh |
| post-bash/refresh-pr-body.sh | PostToolUse | settings.json | sh |
| pre-ask/block-settled-questions.sh | PreToolUse | settings.json | sh |
| pre-bash/block-adhoc-sanctioned.sh | PreToolUse | settings.json | sh |
| pre-bash/block-admin-merge.sh | PreToolUse | settings.json | sh |
| pre-bash/block-agent-browser-repo-output.sh | PreToolUse | settings.json | sh |
| pre-bash/block-bash-write-to-running-script.sh | PreToolUse | settings.json | sh |
| pre-bash/block-binary-deploy.sh | PreToolUse | settings.json | sh |
| pre-bash/block-blanket-git-add.sh | PreToolUse | settings.json | sh |
| pre-bash/block-ci-polling.sh | PreToolUse | settings.json | sh |
| pre-bash/block-ci-reverse-poll.sh | PreToolUse | settings.json | sh |
| pre-bash/block-cli-bundle.sh | PreToolUse | settings.json | sh |
| pre-bash/block-commit-meta.sh | PreToolUse | settings.json | sh |
| pre-bash/block-destructive-git-restore.sh | PreToolUse | settings.json | sh |
| pre-bash/block-git-amend.sh | PreToolUse | settings.json | sh |
| pre-bash/block-git-empty-commit.sh | PreToolUse | settings.json | sh |
| pre-bash/block-git-force-push.sh | PreToolUse | settings.json | sh |
| pre-bash/block-host-toolchain-run.sh | PreToolUse | settings.json | sh |
| pre-bash/block-long-sleep.sh | PreToolUse | settings.json | sh |
| pre-bash/block-merge-with-unpushed.sh | PreToolUse | settings.json | sh |
| pre-bash/block-nondraft-pr-create.sh | PreToolUse | settings.json | sh |
| pre-bash/block-nonstandard-branch-name.sh | PreToolUse | settings.json | sh |
| pre-bash/block-premature-ready.sh | PreToolUse | settings.json | sh |
| pre-bash/block-protected-files.sh | PreToolUse | settings.json | sh |
| pre-bash/block-raw-pr-body-edit.sh | PreToolUse | settings.json | sh |
| pre-bash/block-roundlog-truncate.sh | PreToolUse | settings.json | sh |
| pre-bash/block-second-open-pr.sh | PreToolUse | settings.json | sh |
| pre-bash/block-self-matching-pgrep.sh | PreToolUse | settings.json | sh |
| pre-bash/block-shell-background-waiter.sh | PreToolUse | settings.json | sh |
| pre-bash/block-ssh-docker.sh | PreToolUse | settings.json | sh |
| pre-bash/block-ssh-file-write.sh | PreToolUse | settings.json | sh |
| pre-bash/block-stale-pr-branch-date.sh | PreToolUse | settings.json | sh |
| pre-bash/block-unlinked-commit-author.sh | PreToolUse | settings.json | sh |
| pre-bash/block-untagged-commit.sh | PreToolUse | settings.json | sh |
| pre-bash/block-unverified-push.sh | PreToolUse | settings.json | sh |
| pre-bash/block-worktree-add.sh | PreToolUse | settings.json | sh |
| pre-bash/lib/command-scan.sh | (none) | via pre-bash/block-adhoc-sanctioned.sh | sh |
| pre-bash/test-block-destructive-git-restore.py | (none) | via test-hooks.sh | py |
| pre-bash/test-block-git-amend.py | (none) | via test-hooks.sh | py |
| pre-bash/test-block-host-toolchain-run.py | (none) | via test-hooks.sh | py |
| pre-bash/test-block-unverified-push.py | (none) | via test-hooks.sh | py |
| pre-bash/warn-hook-change.sh | PreToolUse | settings.json | sh |
| pre-bash/warn-remote-drift.sh | PreToolUse | settings.json | sh |
| pre-bash/warn-stale-index.sh | PreToolUse | settings.json | sh |
| pre-bash/warn-submodule-deletions.sh | PreToolUse | settings.json | sh |
| pre-edit/block-agent-state-shape.sh | PreToolUse | settings.json | sh |
| pre-edit/block-compacted-plan-edit.sh | PreToolUse | settings.json | sh |
| pre-edit/block-edit-of-running-script.sh | PreToolUse | settings.json | sh |
| pre-edit/block-inline-python.sh | PreToolUse | settings.json | sh |
| pre-edit/block-inline-workflow-run.sh | PreToolUse | settings.json | sh |
| pre-edit/block-plan-without-tasks.sh | PreToolUse | settings.json | sh |
| pre-edit/block-roundlog-write.sh | PreToolUse | settings.json | sh |
| pre-edit/block-suppressions.sh | PreToolUse | settings.json | sh |
| profile/bash_env.sh | (none) | (nothing) | sh |
| profile/py/sitecustomize.py | (none) | via stop/wl_resprofile.py | py |
| require-jq.sh | PostToolUse, PreToolUse | settings.json | sh |
| require-python.sh | PostToolUse, PreToolUse | settings.json | sh |
| stop/calibrate-judge-rules.py | (none) | (nothing) | py |
| stop/test-adhoc-watch.py | (none) | via test-hooks.sh | py |
| stop/test-always-tier.py | (none) | via stop/wl_checks.py | py |
| stop/test-completion-evidence.py | (none) | via test-hooks.sh | py |
| stop/test-judge-schema.py | (none) | via stop/wl_shapedup.py | py |
| stop/test-plan-status-parse.py | (none) | via pre-edit/block-plan-without-tasks.sh | py |
| stop/test-planfile.py | (none) | via stop/wl_planfile.py | py |
| stop/test-planindex.py | (none) | via stop/wl_planindex.py | py |
| stop/test-planrec.py | (none) | via stop/test-planindex.py | py |
| stop/test-reggate-ledger.py | (none) | via test-hooks.sh | py |
| stop/test-report-inbox.sh | (none) | via stop/wl_wait.py | sh |
| stop/test-teammate-idle.py | (none) | via stop/worklist-cases/18-identity.sh | py |
| stop/test-worklist-v5.sh | (none) | via pre-bash/block-bash-write-to-running-script.sh | sh |
| stop/wl_admit.py | (none) | via stop/wl_checks.py | py |
| stop/wl_agents.py | (none) | via pre-ask/block-settled-questions.sh | py |
| stop/wl_bravedefault.py | (none) | via stop/test-judge-schema.py | py |
| stop/wl_checklist.py | (none) | via stop/worklist.py | py |
| stop/wl_checks.py | (none) | via pre-edit/block-compacted-plan-edit.sh | py |
| stop/wl_ci.py | (none) | via stop/wl_checks.py | py |
| stop/wl_classsweep.py | (none) | via stop/test-judge-schema.py | py |
| stop/wl_core.py | (none) | via post-bash/cancel-old-ci.sh | py |
| stop/wl_epic.py | (none) | via stop/worklist.py | py |
| stop/wl_git.py | (none) | via pre-bash/block-unverified-push.sh | py |
| stop/wl_histfirst.py | (none) | via stop/wl_checks.py | py |
| stop/wl_judge.py | (none) | via stop/wl_agents.py | py |
| stop/wl_lineage.py | (none) | via stop/wl_core.py | py |
| stop/wl_liveness.py | (none) | via stop/wl_checks.py | py |
| stop/wl_planfid.py | (none) | via pre-edit/block-plan-without-tasks.sh | py |
| stop/wl_planfile.py | (none) | via stop/wl_checks.py | py |
| stop/wl_planindex.py | (none) | via stop/wl_checks.py | py |
| stop/wl_planrec.py | (none) | via pre-edit/block-compacted-plan-edit.sh | py |
| stop/wl_profile.py | (none) | via stop/wl_checks.py | py |
| stop/wl_reggate.py | (none) | via stop/wl_checks.py | py |
| stop/wl_report.py | PostCompact, SessionStart, SubagentStop | settings.json | py |
| stop/wl_requests.py | (none) | via stop/wl_checks.py | py |
| stop/wl_resprofile.py | (none) | via stop/wl_checks.py | py |
| stop/wl_ressample.py | (none) | via stop/wl_profile.py | py |
| stop/wl_roundlog.py | (none) | via stop/wl_checks.py | py |
| stop/wl_rules.py | (none) | via stop/test-judge-schema.py | py |
| stop/wl_shapedup.py | (none) | via stop/wl_checks.py | py |
| stop/wl_store.py | (none) | via context/ctx_budget.py | py |
| stop/wl_wait.py | PostToolUse | settings.json | py |
| stop/worklist-cases/01-core-blocking.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/02-state-document.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/03-drift-loops-freshness.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/04-stuck-and-blockers.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/05-requests.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/06-regression-gate.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/07-idle-and-evidence.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/08-poll-and-waiting.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/09-ci-status.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/10-event-store.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/11-guide-and-deferrals.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/12-agent-docs-and-focus.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/13-ci-queue-and-mail.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/14-background-waits.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/15-waiter-controls.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/16-triage-and-plans.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/17-report-queue.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/18-identity.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/19-checklists.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/20-advisories-rotation.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/21-cadence.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/22-plan-fidelity.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/23-priority-ladder.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/24-lineage.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/25-first-touch.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/26-migrate.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist-cases/_harness.sh | (none) | via stop/test-worklist-v5.sh | sh |
| stop/worklist.py | PostCompact, SessionStart, Stop, TeammateIdle | settings.json | py |
| stop/worklist_messages.py | (none) | via pre-bash/warn-stale-index.sh | py |
| test-hooks.sh | (none) | via pre-ask/block-settled-questions.sh | sh |
| trapguard/dispatch.py | PostToolUse | settings.json | py |
| why-on-edit.py | PreToolUse | settings.json | py |

138 row(s). Generated by `npx tsx scripts/gen-docs.ts --write`; do not hand-edit.

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
| .audit-allowlist | 1 | prose only (no live entry) |
| .audit-prod-allowlist | 6 | # comment |
| .ci-parity-exempt | 10 | # comment |
| .ci/breakpoint/.breakpoint-drift-accept | 1 | prose only (no live entry) |
| .ci/config/bws-unrequested.json | 3 | JSON value |
| .ci/config/directive-quotes-allowlist.txt | 2 | prose only (no live entry) |
| .ci/config/docker-npm-pin-exclusions.json | 3 | JSON value |
| .ci/config/syncpack-source-exclusions.json | 8 | JSON value |
| .cli-i18n-orphan-allowlist | 6 | inline |
| .dead-bash-allowlist | 15 | # comment |
| .deps-upgrade-blocklist | 11 | inline |
| .devcontainer-upgrade-blocklist | 1 | prose only (no live entry) |
| .e2e-coverage-allowlist | 3 | # comment |
| .embed-assets-upgrade-blocklist | 1 | prose only (no live entry) |
| .go-deps-upgrade-blocklist | 3 | # comment |
| .plan-housekeeping-allowlist | 1 | prose only (no live entry) |
| .profiler-coverage-allowlist | 4 | # comment |
| .runner-advice-allowlist | 1 | prose only (no live entry) |
| .syncpackrc-reasons.json | 8 | JSON value |
| .unverified-download-allowlist | 4 | # comment |
| knip.jsonc | 26 | // comment |
| package.json | 28 | JSON value |
| scripts/ci-runner/gates.lock.json | 17 | JSON value |
| scripts/data/shape-duplication-seed.json | 16 | JSON value |

24 row(s). Generated by `npx tsx scripts/gen-docs.ts --write`; do not hand-edit.

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
| .ci/config | 21 | .json 15, .txt 3, .conf 1, .sh 1, .yaml 1 |
| .ci/docker | 3 | .sh 3 |
| .ci/docker/ci | 1 | .yml 1 |
| .ci/docker/render | 1 | (none) 1 |
| .ci/docker/service | 2 | .sh 1, .yml 1 |
| .ci/docker/web | 4 | .conf 2, (none) 1, .sh 1 |
| .ci/docs | 2 | .md 2 |
| .ci/keys | 1 | .asc 1 |
| .ci/legacy | 1 | .sh 1 |
| .ci/lib | 7 | .sh 7 |
| .ci/media | 11 | .sh 11 |
| .ci/media/tools | 2 | .sh 2 |
| .ci/media/tts | 2 | (none) 1, .toml 1 |
| .ci/policy | 1 | .md 1 |
| .ci/prompts | 1 | .md 1 |
| .ci/rediacc_ci | 8 | .py 8 |
| .ci/rediacc_ci/core | 10 | .py 10 |
| .ci/rediacc_ci/quality | 15 | .py 15 |
| .ci/rediacc_ci/tests | 25 | .py 25 |
| .ci/rediacc_ci/tests/data | 2 | .json 1, .yml 1 |
| .ci/rediacc_ci/tests/goldens/allowlist/bash-pairs | 17 | .golden 17 |
| .ci/rediacc_ci/tests/goldens/allowlist/corpus | 17 | .list 17 |
| .ci/rediacc_ci/tests/goldens/allowlist/reasons | 2 | .golden 2 |
| .ci/rediacc_ci/tests/goldens/allowlist/ts-records | 17 | .golden 17 |
| .ci/scripts/autopilot | 19 | .sh 16, .cjs 2, .json 1 |
| .ci/scripts/autopilot/prompts | 2 | .md 2 |
| .ci/scripts/build | 17 | .sh 17 |
| .ci/scripts/build/sea-inject | 7 | .mjs 7 |
| .ci/scripts/ci | 25 | .sh 15, .cjs 9, .py 1 |
| .ci/scripts/ci/profiler | 3 | .sh 2, .awk 1 |
| .ci/scripts/deploy | 27 | .sh 27 |
| .ci/scripts/docker | 3 | .sh 3 |
| .ci/scripts/docs | 2 | .mjs 2 |
| .ci/scripts/env | 1 | .sh 1 |
| .ci/scripts/housekeeping | 7 | .sh 6, .py 1 |
| .ci/scripts/infra | 11 | .sh 11 |
| .ci/scripts/lib | 8 | .sh 8 |
| .ci/scripts/pr | 1 | .sh 1 |
| .ci/scripts/private | 9 | .sh 9 |
| .ci/scripts/private/license-mint | 3 | .go 1, .mod 1, .sum 1 |
| .ci/scripts/quality | 133 | .sh 82, .py 48, .json 2, .mjs 1 |
| .ci/scripts/quality/lib | 1 | .py 1 |
| .ci/scripts/release | 21 | .sh 21 |
| .ci/scripts/review | 4 | .sh 4 |
| .ci/scripts/review/prompts | 2 | .md 2 |
| .ci/scripts/security | 9 | .sh 9 |
| .ci/scripts/setup | 3 | .sh 3 |
| .ci/scripts/signal | 1 | .sh 1 |
| .ci/scripts/test | 18 | .sh 17, .ts 1 |
| .ci/scripts/test/fixtures/mutate-check | 2 | .py 1, .sh 1 |
| .ci/scripts/test/gates | 148 | .sh 148 |
| .ci/scripts/test/lib | 3 | .sh 3 |
| .ci/scripts/test/manual | 1 | .sh 1 |
| .ci/scripts/version | 4 | .sh 4 |
| .ci/shadow | 14 | .jsonl 14 |
| .ci/tutorials | 21 | .sh 20, .md 1 |
| .ci/tutorials/apps/demo-pgadmin | 2 | (none) 1, .yml 1 |
| .ci/tutorials/apps/heartbeat | 2 | (none) 1, .yaml 1 |
| .ci/tutorials/apps/heartbeat/app | 2 | .json 1, .mjs 1 |
| .ci/tutorials/apps/secrets-demo | 2 | (none) 1, .yml 1 |
| .ci/tutorials/lib | 4 | .sh 4 |

67 row(s). Generated by `npx tsx scripts/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->
