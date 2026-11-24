"""Deploy one preview's own licence signer, `<name>-signer`, with a fresh delegated key pair (PLAN-preview-signer D1, D2, D14).

    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.preview_signer --db-id <uuid> [--record PATH] [--dry-run]

    environment: PREVIEW_NAME (the `pv-<w>-<w>-<w>` name), PR_NUMBER, CLOUDFLARE_API_TOKEN

THE CALLER. `rediacc_ci.deploy.deploy_www` runs `deploy()` inside the preview lane, after it has (re)created and migrated the preview D1 `account-pr-<n>` and before it deploys the preview Worker: the signer binds that database as `SHARED`, so it must exist with its final id first, and the preview Worker's `LICENSE_SIGNER` binding names `<name>-signer`, which wrangler refuses to deploy while the target Worker is missing. The module entry is for a hand run against a preview whose database already exists.

THE CONFIG. `workers/signer/wrangler.preview.template.toml` (box S2 writes it) is rendered into the gitignored `workers/signer/.generated/wrangler.<name>-signer.toml`. Its tokens are `@WORKER@` (`<name>-signer`), `@PREVIEW_NAME@`, `@REGION@`, `@PREVIEW_HOST@`, `@SHARED_DB@`, `@SHARED_DB_ID@` and `@CENTRAL_SIGNER@` (`signer-bench-eu`). A token left over, a route, a workers.dev host or a preview URL, a name other than `<name>-signer`, a D1 binding other than the one `SHARED` on the preview's own database, a `CENTRAL_SIGNER` binding that is not `signer-bench-eu`'s `LicenseSigner` with `{tier = "preview", name, host, region}` props for this preview, or any key name (the production `ACCOUNT_ED25519_PRIVATE_KEY` or the delegated one) in the rendered text refuses the run before anything is deployed.

THE KEY. A fresh Ed25519 pair per deploy (PKCS#8 and SPKI DER, base64, the account's own key format, from `rediacc_ci.core.account.keypair`). Both halves reach wrangler only as the JSON document on the stdin of `wrangler secret bulk`; no value is put in argv, printed, written to the record or carried by an exception, and every line of wrangler output is redacted of both before it is printed. The verification is `wrangler secret list`, which must name exactly `DELEGATED_PRIVATE_KEY` and `DELEGATED_PUBLIC_KEY`, with the same re-push on a list that only lags as `deploy_signer` has. The central signer issues the delegation cert for the public half on demand (box S2); nothing here asks for one.

FORK SAFETY (D14). Under GitHub Actions, `GITHUB_EVENT_PATH` names the event; a pull request whose head repository is not the base repository is refused before any call, and an event file that cannot be read is refused too, never read as "not a fork". Outside Actions there is no event and no fork.

THE ORDER, AND THE RECORD. `wrangler deploy`, the record (worker, config, version, the previous version and the rollback line), `wrangler secret bulk`, then the verification, and the record rewritten with the secret names seen. A DRY RUN renders with the given database id and runs `wrangler deploy --dry-run`, which needs no credential; no key is generated.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import tomllib
import typing

from rediacc_ci import paths
from rediacc_ci.core import account, wrangler
from rediacc_ci.deploy import deploy_signer, preview_name
from rediacc_ci.enterprise import control_db

SELF = "rediacc_ci.deploy.preview_signer"

SIGNER_REL = deploy_signer.SIGNER_REL
TEMPLATE = "wrangler.preview.template.toml"
GENERATED_DIR = deploy_signer.GENERATED_DIR
SUFFIX = "-signer"
REGION = "eu"
CENTRAL_SIGNER = "signer-bench-eu"
CENTRAL_ENTRYPOINT = "LicenseSigner"
HOST_FMT = "%s.rediacc.workers.dev"
DB_NAME_FMT = "account-pr-%s"

PRIVATE_KEY = "DELEGATED_PRIVATE_KEY"
PUBLIC_KEY = "DELEGATED_PUBLIC_KEY"
SECRET_NAMES = (PRIVATE_KEY, PUBLIC_KEY)
# Key names a rendered config must never carry: the delegated pair arrives as secrets, and the production key never reaches a preview at all.
FORBIDDEN_NAMES = (PRIVATE_KEY, deploy_signer.PRIVATE_KEY, deploy_signer.PUBLIC_KEY)

RefusedError = deploy_signer.RefusedError
Result = deploy_signer.Result
Runner = deploy_signer.Runner
# () -> (private, public), base64 DER. The tests swap it for a fixed pair.
KeyGen = typing.Callable[[], "tuple[str, str]"]


def generate_keys() -> tuple[str, str]:
    private, public = account.keypair("ed25519", strict=True)
    if not private or not public or private == public:
        raise RefusedError("%s: the Ed25519 key generation produced no key pair" % SELF)
    return private, public


def signer_name(name: str) -> str:
    return name + SUFFIX


def check_name(name: str) -> str:
    """`name` when it is a preview's word name (`pv-<w>-<w>-<w>`, not a `-signer` name), else a refusal that does not echo it."""
    if not preview_name.is_preview_worker(name) or name.endswith(SUFFIX):
        raise RefusedError(
            "%s: PREVIEW_NAME must be a preview Worker name (pv-<word>-<word>-<word>)" % SELF
        )
    return name


