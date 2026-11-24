"""Every command in the committed CLI contract carries the semantics the web console and the executor read.

WHAT IT CHECKS (PLAN-console-contract-semantics.md D8). The committed `packages/shared/src/cli-contract/data/contract.json` and its locale bundles under `i18n/`, never the generator. For every command:

  * a `severity` of `none`, `caution` or `destructive`;
  * a non-empty `summaryKey`, and a `summary` of 1 to 100 characters;
  * the `summaryKey` present and non-empty in every bundle the contract's `languages` names;
  * a `preview`, when present, whose `flag` is the long name of one of the command's own options and whose `polarity` is `opt-in` or `default`.

And for the contract as a whole: a non-empty `errorCodes` list in which every row has a code, an `origin` of `user`, `environment` or `rediacc`, and no code appears twice.

WHY THE ARTIFACT AND NOT THE SOURCE. The CLI-side tests (command-safety.test.ts, error-origins.test.ts, agent-refused-options.test.ts) are the type-level half: they prove the tables the generator reads are complete. This gate proves the file the web bundle and the executor actually load says the same thing. check:ci-cli-contract proves the committed file equals what the generator emits today; neither of the two implies the other, because a generator that dropped a field would regenerate a contract that is fresh and empty in the same commit.

THE 100-CHARACTER LIMIT BINDS THE ENGLISH SOURCE. Translated summaries are judged present and non-empty, not measured, because a naturalized translation runs longer than its English by design (docs/i18n/CONVENTIONS.md). The count of translations over 100 characters is PRINTED on every run, so the number is visible and a reader can tell when it grows.

EXIT CODES. 0 every command covered, 1 a finding, 2 a failed control or an unknown argument, 77 the gate CANNOT RUN: the contract is missing, unparseable, or names no command or no language. 77 is never a verdict: a contract with zero commands would otherwise pass every per-command rule vacuously, and that green would mean nothing.

CONTROLS FIRST. `main` runs the selftest before the verdict (`controls.controls_first`), so the real-tree run proves on every invocation that each rule can fire before it reports that none did.

---- gate ----
step: CLI contract coverage
needs: node
selftest: true
lane: quality-packages
---- end gate ----
"""

import contextlib
import io
import json
import pathlib
import re
import shutil
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, controls_first

# Where the committed contract lives, relative to the repository root. The same constant cli_contract.py carries; duplicated rather than imported so neither gate's module is the other's dependency.
DATA_SUBDIR = "packages/shared/src/cli-contract/data"
LANGUAGES_REL = "packages/shared/src/i18n/types.ts"
_SUPPORTED_RE = re.compile(r"SUPPORTED_LANGUAGES\s*=\s*\[(.*?)\]", re.DOTALL)

SEVERITIES = ("none", "caution", "destructive")
POLARITIES = ("opt-in", "default")
ORIGINS = ("user", "environment", "rediacc")
SUMMARY_MAX = 100

# Exit codes. CANNOT_RUN is the value scripts/ci-runner/pool.ts reads as `blocked`.
FINDING = 1
BROKEN = 2
CANNOT_RUN = 77


class CannotRunError(Exception):
    """The gate has nothing to judge. Exit 77, never a verdict either way."""


def load_contract(data_dir: pathlib.Path) -> dict:
    """The parsed contract, or CannotRunError naming what is missing.

    Zero commands or zero languages is CannotRunError, not a pass: every per-command and per-bundle rule below holds vacuously over an empty list.
    """
    path = data_dir / "contract.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CannotRunError("%s does not exist" % path) from None
    except (OSError, ValueError) as exc:
        raise CannotRunError("%s cannot be read as JSON: %s" % (path, exc)) from None
    if not isinstance(contract, dict):
        raise CannotRunError("%s is not a JSON object" % path)
    commands = contract.get("commands")
    if not isinstance(commands, list) or not commands:
        raise CannotRunError("%s names no command, so every rule would hold vacuously" % path)
    languages = contract.get("languages")
    if not isinstance(languages, list) or not languages:
        raise CannotRunError("%s names no language, so no bundle would be read" % path)
    return contract


