## SESSION 74de73ca 2026-09-04T00:48:35Z

# Session 74de73ca -- state

Branch `0903-1`, PR #585, epic `24c98380`. Head 8d17dc201, pushed, tree clean.
CI is mid-flight on it.

## What landed tonight

- **Secret cutover, wave 1.** 79 consumer reads flipped from
  `secrets.{APP_PRIVATE_KEY,CLOUDFLARE_API_TOKEN,DOCKERHUB_TOKEN}` to
  `env.BWS_*` across 16 workflow files (c770b8ebc). VERIFIED IN CI, which is the
  claim that mattered: in run 33815742382 the fetch step succeeded and
  `./.github/actions/app-token` minted a token from the Bitwarden value. The 73
  `GH_<NAME>:` comparator halves were deliberately NOT flipped -- flipping them
  makes the shadow compare a value against itself.
- **breakpoint.yml lost its shadow** rather than gaining a flip (cc3b468ed):
  bws-secrets exports through GITHUB_ENV and that job's later steps hand a human
  a shell, so the fetch was promoting four credentials into it.
- **CHECK 6 of check-workflow-gates.sh** now states a property (`continue-on-error`
  AND a small `timeout-minutes`, both literals) instead of a name allowlist, and
  has its first test ever -- nine assertions, checker extracted from the live gate.
- **Two Docker builds fixed and their class swept.** private/account's image
  stopped building on an npm 10 arborist crash from a package published that
  morning; fixed in the submodule (b0924d1). `check:ci-docker-npm-pins` (502dabe48)
  is the regression test for the class, and it caught two more unpinned installs.
- **The run that went red wearing "cancelled"** (f6a43e635): `Quality / Code` hit
  its own 15-minute ceiling because `lint:unused` runs four npm installs first and
  they took 671s against 21-29s on the five runs before. Bounded and retried.
- **Resprofile wave 2 complete**; `rank()` reads bash.jsonl at last, and the
  retirement trigger stopped counting prose about the layer as work.
- **The retirement tool** (873cce233) writes out the last, irreversible step and
  applies nothing.

## Next action

Re-derive the shadow pass list from the CI run now finishing and check it against
`retire-shadowed-secrets.py`'s report: the tool names 16 files, 73 comparator
halves, 4 whole comparator steps and 23 passthroughs, and that inventory should
agree with which names the comparators actually proved equal on this run. A
disagreement means one of the two is reading the tree wrong, and the tool is the
thing an operator would run against production secrets.

## Remaining

- `[?] #13d281a2` -- retire the three org secrets, or hold. DEFAULT is HOLD; it
  parks no work, everything mechanical is committed.
- `[?] #3838ee4f` -- docker SDK v25 -> v28 in renet. DEFAULT is to land it as the
  first change after #585 merges, so the E2E matrix judges it alone.