def fork_refusal(environ: typing.Mapping[str, str]) -> str | None:
    """Why this run must not deploy a signer for a fork head, or None. Outside Actions (no GITHUB_EVENT_PATH) there is no fork."""
    event_path = environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        return None
    try:
        event = json.loads(pathlib.Path(event_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return (
            "the GitHub event file could not be read (%s), so a fork head cannot be ruled out"
            % (type(exc).__name__)
        )
    pr = event.get("pull_request") if isinstance(event, dict) else None
    if not isinstance(pr, dict):
        return None
    head = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    base = ((pr.get("base") or {}).get("repo") or {}).get("full_name")
    if not head or not base:
        return "the pull_request event names no head or base repository"
    if head != base:
        return "the pull request's head repository is a fork; a fork preview never gets a signer"
    return None


def render_values(name: str, pr: str, db_id: str) -> dict[str, str]:
    return {
        "WORKER": signer_name(name),
        "PREVIEW_NAME": name,
        "REGION": REGION,
        "PREVIEW_HOST": HOST_FMT % name,
        "SHARED_DB": DB_NAME_FMT % pr,
        "SHARED_DB_ID": db_id,
        "CENTRAL_SIGNER": CENTRAL_SIGNER,
    }


def config_refusals(text: str, name: str, pr: str) -> list[str]:
    """Every reason a rendered preview signer config may not deploy; empty when it may."""
    reasons: list[str] = []
    leftover = sorted(set(deploy_signer.TOKEN_RE.findall(text)))
    if leftover:
        reasons.append("unrendered token(s): %s" % ", ".join(leftover))
    reasons.extend(
        "%s is named in the config; a key is a secret only, and the production key never reaches a preview"
        % key
        for key in FORBIDDEN_NAMES
        if key in text
    )
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [*reasons, "does not parse: %s" % exc]
    worker = signer_name(name)
    if doc.get("name") != worker:
        reasons.append("name is %r, not the preview's signer" % doc.get("name"))
    reasons.extend("has `%s`: a signer has no route" % k for k in ("route", "routes") if k in doc)
    if doc.get("workers_dev") is not False:
        reasons.append("workers_dev is not false")
    if doc.get("preview_urls") is not False:
        reasons.append("preview_urls is not false")
    if "env" in doc:
        reasons.append("has an [env.*] table")
    d1 = doc.get("d1_databases", [])
    if [(d.get("binding"), d.get("database_name")) for d in d1] != [("SHARED", DB_NAME_FMT % pr)]:
        reasons.append("d1 bindings are not exactly SHARED on the preview's own database")
    host = HOST_FMT % name
    if doc.get("vars", {}).get("SHARED_HOSTS") != host:
        reasons.append("vars.SHARED_HOSTS is not the preview's one host")
    central = [s for s in doc.get("services", []) if s.get("binding") == "CENTRAL_SIGNER"]
    want_props = {"tier": "preview", "name": name, "host": host, "region": REGION}
    if (
        len(central) != 1
        or central[0].get("service") != CENTRAL_SIGNER
        or central[0].get("entrypoint") != CENTRAL_ENTRYPOINT
        or central[0].get("props") != want_props
    ):
        reasons.append(
            "CENTRAL_SIGNER is not one %s %s binding with this preview's props"
            % (CENTRAL_SIGNER, CENTRAL_ENTRYPOINT)
        )
    return reasons


def deploy(
    repo_root: pathlib.Path,
    *,
    name: str,
    pr: str,
    db_id: str,
    env: typing.Mapping[str, str],
    run: Runner,
    keygen: KeyGen = generate_keys,
    dry_run: bool = False,
    record: pathlib.Path | None = None,
    out: typing.TextIO = sys.stdout,
    sleep: typing.Callable[[float], None] = time.sleep,
) -> dict[str, typing.Any]:
    check_name(name)
    if not pr.isascii() or not pr.isdigit():
        raise RefusedError("%s: PR_NUMBER must be digits" % SELF)
    if not db_id:
        raise RefusedError("%s: the preview database id is required" % SELF)
    refusal = fork_refusal(env)
    if refusal:
        raise RefusedError("%s: %s" % (SELF, refusal))

    signer_dir = repo_root.joinpath(*SIGNER_REL)
    template = signer_dir / TEMPLATE
    if not template.is_file():
        raise RefusedError(
            "%s: %s does not exist (box S2 of PLAN-preview-signer writes it)"
            % (SELF, "/".join(SIGNER_REL) + "/" + TEMPLATE)
        )
    text = deploy_signer.render(
        template.read_text(encoding="utf-8"), render_values(name, pr, db_id)
    )
    reasons = config_refusals(text, name, pr)
    if reasons:
        raise RefusedError(
            *("%s: the preview signer config is refused: %s" % (SELF, r) for r in reasons)
        )
    worker = signer_name(name)
    config = signer_dir / GENERATED_DIR / ("wrangler.%s.toml" % worker)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    config_rel = "/".join(SIGNER_REL) + "/%s/%s" % (GENERATED_DIR, config.name)

    if dry_run:
        res = run(deploy_signer.deploy_argv(config, dry_run=True), signer_dir, None)
        _say(out, deploy_signer.Redactor([]), res.stdout + res.stderr)
        if res.rc != 0:
            raise RefusedError("%s: wrangler deploy --dry-run failed (rc %d)" % (SELF, res.rc))
        return {"worker": worker, "dry_run": True}

    if not env.get("CLOUDFLARE_API_TOKEN"):
        raise RefusedError("%s: a deploy needs CLOUDFLARE_API_TOKEN set" % SELF)
    wrangler.require(signer_dir, control_db.wrangler_env(env, repo_root))

    private_key, public_key = keygen()
    redact = deploy_signer.Redactor([private_key, public_key])

    previous_known = True
    try:
        previous = deploy_signer.newest_version(run, signer_dir, config)
    except deploy_signer.DeploymentsUnreadableError:
        previous, previous_known = None, False
    res = run(deploy_signer.deploy_argv(config, dry_run=False), signer_dir, None)
    _say(out, redact, res.stdout + res.stderr)
    if res.rc != 0:
        raise RefusedError(
            "%s: wrangler deploy of the preview signer failed (rc %d)" % (SELF, res.rc)
        )
    found = deploy_signer.VERSION_ID_RE.findall(res.stdout)
    if not found:
        raise RefusedError("%s: wrangler deploy printed no Current Version ID" % SELF)

    result: dict[str, typing.Any] = {
        "worker": worker,
        "config": config_rel,
        "version_id": found[-1],
        "previous_version_id": previous,
        "previous_known": previous_known,
        "secret_names": [],
        "rollback": deploy_signer.rollback_command(config_rel, previous) if previous else None,
    }
    _write_record(record, result)

    document = json.dumps({PRIVATE_KEY: private_key, PUBLIC_KEY: public_key})

    def push(attempt: int) -> None:
        res = run(deploy_signer.secret_bulk_argv(config), signer_dir, document)
        _say(out, redact, res.stdout + res.stderr)
        if res.rc != 0:
            raise RefusedError(
                "%s: wrangler secret bulk failed (rc %d, push %d)" % (SELF, res.rc, attempt)
            )

    def listed() -> list[str]:
        res = run(deploy_signer.secret_list_argv(config), signer_dir, None)
        if res.rc != 0:
            raise RefusedError("%s: wrangler secret list failed (rc %d)" % (SELF, res.rc))
        try:
            return sorted(str(s.get("name")) for s in json.loads(res.stdout))
        except (json.JSONDecodeError, AttributeError, TypeError):
            raise RefusedError("%s: wrangler secret list printed no JSON list" % SELF) from None

    pushes = 1
    push(pushes)
    names = listed()
    while (
        names != sorted(SECRET_NAMES)
        and set(names) <= set(SECRET_NAMES)
        and pushes < deploy_signer.SECRET_PUSHES
    ):
        sleep(deploy_signer.SECRET_SETTLE_S)
        pushes += 1
        push(pushes)
        names = listed()
    if names != sorted(SECRET_NAMES):
        raise RefusedError(
            "%s: the preview signer holds secrets %s, not exactly %s (after %d push(es))"
            % (SELF, names, sorted(SECRET_NAMES), pushes)
        )
    result["secret_names"] = names
    _write_record(record, result)
    _say(out, redact, "Deployed the preview signer with a fresh delegated key; secrets verified.")
    return result


def _say(out: typing.TextIO, redact: deploy_signer.Redactor, text: str) -> None:
    if text:
        out.write(redact(text) if text.endswith("\n") else redact(text) + "\n")


def _write_record(record: pathlib.Path | None, result: dict[str, typing.Any]) -> None:
    if record is not None:
        record.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=SELF, description=__doc__.splitlines()[0])
    parser.add_argument("--db-id", required=True, help="the preview D1's id (account-pr-<n>)")
    parser.add_argument("--record", type=pathlib.Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        deploy(
            paths.repo_root(),
            name=os.environ.get("PREVIEW_NAME", ""),
            pr=os.environ.get("PR_NUMBER", ""),
            db_id=args.db_id,
            env=os.environ,
            run=deploy_signer.run_process,
            dry_run=args.dry_run,
            record=args.record,
        )
    except RefusedError as exc:
        for line in exc.lines:
            print(line, file=sys.stderr)
        return 1
    except wrangler.WranglerNotInstalledError as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