def load_bundles(data_dir: pathlib.Path, languages: list) -> tuple[dict[str, dict], list[str]]:
    """`({lang: bundle}, findings)`. A declared language with no readable bundle is a FINDING, reported once rather than once per command."""
    bundles: dict[str, dict] = {}
    findings: list[str] = []
    for lang in languages:
        path = data_dir / "i18n" / ("%s.json" % lang)
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            findings.append(
                "i18n/%s.json: the contract declares language %r and no bundle exists. "
                "Fix: npm run generate:cli-contract -w @rediacc/cli" % (lang, lang)
            )
            continue
        except (OSError, ValueError) as exc:
            findings.append("i18n/%s.json: cannot be read as JSON (%s)" % (lang, exc))
            continue
        if not isinstance(bundle, dict):
            findings.append("i18n/%s.json: not a JSON object" % lang)
            continue
        bundles[lang] = bundle
    return bundles, findings


def command_findings(command: dict, bundles: dict[str, dict]) -> list[str]:
    """Every coverage defect of one contract command, each naming the command, the field and the fix."""
    key = command.get("pathKey") or "<command with no pathKey>"
    out: list[str] = []

    severity = command.get("severity")
    if severity not in SEVERITIES:
        out.append(
            "%s: severity is %r, not one of %s. Fix: add the command to "
            "packages/cli/src/config/command-safety.ts and regenerate"
            % (key, severity, "/".join(SEVERITIES))
        )

    summary_key = command.get("summaryKey")
    if not isinstance(summary_key, str) or not summary_key.strip():
        out.append(
            "%s: no summaryKey. Fix: give the command a "
            ".summary(t('commands.<path>.descriptionShort')) call and regenerate" % key
        )
        summary_key = None

    summary = command.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        out.append(
            "%s: empty summary. Fix: write the English descriptionShort and regenerate" % key
        )
    elif len(summary) > SUMMARY_MAX:
        out.append(
            "%s: summary is %d characters, over the %d limit. Fix: shorten its "
            "descriptionShort in packages/cli/src/i18n/locales/en/cli.json"
            % (key, len(summary), SUMMARY_MAX)
        )

    if summary_key is not None:
        for lang, bundle in sorted(bundles.items()):
            text = bundle.get(summary_key)
            if not isinstance(text, str) or not text.strip():
                out.append(
                    "%s: summaryKey %s is absent or empty in i18n/%s.json. Fix: translate it in "
                    "packages/cli/src/i18n/locales/%s/cli.json and regenerate"
                    % (key, summary_key, lang, lang)
                )

    preview = command.get("preview")
    if preview is not None:
        if not isinstance(preview, dict):
            out.append("%s: preview is %r, not an object" % (key, preview))
        else:
            longs = {o.get("long") for o in command.get("options") or [] if isinstance(o, dict)}
            if preview.get("flag") not in longs:
                out.append(
                    "%s: preview flag %r names no option of the command (options: %s). Fix: correct "
                    "the preview table in packages/cli/src/config/command-safety.ts"
                    % (key, preview.get("flag"), ", ".join(sorted(str(x) for x in longs)) or "none")
                )
            if preview.get("polarity") not in POLARITIES:
                out.append(
                    "%s: preview polarity %r is not one of %s"
                    % (key, preview.get("polarity"), "/".join(POLARITIES))
                )
    return out


def error_code_findings(rows: object) -> list[str]:
    """Every defect of the contract's `errorCodes` list. An empty list is a finding: the CLI emits error codes, so none means the generator dropped them."""
    if not isinstance(rows, list) or not rows:
        return [
            (
                "errorCodes is missing or empty. Fix: the generator exports ERROR_CODE_ORIGINS and "
                "NAMED_ERROR_ORIGINS (packages/cli/src/types/error-origins.ts); regenerate"
            )
        ]
    out: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        code = row.get("code") if isinstance(row, dict) else None
        if not isinstance(code, str) or not code:
            out.append("errorCodes[%d]: no code (%r)" % (index, row))
            continue
        if code in seen:
            out.append("errorCodes: %s appears twice" % code)
        seen.add(code)
        origin = row.get("origin")
        if origin not in ORIGINS:
            out.append(
                "errorCodes: %s has origin %r, not one of %s. Fix: classify it in "
                "packages/cli/src/types/error-origins.ts and regenerate"
                % (code, origin, "/".join(ORIGINS))
            )
    return out


