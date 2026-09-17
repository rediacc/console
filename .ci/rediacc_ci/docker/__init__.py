"""Python ports of `.ci/scripts/docker/*.sh`, box W7P6.

Sibling of `rediacc_ci.deploy` and `rediacc_ci.release`; see the `deploy`
package's docstring for why a subpackage exists at all, why nothing here carries
a `---- gate ----` header, and why the call-site cutover is a separate, later box. `docker/` held exactly 3 bash scripts and zero Python before this box, and this one ports all three.

NONE OF THE THREE IS A GATE, and two of them are workflow `run:` targets. The call sites are listed rather than summarised, because a cutover box needs the list and because an earlier draft of this docstring claimed all three were called only from other scripts, which the grep disproved:

  * `create-manifest.sh`: `.github/workflows/ci-build-docker.yml:436`, `:509`
    and `:604` (the renet, rdc and web image jobs).
  * `retag-image.sh`: `.github/workflows/cd-v2.yml:301-305` (with
    `--push-latest --skip-if-exists`) and `.github/workflows/cd-stage.yml:242-247`.
    Both drive `--image` twice and `--image-path ghcr.io/rediacc/server` once,
    which is the slash-decides-the-mode path the differential covers on purpose.
  * `cleanup-staging.sh`: no workflow reaches it. It is forwarded to by
    `.ci/scripts/release/cleanup-channel-docker-tags.sh` and by that script's
    own port, `rediacc_ci.release.cleanup_channel_docker_tags`.

So no `scripts/ci-runner/manifest.ts` entry follows from a module living here (these are `run:` targets and plumbing, never gates), and every one of those call sites still names the BASH twin. Flipping them is the cutover box, not this one.

WHAT "VERIFIED EQUIVALENT" MEANS HERE, and it is narrower than for the quality gates. Every one of these three talks to a REGISTRY. The differential drives both sides against recording fakes for `docker` and `gh` on a scratch PATH and compares stdout, stderr, the exit code and the exact argv of every external call; the shadow-gate ledger under `.ci/shadow/w7p6-*.observations.jsonl`
scopes its `--finding-re` to those recorded calls, so the compared finding set IS the set of registry operations each side would have performed. Nothing in this
package has ever been run against a real registry from a test, and nothing here
should be.

Deliberately no re-exports, same reasoning as `rediacc_ci/__init__.py`: a consumer should import exactly the module it needs.
"""

__all__: list[str] = []
