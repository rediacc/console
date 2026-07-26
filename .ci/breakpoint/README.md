# breakpoint

An on-demand debug box: a CI runner held open for a chosen duration, reachable
over a Cloudflare tunnel, optionally with an SSH shell and a browser desktop.

You dispatch it from the Actions tab when something only reproduces in CI.

This folder is **self-contained and copyable**. It has zero dependencies on the
repository around it, and a drift gate proves a vendored copy has not diverged
from the canonical one.

---

## Quick start

Actions → **Breakpoint** → Run workflow. The defaults (quick tunnel,
`ubuntu-latest`, 30 minutes, `core` services) need no configuration at all.

Where the URL lands is decided by whether email is available, and this is a
security decision, not a preference. See [Access delivery](#access-delivery).

---

## The two tunnel modes

|                        | `quick` (default)                     | `named`                                    |
| ---------------------- | ------------------------------------- | ------------------------------------------ |
| Hostname               | random `*.trycloudflare.com`          | `<label>-<run-id>.<zone>`                   |
| Credentials needed     | none                                  | a Cloudflare API token                      |
| Authentication         | **none** — the URL *is* the secret    | Cloudflare Access                           |
| Account-side objects   | **none**                              | tunnel + DNS record + Access app            |
| Teardown surface       | **nothing to clean up**               | three objects, and a sweeper as backstop    |
| Limits                 | 200 concurrent requests, **no SSE**   | ordinary Cloudflare limits                  |

Quick mode creating **zero** account-side objects is not a footnote: it is why
the per-CI-round lifecycle test can run inside a watchdog-monitored run safely.
The watchdog force-cancels, force-cancel bypasses `if: always()`, and quick mode
has nothing to leak.

`named` mode ships **with** Cloudflare Access, in the same script and the same
call sequence as the DNS record. There is deliberately no ordering in which the
hostname resolves while unprotected. The hostname is derived from a run id that
is public on a public repo, so obscurity was never the control.

**Named mode never silently falls back to quick.** Falling back would drop
authentication at the moment nobody is watching. `--allow-fallback` opts in, and
even then it refuses when a shell or desktop is enabled.

---

## One hostname, several services

A quick tunnel gives you exactly **one** hostname. Without path multiplexing you
would have to choose between tunnelling the application and tunnelling the
desktop. So when a session needs more than a bare tunnel, the origin is a
**Caddy gateway** (`docker/Caddyfile`) rather than a static server:

| Path | Goes to | What it is |
| --- | --- | --- |
| `/health` | Caddy itself | liveness, deliberately independent of whether the app is up |
| `/desktop` | redirect | bounces to an already-connected noVNC session |
| `/desktop/*` | `:6080` | noVNC static assets (prefix stripped) |
| `/vnc` | `:6080` | the VNC WebSocket pixel stream |
| `/*` | `:80` | **the application** |

That last row is the point: it is what makes this a gateway rather than a noVNC
front end. Adding `/code` or `/term` later is a three-line Caddyfile edit — the
hub product already routes code-server, ttyd and noVNC over one hostname the
same way.

The kind is **inferred**, not asked for:

| Session | Origin kind | Needs Docker? |
| --- | --- | --- |
| desktop or services enabled | `gateway` | yes (session job is `ubuntu-latest`) |
| bare tunnel | `static` (`python3 -m http.server`) | no |

`--kind static|gateway` forces one. The per-CI-round lifecycle leg runs
`--desktop none --services none`, so it infers `static` and stays runnable on
`ubuntu-slim` with no Docker at all. If a gateway is requested where Docker is
absent, it degrades to static and says loudly that `/desktop` will not be
reachable.

Two details worth knowing. `--network host` is load-bearing: the desktop stack
runs **directly on the runner**, not in a container, so `localhost:6080` only
resolves for a container sharing the host's network namespace. And the Caddy
image is pinned **by digest** in `versions.sh`, not by the `caddy:alpine` tag the
old overlay used — a tag is a moving target, a digest is the bytes you reviewed.

## Access delivery

On a public repository the quick-mode URL is a **bearer credential**: anyone
reading the Actions log can reach a runner holding your source, the app token,
and possibly a shell. So:

| Condition                                              | Channel   | URL masked?                 |
| ------------------------------------------------------ | --------- | --------------------------- |
| SES configured **and** the actor resolves to an email   | **email** | yes, and not printed        |
| no SES, or unmapped actor, or `send-email: false`       | **logs**  | **no** — printed, with a warning |
| named mode                                              | either    | never — Access is the control |

**The rule: never mask without a working alternative channel.** The old
implementation masked unconditionally and, when SES was absent, told you the
details were "available via masked step outputs" — which is unreadable by
construction. You got nothing.

The `AWS_SES_*` secrets are org-level with `visibility: selected`. If your repo
is not on that list, you get the logs channel, and that is a working
configuration. To switch to email, add the repo to the secret's selected list.

---

## Adopting this in another repository

```bash
mkdir -p <repo>/.ci
cp -r console/.ci/breakpoint <repo>/.ci/breakpoint
cp console/.ci/breakpoint/workflow/breakpoint.yml <repo>/.github/workflows/breakpoint.yml
$EDITOR <repo>/.ci/breakpoint/breakpoint.conf      # the ONLY file you should edit
<repo>/.ci/breakpoint/scripts/check-breakpoint-drift.sh   # must print "Verified N files"
```

No `.ci/scripts/`, no `package.json`, no composite action, no network. The
folder works when `.ci/breakpoint/` is the only thing in `.ci/`, and
`test-breakpoint-portability.sh` proves it by executing the gate inside an
otherwise-empty tree.

**`breakpoint.conf` is the only file you should edit.** If you find yourself
needing to change a script, that is a signal the value belongs in conf — raise
it upstream rather than forking your copy.

### Keeping a copy honest

```bash
scripts/check-breakpoint-drift.sh                  # offline: has THIS copy been edited?
scripts/check-breakpoint-drift.sh --verify-upstream # has the canonical copy moved on?
scripts/sync-breakpoint.sh                          # re-vendor, preserving your conf
```

`--write` regenerates the manifest and **refuses to run outside the canonical
repo**. That refusal is the whole reason the gate has teeth: otherwise a
downstream operator "fixes" drift by regenerating it, and the gate becomes
decorative.

Genuinely repo-specific divergence goes in `.breakpoint-drift-accept` under a
`# BLOCKER:` line explaining what is different about *this* repo and why the
canonical copy cannot carry the change.

---

## Teardown, and why it is three layers

Two cancellation paths skip `if: always()` entirely: the CI watchdog's
`force-cancel`, and a runner crash. So in-job teardown alone is not enough.

1. **In-job `always()`** — covers timeout, manual cancel, normal completion.
2. **Deterministic naming** — every object is named `breakpoint-<label>-<run-id>`,
   a pure function of `$GITHUB_RUN_ID`. This is the durable channel: the session
   state file lives on a runner that can vanish, but the *name* lets cleanup
   attribute an orphan with zero cooperation from a dead runner.
3. **Nightly sweeper** (`reap-breakpoint-orphans.sh`) — enumerates Cloudflare's
   own object list, parses the run id back out of each name, asks GitHub whether
   that run is over, and reaps. Terminal run state is the primary signal; age is
   a backstop; an inconclusive answer is never acted on.

`stop-breakpoint.sh` exits 0 only after re-querying and confirming the objects
are gone. A red teardown is noise you investigate once; a green teardown that
leaked is a lie nobody investigates at all.

It kills **only PIDs it recorded**. Never `pkill -f`: on a shared machine a
pattern kill reaches a concurrent job's processes.

---

## Runner choice

Default `ubuntu-latest` (linux amd64). The dropdown also lists paid larger
runners for future use.

**A larger-runner label on an org without them QUEUES INDEFINITELY rather than
failing** — `timeout-minutes` starts when the job starts, so it does not bound
queue time. The preflight job warns about this. It deliberately touches no
Cloudflare API, so a permanently queued session leaks nothing.

`ubuntu-slim` is excluded: its hard 15-minute cap makes a debug session
impossible.

---

## Files

| Path                       | Purpose                                                    |
| -------------------------- | ---------------------------------------------------------- |
| `breakpoint.conf`          | the per-repo edit point; excluded from the manifest         |
| `versions.sh`              | pinned cloudflared/tmate versions + sha256 per architecture |
| `lib/breakpoint-common.sh` | vendored logging, `parse_args`, state and PID helpers       |
| `lib/breakpoint-blocker.sh`| BLOCKER validation for the drift accept-list                |
| `scripts/`                 | one script per step; see each file's header for the why     |
| `workflow/breakpoint.yml`  | copied to `.github/workflows/`; identical in every repo     |
| `MANIFEST.sha256`          | the drift oracle                                            |

The desktop stack is deliberately duplicated with
`.devcontainer/start-desktop.sh`. That file is a **shipped product interface**
(the hub feature invokes it by name as a container command and as CRIU
checkpoint hooks, documented across 13 locales), and hub users run that image
without this repository mounted, so it cannot become a shim. Prefer fixing the
devcontainer copy first: it is the one customers run.