def supported_languages(root: pathlib.Path) -> list[str]:
    """The locale set the product ships, read from `SUPPORTED_LANGUAGES` in the shared i18n types. CannotRunError when it cannot be read, because the contract's own `languages` list cannot vouch for itself."""
    path = root / LANGUAGES_REL
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CannotRunError("%s cannot be read: %s" % (path, exc)) from None
    match = _SUPPORTED_RE.search(text)
    found = re.findall(r"'([a-z]{2,3})'", match.group(1)) if match else []
    if not found:
        raise CannotRunError("%s names no SUPPORTED_LANGUAGES" % path)
    return found


def evaluate(data_dir: pathlib.Path, supported: list[str] | None = None) -> tuple[list[str], dict]:
    """`(findings, shape)` for the contract under `data_dir`. `supported` is the shipped locale set the contract's `languages` must equal. Raises CannotRunError when there is nothing to judge."""
    contract = load_contract(data_dir)
    bundles, findings = load_bundles(data_dir, contract["languages"])
    if supported is not None and sorted(contract["languages"]) != sorted(supported):
        missing = sorted(set(supported) - set(contract["languages"]))
        extra = sorted(set(contract["languages"]) - set(supported))
        findings.append(
            "languages: the contract declares %d, the product ships %d (missing %s, extra %s). "
            "Fix: npm run generate:cli-contract -w @rediacc/cli"
            % (len(contract["languages"]), len(supported), missing or "none", extra or "none")
        )
    severities = dict.fromkeys(SEVERITIES, 0)
    previews = 0
    long_translations = 0
    for command in contract["commands"]:
        if not isinstance(command, dict):
            findings.append("commands: an entry is not an object (%r)" % (command,))
            continue
        findings.extend(command_findings(command, bundles))
        if command.get("severity") in severities:
            severities[command["severity"]] += 1
        if isinstance(command.get("preview"), dict):
            previews += 1
        summary_key = command.get("summaryKey")
        for lang, bundle in bundles.items():
            text = bundle.get(summary_key) if isinstance(summary_key, str) else None
            if lang != "en" and isinstance(text, str) and len(text) > SUMMARY_MAX:
                long_translations += 1
    error_codes = contract.get("errorCodes")
    findings.extend(error_code_findings(error_codes))
    shape = {
        "commands": len(contract["commands"]),
        "bundles": len(bundles),
        "languages": len(contract["languages"]),
        "previews": previews,
        "error_codes": len(error_codes) if isinstance(error_codes, list) else 0,
        "severities": severities,
        "long_translations": long_translations,
    }
    return findings, shape


def _shape_line(shape: dict) -> str:
    sev = shape["severities"]
    return (
        "%d commands (none %d, caution %d, destructive %d), %d of %d bundles, %d previews, %d error codes"
        % (
            shape["commands"],
            sev["none"],
            sev["caution"],
            sev["destructive"],
            shape["bundles"],
            shape["languages"],
            shape["previews"],
            shape["error_codes"],
        )
    )


def verdict(root: pathlib.Path) -> int:
    """Judge the contract under `root`. The exit code; prints the shape either way."""
    data_dir = root / DATA_SUBDIR
    try:
        findings, shape = evaluate(data_dir, supported_languages(root))
    except CannotRunError as exc:
        log.error("CANNOT RUN (exit 77, which is not a verdict): %s" % exc)
        log.error("the gate is not seeing the contract; its green would mean nothing")
        return CANNOT_RUN
    log.info("read: %s" % _shape_line(shape))
    log.info(
        "note: %d translated summaries exceed %d characters (the limit binds the English source)"
        % (shape["long_translations"], SUMMARY_MAX)
    )
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error("CLI contract coverage: %d finding(s) in %s" % (len(findings), DATA_SUBDIR))
        return FINDING
    log.info("CLI contract coverage OK: %s" % _shape_line(shape))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    if args == ["--selftest"]:
        return selftest()
    if args:
        log.error("unknown argument(s): %s (known: --selftest)" % " ".join(args))
        return BROKEN
    refused = controls_first("cli-contract-coverage", selftest)
    if refused:
        return refused
    return verdict(paths.repo_root())


