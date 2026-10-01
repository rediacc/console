"""A scratch world for driving `scripts/ops/{backup-d1,reset-bench,deploy-bench}.sh` and their Python ports against FAKE binaries.

The scratch PATH is REPLACED, never prepended: it holds the fakes plus symlinks to the few real tools the scripts need, so no real `curl`, `npx` or `wrangler` is reachable. Every fake appends one JSON line to `$FAKE_LOG` (argv, cwd and, for `npx`, which Cloudflare variables were set, never their values) and answers from `$FAKE_ROUTES`.

The bash twins are COPIED into the scratch root (`scripts/ops/*`, `.ci/scripts/lib/common.sh`), so `ROOT_DIR` resolves to the scratch tree and a bash run writes `.backups/` there rather than into the checkout. The Python port runs from the real package with `REDIACC_CI_ROOT` pointing at the scratch root.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
BASH = shutil.which("bash") or "/bin/bash"

REAL_TOOLS = (
    "jq",
    "dirname",
    "basename",
    "mkdir",
    "cat",
    "grep",
    "sed",
    "date",
    "wc",
    "cut",
    "tr",
    "du",
    "awk",
    "head",
    "uname",
    "env",
)

FAKE_CURL = """#!{py}
import json, os, sys
argv = sys.argv[1:]
method = "GET"
if "-X" in argv:
    method = argv[argv.index("-X") + 1]
url = next((a for a in argv if a.startswith("http")), "")
body = argv[argv.index("-d") + 1] if "-d" in argv else None
stdin_has_user = None
if "-K" in argv:
    stdin_has_user = sys.stdin.read().startswith('user = "')
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"tool": "curl", "method": method, "url": url, "body": body,
                          "headers": sorted(argv[i + 1] for i, a in enumerate(argv) if a == "-H"),
                          "sigv4": "--aws-sigv4" in argv, "creds_on_stdin": stdin_has_user,
                          "creds_on_argv": any(a in ("-u", "--user") for a in argv)}}) + "\\n")
if argv[:2] == ["--help", "all"]:
    # A help text far longer than the pipe buffer, with the flag near the top: `grep -q` stops reading at once.
    sys.stdout.write("     --aws-sigv4 <provider1[:provider2:region:service]>\\n" + "     --other-option text\\n" * int(os.environ.get("FAKE_HELP_LINES", "5")))
    sys.exit(0)
routes = json.load(open(os.environ["FAKE_ROUTES"]))
for route in routes:
    if route["method"] == method and route["match"] in url:
        if route.get("rc"):
            sys.exit(route["rc"])
        sys.stdout.write(route["raw"] if "raw" in route else json.dumps(route["body"]))
        if "-w" in argv and route.get("bare"):
            sys.stdout.write("%d" % route.get("status", 200))
        elif "-w" in argv:
            sys.stdout.write("\\n%d" % route.get("status", 200))
        sys.exit(0)
sys.stdout.write(json.dumps({{"success": False, "errors": [{{"message": "no fake route"}}]}}))
"""

FAKE_NPX = """#!{py}
import json, os, sys
argv = sys.argv[1:]
stdin = None
if argv[:3] == ["wrangler", "secret", "bulk"]:
    stdin = sys.stdin.read()
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"tool": "npx", "argv": argv, "cwd": os.path.relpath(os.getcwd(), os.environ["FAKE_ROOT"]),
                          "stdin": json.loads(stdin) if stdin else None,
                          "cf_env": sorted(k for k in os.environ if k.startswith(("CLOUDFLARE_", "CF_")))}}) + "\\n")
if argv[:3] == ["wrangler", "d1", "export"] and "--remote" in argv:
    out = next(a for a in argv if a.startswith("--output="))[len("--output="):]
    if os.environ.get("FAKE_EXPORT_WRITES", "1") == "1":
        open(out, "w").write("CREATE TABLE a;\\nINSERT INTO a;\\n")
    print("Exporting database " + argv[3])
    print("Upload to https://x.r2.cloudflarestorage.com/abc?sig=SECRET")
    print("The link is valid for one hour")
    print("Done")
if argv[:4] == ["wrangler", "r2", "bucket", "list"]:
    print("name:           rediacc-configs-bench")
    print("name:           rediacc-backups-bench")
fail = os.environ.get("FAKE_NPX_FAIL")
if fail and " ".join(argv).startswith(fail):
    sys.exit(int(os.environ.get("FAKE_NPX_RC", "1")))
