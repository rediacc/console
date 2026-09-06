# Breakpoint's secret shape

Status: DESIGN, not implemented — 2026-09-06
Owner decision required. Raised by session d1589e0b under operator ruling
"Build the step-scoped fetch shape now" (/ask, 2026-09-05).

## The problem, precisely

`.github/workflows/breakpoint.yml` has three reads that resolve to the EMPTY
STRING since the org secrets were deleted on 2026-09-05:

| line | read | used for |
|------|------|----------|
| 238 | `secrets.APP_PRIVATE_KEY` | mints an app token, to check out the on-prem stack |
| 317 | `secrets.AWS_SES_ACCESS_KEY_ID_EU` | emails the access details |
| 318 | `secrets.AWS_SES_SECRET_ACCESS_KEY_EU` | same |

They are the last 3 of what were 147 org-scope reads. Every other consumer now
fetches from Bitwarden. This job deliberately does not, and the file says why:
its later steps include `Start debug shell`, so anything the job holds is
readable by the human who sits down at it.

## Why "step-scoped" does not solve it

The obvious fix — fetch into one step's own `env:` rather than through
`GITHUB_ENV` — does not achieve the isolation its name implies:

- `GITHUB_ENV` and `GITHUB_OUTPUT` are FILES under the runner's `_temp`
  directory. Any step in the job can read them, including a shell.
- A composite action cannot export to its caller except through those files.
- So a value fetched anywhere in the `session` job is reachable from the shell.

The only real isolation is **not having the long-lived credential in that job at
all**. That is a different change from the one the ruling names, which is why
this is a plan and not a commit.

## The two escapes, and why neither is free

**A separate `mint` job passing a short-lived token.** The private key would live
only in a job with no shell, and `session` would receive a 1-hour installation
token instead — blast radius drops from a permanent app credential to a
revocable hour.
BLOCKER TO VERIFY FIRST: GitHub redacts masked values in job outputs, and
`actions/create-github-app-token` masks its token. If that redaction applies, the
output arrives EMPTY and this silently reproduces the exact failure mode this
whole migration exists to remove. **Verify on a scratch branch before building
anything on it.**

**Moving the SES email to its own job.** Cannot work as the workflow stands: the
email carries the tunnel URL, which exists only after `Start tunnel`, and the
`session` job then holds open for hours. Job outputs are available only after a
job completes, so a downstream job would send the mail after the session ended.

## Options for the operator

1. **Drop the 3 reads.** The debug box stops offering app-token checkout and the
   email; the run log still carries the URL. Nothing pretends to work. Cheapest,
   and honest.
2. **Mint job for the token only** (after verifying the redaction question),
   leaving the email dropped. Restores the useful half.
3. **Notify out-of-band.** Replace SES with something needing no long-lived
   credential on the box — the tunnel step posting to a webhook whose URL is
   itself the only secret, or the operator reading the run log.

## What is true today
Nothing is broken by leaving this: the three reads are empty, so the app-token
checkout and the email already do nothing. This is a capability gap, not an
outage, and `check:ci-secret-scope` freezes the 3 reads so they cannot multiply.
