r"""check:ci-mcp-logging-guard -- no platform log, tail consumer or URL ever carries an MCP credential.

WHY. The remote MCP Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 9, decision D14) authenticates with a bearer `rmcp_<grantId>.<S>` or an OAuth access token, and both must reach the Worker in a header, never in a URL. Cloudflare logs a URL in full (Logpush `ClientRequestURI`, OTel `url.full`), records request headers only through configured custom fields, and redacts the headers a Tail Worker sees by a name heuristic that `getUnredacted()` undoes. So the secret stays out of every log only while three things stay true, and this gate holds each one.

THE RULES.

  W1 HEADER FIELD. No wrangler file under `workers/` (any `*.toml` there, the
     templates included) carries a log custom field that captures a request
     header: a key named like a custom-field list (`custom_fields`,
     `request_headers`, ...) with a non-empty value, or a string value naming
     the Logpush header or cookie fields (`RequestHeaders`, `Cookies`, ...).
  W2 MCP PLATFORM LOGS. Each wrangler file under `workers/mcp/` keeps the
     platform from recording the request: `logpush` is not true, no
     `tail_consumers` are bound (a Tail Worker can call `getUnredacted()` on
     this Worker's events, out of reach of rule S1), and when logs are on,
     `observability.logs.invocation_logs` is set to false explicitly (the
     platform default is on).
  W3 ROUTE PATTERN. No route pattern in a wrangler file under `workers/`
     carries a query string or names a credential.
  S1 UNREDACTED. No tracked source under `workers/mcp/` names `getUnredacted`,
     tests included, comments included: the name has no harmless use there.
  S2 URL CREDENTIAL. No non-test source under `workers/mcp/` reads or writes a
     credential through a URL: a query parameter or path parameter whose name
     is a credential (`token`, `access_token`, `api_key`, `secret`, `S`, ...),
     or the agent bearer parsed out of a `pathname`. The query scan in
     `credential.ts` that REFUSES such a request iterates the parameters
     generically and never names one, so it is not a finding.

ANTI-VACUITY. Zero wrangler files under `workers/`, zero under `workers/mcp/`, or zero non-test sources under `workers/mcp/` is a REFUSAL (the instrument lost the tree), and so is a wrangler file that does not parse: an unread file is an unchecked file, never a clean one. The success line prints every count.

Exit 1 on a finding or refusal, 2 on a failed control.

---- gate ----
step: MCP credentials never reach a log or a URL
lane: quality-security
selftest: true
why: the remote MCP Worker's bearer and OAuth tokens travel only in headers, so no Worker may log a
     request header, bind a tail consumer to the MCP Worker, call getUnredacted() there, or read a
     credential from a URL (PLAN-rmcp-remote-worker.md Design 9, D14).
---- end gate ----
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, git_isolated, plant

if TYPE_CHECKING:
    from collections.abc import Mapping

WORKERS = "workers/"
MCP = "workers/mcp/"
SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".mjs", ".cjs")

# W1: a key that declares a list of logged fields, compared after lowercasing and `-` -> `_`.
HEADER_FIELD_KEYS = frozenset(
    {
        "custom_fields",
        "logpush_custom_fields",
        "http_log_custom_fields",
        "log_custom_fields",
        "request_headers",
        "request_header_fields",
        "cookie_fields",
        "cookie_names",
    }
)
# W1: Logpush field names that carry request headers or cookies.
HEADER_FIELD_VALUE_RE = re.compile(
    r"\b(?:RequestHeaders|ClientRequestHeaders?|RequestHeader|Cookies|CookieValues?)\b"
)

# The credential names S2 and W3 recognise, matched case-insensitively and whole.
CREDENTIAL_NAMES = (
    "access_token",
    "accesstoken",
    "refresh_token",
    "id_token",
    "token",
    "api_key",
    "api-key",
    "apikey",
    "key",
    "client_secret",
    "secret",
    "bearer",
    "auth",
    "authorization",
    "password",
    "s",
)
_NAMES = "|".join(re.escape(n) for n in sorted(CREDENTIAL_NAMES, key=len, reverse=True))

# S2a: `url.searchParams.get('token')`, `.query.set("access_token", ...)` and friends.
QUERY_RE = re.compile(
    r"\b(?:searchParams|query)\s*\.\s*(?:get|getAll|has|set|append)\s*\(\s*(['\"`])(?:%s)\1"
    % _NAMES,
    re.IGNORECASE,
)
# S2b: Hono-style `c.req.query('token')`, `c.req.param('secret')`.
HONO_RE = re.compile(
    r"\.\s*req\s*\.\s*(?:query|queries|param)\s*\(\s*(['\"`])(?:%s)\1" % _NAMES,
    re.IGNORECASE,
)
# S2c: a route path literal with a credential parameter, `'/g/:grantId/:token'`.
PATH_PARAM_RE = re.compile(r"['\"`][^'\"`\n]*/:(?:%s)(?![\w-])" % _NAMES, re.IGNORECASE)
# S2d: the agent bearer read out of a path.
BEARER_IN_PATH_RE = re.compile(
    r"pathname.*(?:rmcp_|AGENT_BEARER_PREFIX|parseAgentBearer|openBearer)"
    r"|(?:rmcp_|AGENT_BEARER_PREFIX|parseAgentBearer|openBearer).*pathname"
)
UNREDACTED_RE = re.compile(r"\bgetUnredacted\b")
# W3: a route pattern naming a credential.
ROUTE_CREDENTIAL_RE = re.compile(
    r"(?:token|secret|bearer|api[_-]?key|password|rmcp_|authorization)", re.IGNORECASE
)
# Template placeholders the renderer fills (`rediacc_ci.deploy.*`). A SPLICE stands for whole TOML
# text the template cannot show, either a line of its own (`  @@ROUTE_ENTRY@@`) or a suffix after a
# value (`"..."@@EXTRA_VARS@@`); it is dropped before parsing and counted in the success line, and
# the rendered files of every Worker that commits them are judged in full. A bare VALUE
# placeholder (`x = @@X@@`) is quoted.
SPLICE_LINE_RE = re.compile(r"^[ \t]*@@\w+@@[ \t]*,?[ \t]*$", re.MULTILINE)
SPLICE_SUFFIX_RE = re.compile(r"([\"'\]}])@@\w+@@[ \t]*$", re.MULTILINE)
BARE_PLACEHOLDER_RE = re.compile(r"([=\[,{][ \t]*)@@(\w+)@@(?=[ \t]*(?:[,\]}#]|$))", re.MULTILINE)


class RefusalError(Exception):
    """No verdict can be reached. Exit 1, never a silent pass."""


def tracked(root: pathlib.Path) -> list[str]:
    """Every tracked path under `workers/`, relative to `root`."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", WORKERS],
        capture_output=True,
        check=False,
    )
    files = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]
    if out.returncode != 0:
        raise RefusalError(
            "`git ls-files -- %s` failed (rc=%d) in %s: %s"
            % (WORKERS, out.returncode, root, out.stderr.decode("utf-8", "replace").strip())
        )
    return files