# -----------------------------------------------------------------------------
# selftest
# -----------------------------------------------------------------------------

_LANGS = ("en", "tr")


def _fixture() -> tuple[dict, dict[str, dict]]:
    """The smallest contract that passes every rule: two commands, two locales, one preview, two error codes. Every plant is this with exactly one thing changed."""
    contract = {
        "version": "0123456789abcdef",
        "languages": list(_LANGS),
        "commands": [
            {
                "pathKey": "repo prune",
                "summaryKey": "commands.repo.prune.descriptionShort",
                "summary": "Remove orphaned repository data",
                "severity": "destructive",
                "preview": {"flag": "apply", "polarity": "default"},
                "options": [{"long": "apply"}, {"long": "offline"}],
            },
            {
                "pathKey": "repo list",
                "summaryKey": "commands.repo.list.descriptionShort",
                "summary": "List repositories",
                "severity": "none",
                "options": [],
            },
        ],
        "errorCodes": [
            {"code": "SERVER_ERROR", "origin": "rediacc"},
            {"code": "INVALID_ARGUMENT", "origin": "user"},
        ],
    }
    bundles = {
        "en": {
            "commands.repo.prune.descriptionShort": "Remove orphaned repository data",
            "commands.repo.list.descriptionShort": "List repositories",
        },
        "tr": {
            "commands.repo.prune.descriptionShort": "Sahipsiz depo verisini kaldir",
            "commands.repo.list.descriptionShort": "Depolari listele",
        },
    }
    return contract, bundles


def _write(root: pathlib.Path, contract: object, bundles: dict[str, object]) -> pathlib.Path:
    if root.exists():
        shutil.rmtree(root)
    data = root / DATA_SUBDIR
    (data / "i18n").mkdir(parents=True)
    types = root / LANGUAGES_REL
    types.parent.mkdir(parents=True)
    types.write_text(
        "export const SUPPORTED_LANGUAGES = [%s] as const;\n"
        % ", ".join("'%s'" % lang for lang in _LANGS),
        encoding="utf-8",
    )
    if contract is not None:
        text = contract if isinstance(contract, str) else json.dumps(contract)
        (data / "contract.json").write_text(text, encoding="utf-8")
    for lang, bundle in bundles.items():
        (data / "i18n" / ("%s.json" % lang)).write_text(json.dumps(bundle), encoding="utf-8")
    return root


def _quiet_verdict(root: pathlib.Path) -> int:
    """`verdict` with its log lines captured, so a real-tree run is not buried under the fixture runs' findings. A failing control still prints its own FAIL line, which goes through Controls and not through here."""
    with contextlib.redirect_stderr(io.StringIO()):
        return verdict(root)