sys.exit(0)
"""

FAKE_PLAIN = """#!{py}
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"tool": "{name}", "argv": sys.argv[1:], "cwd": os.path.relpath(os.getcwd(), os.environ["FAKE_ROOT"])}}) + "\\n")
sys.exit(0)
"""

FAKE_RUN_SH = """#!{py}
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"tool": "run.sh", "argv": sys.argv[1:]}}) + "\\n")
sys.exit(int(os.environ.get("FAKE_ROTATION_RC", "0")))
"""

TOKEN_ROUTES = [
    {
        "method": "GET",
        "match": "/user/tokens/verify",
        "body": {"result": {"id": "TID"}, "success": True},
    },
    {"method": "DELETE", "match": "/user/tokens/TID", "body": {"success": True}},
    {"method": "GET", "match": "/user", "body": {"result": {"id": "USER1"}}},
    {"method": "GET", "match": "/zones", "body": {"result": [{"id": "ZONE1"}, {"id": "ZONE2"}]}},
    {"method": "POST", "match": "/user/tokens", "body": {"result": {"value": "MINTED"}}},
]

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class World:
    """One scratch tree, one fake PATH, one call log."""

    def __init__(self, tmp: pathlib.Path):
        self.root = tmp / "root"
        self.bin = tmp / "bin"
        self.log = tmp / "calls.jsonl"
        self.routes = tmp / "routes.json"
        self.root.mkdir()
        self.bin.mkdir()
        self.log.write_text("")
        self.set_routes(TOKEN_ROUTES)
        py = sys.executable
        for name, text in (
            ("curl", FAKE_CURL.format(py=py)),
            ("npx", FAKE_NPX.format(py=py)),
            ("npm", FAKE_PLAIN.format(py=py, name="npm")),
            ("sleep", FAKE_PLAIN.format(py=py, name="sleep")),
        ):
            self._write_exec(self.bin / name, text)
        for tool in REAL_TOOLS:
            real = shutil.which(tool)
            if real:
                (self.bin / tool).symlink_to(real)
        (self.bin / "python3").symlink_to(py)
        (self.bin / "bash").symlink_to(BASH)
        for rel in (
            "scripts/ops/backup-d1.sh",
            "scripts/ops/reset-bench.sh",
            "scripts/ops/deploy-bench.sh",
            "scripts/ops/backup-cutover-preflight.sh",
            "scripts/ops/apply-cf-redirect-rules.sh",
            "scripts/ops/lib/cf-auth.sh",
            ".ci/scripts/lib/common.sh",
        ):
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dest)
        (self.root / "workers/account/node_modules").mkdir(parents=True)
        (self.root / "workers/account/wrangler.bench.toml").write_text(
            '[[r2_buckets]]\nbucket_name = "rediacc-configs-bench"\n'
        )
        (self.root / "private/account/web/node_modules").mkdir(parents=True)
        (self.root / "private/account").mkdir(parents=True, exist_ok=True)
        (self.root / ".ci").mkdir(exist_ok=True)
        (self.root / ".ci/rediacc_ci").symlink_to(ROOT / ".ci/rediacc_ci")
        self._write_exec(self.root / "run.sh", FAKE_RUN_SH.format(py=py))

    @staticmethod
    def _write_exec(path: pathlib.Path, text: str) -> None:
        path.write_text(text)
        path.chmod(0o755)

    def set_routes(self, routes: list[dict]) -> None:
        self.routes.write_text(json.dumps(routes))

    def env(self, **extra: str) -> dict[str, str]:
        env = {
            "PATH": str(self.bin),
            "HOME": str(self.root),
            "LC_ALL": "C",
            "FAKE_LOG": str(self.log),
            "FAKE_ROUTES": str(self.routes),
            "FAKE_ROOT": str(self.root),
            "REDIACC_CI_ROOT": str(self.root),
            "PYTHONPATH": str(ROOT / ".ci"),
            "REDIACC_BWS_PROFILES": "deploy-bench",
        }
        env.update(extra)
        return env

    def calls(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text().splitlines() if line]

    def reset_log(self) -> None:
        self.log.write_text("")

    def bash(
        self, script: str, args: list[str], env: dict[str, str], stdin: str = ""
    ) -> tuple[int, str, str]:
        proc = subprocess.run(
            [BASH, str(self.root / script), *args],
            capture_output=True,
            text=True,
            env=env,
            input=stdin,
            cwd=str(self.root),
            check=False,
            timeout=60,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def port(
        self, module: str, args: list[str], env: dict[str, str], stdin: str = ""
    ) -> tuple[int, str, str]:
        proc = subprocess.run(
            [sys.executable, "-m", module, *args],
            capture_output=True,
            text=True,
            env=env,
            input=stdin,
            cwd=str(self.root),
            check=False,
            timeout=60,
        )
        return proc.returncode, proc.stdout, proc.stderr


def normalise_calls(calls: list[dict], mask_token_policies: bool = True) -> list[dict]:
    """The comparable form of a call log: curl bodies parsed so key spacing is not a difference.

    The token-mint POST's policy list is masked by default: the port adds one permission group on purpose (Workers R2 Storage Write), and the mint tests that look at it pass `mask_token_policies=False`.
    """
    out = []
    for raw in calls:
        call = dict(raw)
        if call.get("body"):
            call["body"] = json.loads(call["body"])
            if (
                mask_token_policies
                and call["url"].endswith("/user/tokens")
                and call["method"] == "POST"
            ):
                call["body"] = {"name": call["body"]["name"], "policies": "<masked>"}
        out.append(call)
    return out


def strip(text: str) -> str:
    return ANSI.sub("", text)


def mask_stamp(text: str) -> str:
    return re.sub(r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d", "<STAMP>", text)


def mask_root(text: str, world: World) -> str:
    return text.replace(str(world.root), "<ROOT>")