def is_test(rel: str) -> bool:
    return "/__tests__/" in rel or re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", rel) is not None


def wrangler_files(files: list[str]) -> list[str]:
    return sorted(f for f in files if f.endswith(".toml") and "/node_modules/" not in f)


def source_files(files: list[str]) -> list[str]:
    return sorted(
        f
        for f in files
        if f.startswith(MCP) and f.endswith(SOURCE_SUFFIXES) and "/node_modules/" not in f
    )


def strip_template(text: str) -> tuple[str, int]:
    """The template with its splices dropped and bare value placeholders quoted, and the splice count."""
    text, lines = SPLICE_LINE_RE.subn("", text)
    text, suffixes = SPLICE_SUFFIX_RE.subn(r"\1", text)
    return BARE_PLACEHOLDER_RE.sub(r'\1"@@\2@@"', text), lines + suffixes


def parse_toml(rel: str, text: str) -> tuple[dict, int]:
    """Parse a wrangler file and count its template splices. Unparseable is a refusal."""
    stripped, splices = strip_template(text)
    try:
        return tomllib.loads(stripped), splices
    except tomllib.TOMLDecodeError as exc:
        raise RefusalError(
            "%s does not parse as TOML (%s). An unread wrangler file is an unchecked one; fix "
            "the file or teach `parse_toml` its template form." % (rel, exc)
        ) from exc