def selftest() -> int:
    """Each rule planted red against a green control, plus the cannot-run and argv paths. Returns 0 green, 1 red."""
    ctl = Controls("cli-contract-coverage", floor=23, verbose=True)
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        def run(mutate=None, *, contract_text: str | None = None) -> int:
            contract, bundles = _fixture()
            if mutate is not None:
                mutate(contract, bundles)
            root = _write(
                base / "root", contract_text if contract_text is not None else contract, bundles
            )
            return _quiet_verdict(root)

        # CONTROL FIRST. Without a green fixture every plant below could be red for an unrelated reason.
        ctl.check("CONTROL: a fully covered contract passes", run(), 0)

        def drop(field):
            return lambda c, _b: c["commands"][1].pop(field)

        def setf(index, field, value):
            return lambda c, _b: c["commands"][index].__setitem__(field, value)

        ctl.check("PLANT: a missing severity is caught", run(drop("severity")), FINDING)
        ctl.check("PLANT: an unknown severity is caught", run(setf(1, "severity", "high")), FINDING)
        ctl.check("PLANT: a missing summaryKey is caught", run(drop("summaryKey")), FINDING)
        ctl.check("PLANT: an empty summary is caught", run(setf(1, "summary", "  ")), FINDING)
        ctl.check(
            "PLANT: a 101-character summary is caught", run(setf(1, "summary", "x" * 101)), FINDING
        )
        ctl.check(
            "MIRROR: a 100-character summary passes", run(setf(1, "summary", "x" * SUMMARY_MAX)), 0
        )
        ctl.check(
            "PLANT: a summary key absent from one bundle is caught",
            run(lambda _c, b: b["tr"].pop("commands.repo.list.descriptionShort")),
            FINDING,
        )
        ctl.check(
            "PLANT: a summary key empty in one bundle is caught",
            run(lambda _c, b: b["tr"].__setitem__("commands.repo.list.descriptionShort", "")),
            FINDING,
        )
        ctl.check(
            "PLANT: a declared language with no bundle is caught",
            run(lambda _c, b: b.pop("tr")),
            FINDING,
        )
        ctl.check(
            "MIRROR: a translation over 100 characters is not a finding",
            run(
                lambda _c, b: b["tr"].__setitem__("commands.repo.list.descriptionShort", "y" * 140)
            ),
            0,
        )
        ctl.check(
            "PLANT: a preview flag naming no option is caught",
            run(lambda c, _b: c["commands"][0]["preview"].__setitem__("flag", "dry-run")),
            FINDING,
        )
        ctl.check(
            "PLANT: an unknown preview polarity is caught",
            run(lambda c, _b: c["commands"][0]["preview"].__setitem__("polarity", "always")),
            FINDING,
        )
        ctl.check(
            "PLANT: an error code without origin is caught",
            run(lambda c, _b: c["errorCodes"][1].pop("origin")),
            FINDING,
        )
        ctl.check(
            "PLANT: an error code with an unknown origin is caught",
            run(lambda c, _b: c["errorCodes"][1].__setitem__("origin", "network")),
            FINDING,
        )
        ctl.check(
            "PLANT: a duplicated error code is caught",
            run(
                lambda c, _b: c["errorCodes"].append({"code": "SERVER_ERROR", "origin": "rediacc"})
            ),
            FINDING,
        )
        ctl.check(
            "PLANT: an empty errorCodes list is caught",
            run(lambda c, _b: c.__setitem__("errorCodes", [])),
            FINDING,
        )

        # CANNOT RUN: nothing to judge is 77, never 0 and never 1.
        ctl.check(
            "CANNOT RUN: zero commands is 77",
            run(lambda c, _b: c.__setitem__("commands", [])),
            CANNOT_RUN,
        )
        ctl.check(
            "PLANT: a contract that drops a shipped language reds (b2ffbf55.1)",
            run(lambda c, _b: c.__setitem__("languages", ["en"])),
            FINDING,
        )
        ctl.check(
            "CANNOT RUN: zero languages is 77",
            run(lambda c, _b: c.__setitem__("languages", [])),
            CANNOT_RUN,
        )
        ctl.check(
            "CANNOT RUN: unparseable contract is 77", run(contract_text="{not json"), CANNOT_RUN
        )
        ctl.check(
            "CANNOT RUN: a missing contract is 77",
            _quiet_verdict(_write(base / "root", None, {})),
            CANNOT_RUN,
        )

        # The helper's findings name the command and the field, so a red is actionable.
        contract, bundles = _fixture()
        contract["commands"][1]["summary"] = "x" * 101
        ctl.truthy(
            "MESSAGE: a finding names the command and the limit",
            any(
                "repo list" in f and "101 characters" in f
                for f in command_findings(contract["commands"][1], bundles)
            ),
        )

    with contextlib.redirect_stderr(io.StringIO()):
        refused = main(["--selftset"])
    ctl.check("ARGV: an unknown flag is refused, never ignored", refused, BROKEN)
    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
