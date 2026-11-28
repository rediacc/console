# Edge Workers release of 1121-1, 2026-11-28 (operator answer ASKED:2026-11-28T03:20Z)

Command: `RELEASE_ASKED=ASKED:2026-11-28T03:20Z npm run release:local -- --channel edge --workers-only --branch-release --regions eu,us,asia`, rc 0, from pushed head b1a15af0-era 1121-1 (records under `release-records/v4.0.1/edge/branch-1121-1.db888ade/`, run record `release-records/v4.0.1/edge/run-20261128T071259Z-d921d960.json`). Every deploy, smoke and record step rc 0; verify-endpoints rc 0.

| Region | Worker | Before (rollback target) | After |
|---|---|---|---|
| global | www | | 1159ac52-a289-4119-8858-63bd42d0e186 |
| eu | signer | 5011830a-c5fd-4698-908d-81fd5ea3e504 | 6c7ec4b9-8697-45a2-be39-87c203a6f65d |
| us | signer | bb211a8b-a407-474e-b6ae-1976cbe2bcd5 | 7ab35d30-4584-4061-a52e-d88b1545f576 |
| asia | signer | 3c7d1806-255d-4994-82ec-5475c41122e8 | 0ae05cec-9aa1-498d-a280-6728a055c0c7 |
| eu | account | 9a8f9326-5cfb-46a6-8ccf-1a5fb0c900d9 | 67fe01bf-a85a-4379-a78a-956b049d8b35 |
| us | account | 34c7b4c8-8d47-47df-9b5f-5312bc0db00b | 02dba832-1ae9-488c-98b7-7cbc838efcbe |
| asia | account | 69a44ac3-0dc2-4a76-a0dc-74ded9d96f78 | 652d4cdf-8471-4544-9a7c-8823d5bfff52 |
| eu | proxy | 0fb278e9-39ab-4a03-a77d-87f597bf6e3e | 157e57df-9acc-4080-a241-99ccef341d37 |
| us | proxy | 08690835-138a-4e34-b2ba-2984d5634faf | 20d3f151-64cb-4d28-b35d-51d0fe75ef22 |
| asia | proxy | 3abe652a-5169-4055-9c6b-3724e35fe04c | 2f0319d2-368e-4271-b1e5-b6baa18afa31 |

D1 Time Travel bookmarks taken before the migrations:

- account-eu `00000ba1-00000012-00005131-7cc526b116433e250b3336a7fedcf1a7`
- account-us `00000243-00000000-00005131-6e31737be96baa8b573f754f0e5304e9`
- account-asia `00000252-00000000-00005131-29443559e59e311d544489c8e0c77d60`

Rollback (operator-run; the guard refuses `wrangler rollback` from agent Bash): `cd workers/<account|proxy> && npx --no-install wrangler rollback <before id> --config wrangler.<region>.toml`; signer `--config workers/signer/.generated/wrangler.<region>.toml`; D1 `cd workers/account && npx --no-install wrangler d1 time-travel restore account-<region> --bookmark=<bookmark> --config wrangler.<region>.toml`. Console executor enabled per region after the proxy smoke (executor-enable-* rc 0); its rollback is `wrangler secret delete EXECUTOR_MODE` on the account Worker.