def _walk(node, trail: tuple[str, ...] = ()):
    """Yield (key path, value) for every leaf and every keyed node."""
    if isinstance(node, dict):
        for key, value in node.items():
            path = (*trail, str(key))
            yield path, value
            yield from _walk(value, path)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, (*trail, "[%d]" % i))


def _non_empty(value) -> bool:
    return value not in (None, False, "", [], {})


def route_patterns(doc: dict) -> list[str]:
    """Every route pattern the file declares, at the top level and under `env.*`."""
    tables = [doc, *[(v if isinstance(v, dict) else {}) for v in (doc.get("env") or {}).values()]]
    out = []
    for table in tables:
        entries = list(table.get("routes") or [])
        if table.get("route") is not None:
            entries.append(table["route"])
        for entry in entries:
            if isinstance(entry, str):
                out.append(entry)
            elif isinstance(entry, dict) and isinstance(entry.get("pattern"), str):
                out.append(entry["pattern"])
    return out


def evaluate_wrangler(rel: str, doc: dict) -> list[str]:
    findings = []
    for path, value in _walk(doc):
        key = path[-1].lower().replace("-", "_")
        dotted = ".".join(path)
        if key in HEADER_FIELD_KEYS and _non_empty(value):
            findings.append(
                "W1 %s: `%s` declares logged custom fields (%r). A logged request header carries "
                "the MCP bearer in clear (Design 9, D14); delete the key." % (rel, dotted, value)
            )
        elif isinstance(value, str) and HEADER_FIELD_VALUE_RE.search(value):
            findings.append(
                "W1 %s: `%s` = %r names a request header or cookie log field. Headers carry the "
                "MCP bearer; log nothing from them." % (rel, dotted, value)
            )
    findings += [
        "W3 %s: route pattern %r carries a query string or names a credential. A "
        "credential travels in a header, never in a URL (D14)." % (rel, pattern)
        for pattern in route_patterns(doc)
        if "?" in pattern or ROUTE_CREDENTIAL_RE.search(pattern)
    ]
    if rel.startswith(MCP):
        findings += _evaluate_mcp_platform(rel, doc)
    return findings


def _evaluate_mcp_platform(rel: str, doc: dict) -> list[str]:
    findings = []
    tables = [("", doc)] + [
        ("env.%s." % name, table)
        for name, table in (doc.get("env") or {}).items()
        if isinstance(table, dict)
    ]
    for prefix, table in tables:
        if table.get("logpush") is True:
            findings.append(
                "W2 %s: `%slogpush = true` ships every request of the MCP Worker to a Logpush "
                "job. Set it false or delete it." % (rel, prefix)
            )
        if _non_empty(table.get("tail_consumers")):
            findings.append(
                "W2 %s: `%stail_consumers` binds a Tail Worker to the MCP Worker, and a Tail "
                "Worker can call getUnredacted() on its request headers. Delete the binding."
                % (rel, prefix)
            )
        obs = table.get("observability")
        if not isinstance(obs, dict):
            continue
        raw_logs = obs.get("logs")
        logs: dict = raw_logs if isinstance(raw_logs, dict) else {}
        logs_on = logs.get("enabled", obs.get("enabled")) is True
        if logs_on and logs.get("invocation_logs") is not False:
            findings.append(
                "W2 %s: `%sobservability.logs` is on and `invocation_logs` is %r. The platform "
                "default records each request's URL and headers; set `invocation_logs = false`."
                % (rel, prefix, logs.get("invocation_logs", "unset"))
            )
    return findings


def evaluate_source(rel: str, text: str) -> list[str]:
    findings = []
    test = is_test(rel)
    for n, line in enumerate(text.splitlines(), 1):
        if UNREDACTED_RE.search(line):
            findings.append(
                "S1 %s:%d: `getUnredacted` exposes every request header, the bearer included. "
                "Delete the call; no MCP code needs unredacted headers." % (rel, n)
            )
        if test:
            continue
        for rule, regex, what in (
            ("S2", QUERY_RE, "a credential query parameter"),
            ("S2", HONO_RE, "a credential query or path parameter"),
            ("S2", PATH_PARAM_RE, "a credential path parameter in a route"),
            ("S2", BEARER_IN_PATH_RE, "the agent bearer parsed from the path"),
        ):
            if regex.search(line):
                findings.append(
                    "%s %s:%d: %s: %s. A URL is logged in full (D14); read the credential from "
                    "the Authorization or x-api-key header." % (rule, rel, n, what, line.strip())
                )
                break
    return findings


def run(root=None):
    root = pathlib.Path(root or paths.repo_root())
    files = tracked(root)
    wranglers = wrangler_files(files)
    mcp_wranglers = [f for f in wranglers if f.startswith(MCP)]
    sources = source_files(files)
    non_test = [f for f in sources if not is_test(f)]
    for count, what in (
        (len(wranglers), "wrangler file(s) under %s" % WORKERS),
        (len(mcp_wranglers), "wrangler file(s) under %s" % MCP),
        (len(non_test), "non-test source file(s) under %s" % MCP),
    ):
        if count == 0:
            raise RefusalError(
                "0 %s. The gate is not seeing the tree; its green would mean nothing." % what
            )
    findings: list[str] = []
    routes = 0
    spliced: list[str] = []
    for rel in wranglers:
        doc, splices = parse_toml(rel, (root / rel).read_text(encoding="utf-8"))
        if splices:
            spliced.append("%s (%d)" % (rel, splices))
        routes += len(route_patterns(doc))
        findings += evaluate_wrangler(rel, doc)
    for rel in sources:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise RefusalError("%s is unreadable (%s)." % (rel, exc)) from exc
        findings += evaluate_source(rel, text)
    stats = {
        "wranglers": len(wranglers),
        "mcp_wranglers": len(mcp_wranglers),
        "routes": routes,
        "sources": len(sources),
        "non_test": len(non_test),
        "spliced": spliced,
    }
    return findings, stats


def main(argv=None) -> int:
    argv = list(argv or [])
    if "--selftest" in argv:
        return 2 if selftest() else 0
    rc = controls_first("mcp logging guard", selftest)
    if rc:
        return rc
    try:
        findings, stats = run()
    except RefusalError as exc:
        log.error("mcp logging guard: %s" % exc)
        return 1
    log.info(
        "  %d wrangler file(s) under %s (%d under %s, %d route pattern(s)); %d source file(s) "
        "under %s, %d of them non-test"
        % (
            stats["wranglers"],
            WORKERS,
            stats["mcp_wranglers"],
            MCP,
            stats["routes"],
            stats["sources"],
            MCP,
            stats["non_test"],
        )
    )
    if stats["spliced"]:
        log.info(
            "  template splices not judged here (the renderer fills them): %s"
            % ", ".join(stats["spliced"])
        )
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s): an MCP credential could reach a log or a URL (PLAN-rmcp-remote-worker.md "
            "Design 9)." % len(findings)
        )
        return 1
    log.success(
        "mcp logging guard: no logged header, tail consumer, getUnredacted or URL credential"
    )
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------

_MCP_TOML = """\
name = "mcp-eu"
main = "src/index.ts"
routes = [
  { pattern = "@@HOST@@", custom_domain = true }
]

[observability]
enabled = true

[observability.logs]
enabled = true
invocation_logs = false
persist = false
"""

_PROXY_TOML = """\
name = "proxy-eu"
routes = [
  { pattern = "proxy.eu.example", custom_domain = true }
]
"""

_SOURCE = """\
const GRANT_PATH = /^\\/g\\/([A-Za-z0-9_-]{1,64})$/;
export function grantOf(request: Request): string | undefined {
  const url = new URL(request.url);
  const client = url.searchParams.get('client_id');
  for (const [name] of url.searchParams) void name;
  void client;
  return GRANT_PATH.exec(url.pathname)?.[1];
}
"""


def _fixture(tmp, files: Mapping[str, str | None] | None = None):
    root = pathlib.Path(tmp)
    body: dict[str, str | None] = {
        "workers/mcp/wrangler.template.toml": _MCP_TOML,
        "workers/proxy/wrangler.template.toml": _PROXY_TOML,
        "workers/mcp/src/index.ts": _SOURCE,
        "workers/mcp/src/__tests__/index.test.ts": "new URL('https://x/g/a?access_token=1');\n",
    }
    body.update(files or {})
    for rel, text in body.items():
        if text is None:
            continue
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A", "-f", "."]):
        subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    return root


def _findings(files: dict[str, str] | None = None) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        return run(_fixture(tmp, files))[0]


def _refused(files: dict[str, str]) -> bool:
    try:
        _findings(files)
    except RefusalError:
        return True
    return False


def _fires(findings: list[str], prefix: str) -> bool:
    return any(f.startswith(prefix) for f in findings)


@git_isolated
def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""

    check = Checker()
    mcp = "workers/mcp/wrangler.template.toml"
    src = "workers/mcp/src/index.ts"
    check("CONTROL: the clean fixture is clean", _findings() == [])
    check(
        "PLANT W1: a custom_fields list in any Worker's wrangler file reds",
        _fires(
            _findings(
                {
                    "workers/proxy/wrangler.template.toml": _PROXY_TOML
                    + '\n[logging]\ncustom_fields = ["authorization"]\n'
                }
            ),
            "W1 workers/proxy/",
        ),
    )
    check(
        "PLANT W1: a string naming the RequestHeaders log field reds",
        _fires(
            _findings({mcp: _MCP_TOML + '\n[vars]\nLOG_FIELDS = "RequestHeaders,ClientIP"\n'}),
            "W1 " + mcp,
        ),
    )
    check(
        "PLANT W2: invocation_logs switched on in the MCP wrangler file reds",
        _fires(
            _findings({mcp: plant(_MCP_TOML, "invocation_logs = false", "invocation_logs = true")}),
            "W2 " + mcp,
        ),
    )
    check(
        "PLANT W2: invocation_logs left unset while logs are on reds (the default is on)",
        _fires(_findings({mcp: plant(_MCP_TOML, "invocation_logs = false\n", "")}), "W2 " + mcp),
    )
    check(
        "PLANT W2: logpush = true on the MCP Worker reds",
        _fires(
            _findings(
                {mcp: plant(_MCP_TOML, 'main = "src/index.ts"', 'main = "x"\nlogpush = true')}
            ),
            "W2 " + mcp,
        ),
    )
    check(
        "PLANT W2: a tail consumer under env.bench of the MCP Worker reds",
        _fires(
            _findings(
                {mcp: _MCP_TOML + '\n[env.bench]\ntail_consumers = [{ service = "tail" }]\n'}
            ),
            "W2 " + mcp,
        ),
    )
    check(
        "ANTI-SILENCER: logpush and invocation logs on a NON-MCP Worker are not W2's business",
        _findings({"workers/proxy/wrangler.template.toml": _PROXY_TOML + "logpush = false\n"})
        == [],
    )
    check(
        "PLANT W3: a route pattern with a token query string reds",
        _fires(
            _findings(
                {
                    mcp: plant(
                        _MCP_TOML, 'pattern = "@@HOST@@"', 'pattern = "mcp.example/g/*?token=*"'
                    )
                }
            ),
            "W3 " + mcp,
        ),
    )
    check(
        "PLANT S1: getUnredacted in an MCP test file reds (tests are not exempt from S1)",
        _fires(
            _findings(
                {"workers/mcp/src/__tests__/tail.test.ts": "event.getUnredacted().headers;\n"}
            ),
            "S1 workers/mcp/src/__tests__/tail.test.ts",
        ),
    )
    check(
        "PLANT S2: searchParams.get('access_token') in a handler reds",
        _fires(
            _findings(
                {
                    src: plant(
                        _SOURCE,
                        "searchParams.get('client_id')",
                        "searchParams.get('access_token')",
                    )
                }
            ),
            "S2 " + src,
        ),
    )
    check(
        'PLANT S2: a Hono c.req.query("token") reds',
        _fires(
            _findings({src: _SOURCE + 'const t = c.req.query("token");\n'}),
            "S2 " + src,
        ),
    )
    check(
        "PLANT S2: a route path with a :secret parameter reds",
        _fires(_findings({src: _SOURCE + "app.post('/g/:grantId/:secret', h);\n"}), "S2 " + src),
    )
    check(
        "PLANT S2: the agent bearer parsed from the pathname reds",
        _fires(
            _findings({src: _SOURCE + "const b = parseAgentBearer(url.pathname.slice(3));\n"}),
            "S2 " + src,
        ),
    )
    check(
        "PLANT S2: writing the secret S into an outbound URL reds",
        _fires(_findings({src: _SOURCE + "u.searchParams.set('S', secret);\n"}), "S2 " + src),
    )
    check(
        "ANTI-SILENCER: a test URL carrying access_token is not an S2 finding",
        _findings(
            {
                "workers/mcp/src/__tests__/index.test.ts": (
                    "const u = new URL('https://x/g/a?access_token=1');\n"
                    "u.searchParams.get('access_token');\n"
                )
            }
        )
        == [],
    )
    check(
        "ANTI-SILENCER: authRequest, client_id and a non-credential :grantId do not red",
        _findings(
            {
                src: _SOURCE
                + "const h = url.searchParams.get('authRequest');\n"
                + "app.post('/g/:grantId', h);\n"
                + "page.searchParams.set('grant', grantId);\n"
            }
        )
        == [],
    )
    check(
        "REFUSAL: no wrangler file under workers/mcp/ is refused, not passed",
        _refused_without("workers/mcp/wrangler.template.toml"),
    )
    check(
        "REFUSAL: no non-test MCP source is refused, not passed",
        _refused_without("workers/mcp/src/index.ts"),
    )
    check(
        "REFUSAL: an unparseable wrangler file is refused, not skipped",
        _refused({"workers/proxy/wrangler.template.toml": "name = [unclosed\n"}),
    )
    check(
        "CONTROL: a bare @@PLACEHOLDER@@ value in a template still parses",
        _findings(
            {
                "workers/proxy/wrangler.template.toml": _PROXY_TOML
                + 'workers_dev = @@DEV@@\nq = "a-@@X@@-dlq"\n'
            }
        )
        == [],
    )
    spliced = (
        'name = "@@NAME@@"\nroutes = [\n  @@ROUTE_ENTRY@@\n]\n\n'
        '[vars]\nREGION = "@@REGION@@"@@EXTRA_VARS@@\n'
    )
    check(
        "CONTROL: line and suffix splices are dropped and counted, so the template parses",
        strip_template(spliced)[1] == 2
        and _findings({"workers/proxy/wrangler.template.toml": spliced}) == [],
    )
    check(
        "ANTI-SILENCER: a finding beside a splice still reds",
        _fires(
            _findings(
                {
                    "workers/proxy/wrangler.template.toml": spliced
                    + 'LOG = "RequestHeaders"@@MORE@@\n'
                }
            ),
            "W1 workers/proxy/",
        ),
    )
    return not check.ok


def _refused_without(rel: str) -> bool:
    """True when the clean fixture minus `rel` is refused rather than judged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, {rel: None})
        try:
            run(root)
        except RefusalError:
            return True
    return False


if __name__ == "__main__":
    from rediacc_ci.quality import gate_args

    gate_args.parse("check_mcp_logging_guard.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(main(sys.argv[1:]))
