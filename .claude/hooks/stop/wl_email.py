"""wl_email: the two-way operator email channel (v13 F2).

WHY THIS EXISTS. Every other channel in this hook talks to a MODEL. A `- [?]`
deferral and a request addressed to the operator are the two shapes that a
model cannot settle by definition, and until now both waited for the operator
to happen to read a stop report. The operator is not always at the terminal,
so "waiting for the operator" silently meant "waiting for the operator to come
back", and the DEFAULT: executed in the meantime. This module pushes those
questions OUT, over SES, to a mailbox the operator actually watches.

IMPLICIT TRIGGER, deliberately. There is no "anything to ask?" prompt and no
verb a session invokes to send mail: a channel a model has to REMEMBER to use
is a channel that goes unused, which is the same failure as the finding
written into a commit message that nobody read. Mail fires automatically from
artifacts the hook already reads:

  1. an open, unresolved request whose recipient is the literal string
     "operator" -- emailed ONCE EVER, keyed by request id;
  2. a `- [?]` deferral carrying a DEFAULT: whose last update is older than
     WORKLIST_EMAIL_DEFER_AGE_MIN -- emailed once per UPDATE GENERATION, keyed
     by (item id, upd stamp), so touching an item re-arms it and an untouched
     one never nags twice.

Every candidate on one stop folds into ONE digest, because twelve separate
mails about one session's backlog is a mailbox the operator learns to ignore.

THE ANSWER PATH NEEDS NO NEW CODE. The operator replies by telling any session
to run `worklist.py --answer operator <id> '<words>'`; "operator" passes the
existing prefix validation and the self-answer guard (which compares the
answerer to the request's `from`), and the asker's next stop delivers the text
inside its block via the existing unacked-answer check.

SAFETY PROPERTIES, in the order they bite:
  * NEVER BLOCKS AND NEVER CRASHES A STOP. pump() returns a note string and
    its caller wraps it in try/except. A mail channel that can wedge the gate
    would be a worse bug than the silence it fixes.
  * EXACTLY ONCE ACROSS CONCURRENT SESSIONS. The ledger append is a
    check-then-append, so it runs under a NON-BLOCKING exclusive flock with a
    re-read inside the lock (the escalate_requests pattern). The loser skips
    and retries next stop; nobody double-sends.
  * DELAY, NEVER LOSS. Inside WORKLIST_EMAIL_COOLDOWN_MIN of the last send,
    nothing is sent -- the candidates simply stay candidates and go out with
    the next digest. A failure backs off WORKLIST_EMAIL_RETRY_MIN and says so
    loudly, because a mail channel that fails quietly is worse than none.
  * SECRETS ARE NEVER ARGV. curl reads the AWS key pair from a `-K -` config
    on stdin, so `ps` on a shared box shows no credential. The JSON body goes
    through a mkstemp file (unlinked afterwards) rather than the command line,
    which also keeps a 4 KB digest off the argv limit.
  * THE SUITE NEVER TOUCHES THE NETWORK. WORKLIST_EMAIL_TRANSPORT=file:<dir>
    writes the payload into <dir> instead of sending it. The directory is NOT
    created on demand, which is what makes `file:/nonexistent-dir` a usable
    failure-path fixture.
"""

import fcntl
import hashlib
import hmac
import json
import os
import pathlib
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

import wl_core as C
import wl_requests as R
import wl_store as S

# Off is a real state, not a test hatch: the operator may be on a plane, or a
# checkout may be a scratch clone whose deferrals are nobody's business.
DISABLED = os.environ.get("WORKLIST_EMAIL", "on").lower() in ("off", "0", "no")
COOLDOWN_MIN = float(os.environ.get("WORKLIST_EMAIL_COOLDOWN_MIN", "120"))
RETRY_MIN = float(os.environ.get("WORKLIST_EMAIL_RETRY_MIN", "15"))
DEFER_AGE_MIN = float(os.environ.get("WORKLIST_EMAIL_DEFER_AGE_MIN", "60"))
RECIPIENT = os.environ.get("WORKLIST_EMAIL_TO", "muhammed@rediacc.com")
# The Stop hook's own budget is 15s and this runs inside it, so the transport
# gets a hard ceiling rather than the harness killing the whole hook.
SEND_TIMEOUT_S = float(os.environ.get("WORKLIST_EMAIL_TIMEOUT_S", "20"))
# Digest bodies are for a human on a phone; a runaway backlog must not mail a
# 500-line wall.
MAX_QUESTIONS = int(os.environ.get("WORKLIST_EMAIL_MAX_QUESTIONS", "12"))
BODY_CHARS = 600

CURL_VERSION_RE = re.compile(r"^curl\s+(\d+)\.(\d+)")
# --aws-sigv4 landed in curl 7.75.0. Below that the flag is silently unknown
# and the request goes out UNSIGNED, which SES rejects with a 403 that reads
# like a credential problem, so the version is probed rather than assumed.
CURL_MIN = (7, 75)

REQUIRED = (
    "AWS_SES_ACCESS_KEY_ID",
    "AWS_SES_SECRET_ACCESS_KEY",
    "AWS_SES_REGION",
    "AWS_SES_FROM",
)


def ledger_path(worklist):
    return worklist.with_suffix(".emails")


def ledger_lock_path(worklist):
    return str(ledger_path(worklist)) + ".lock"


def unconfigured_marker(worklist, session_id):
    return worklist.with_suffix(".emailunconf-%s" % (session_id or "unknown")[:8])


def read_ledger(worklist):
    """Every parseable row of the append-only ledger, oldest first. A torn
    tail line (crash mid-write) fails json.loads and is skipped, exactly as in
    the requests log; an unreadable ledger reads as empty, which costs at most
    one duplicate mail and never loses a question."""
    p = ledger_path(worklist)
    rows = []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            rows.append(ev)
    return rows


def _newest_age_min(rows, ev):
    ages = [
        C.stamp_age_min(str(r.get("at", "")))
        for r in rows
        if r.get("ev") == ev
    ]
    ages = [a for a in ages if a is not None]
    return min(ages) if ages else None


def sent_keys(rows):
    return {str(r.get("key", "")) for r in rows if r.get("ev") == "sent"}


# ---- credentials -----------------------------------------------------------

def credentials(root):
    """(cfg, path). cfg is None when the channel is not configured.

    KEY=VALUE lines from WORKLIST_SES_ENV, else <root>/private/account/.env.
    Deliberately the AWS_SES_* quartet and NOT the SES_AK_ID/SES_AK_SECRET
    pair that lives in the same file: those are the IAM-admin credentials the
    rotation tool uses, and a Stop hook has no business holding them.
    """
    p = os.environ.get("WORKLIST_SES_ENV") or str(
        pathlib.Path(root) / "private" / "account" / ".env"
    )
    vals = {}
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        return None, p
    if not all(vals.get(k) for k in REQUIRED):
        return None, p
    return (
        {
            "key": vals["AWS_SES_ACCESS_KEY_ID"],
            "secret": vals["AWS_SES_SECRET_ACCESS_KEY"],
            "region": vals["AWS_SES_REGION"],
            "from": vals["AWS_SES_FROM"],
            "to": RECIPIENT,
        },
        p,
    )


# ---- transport -------------------------------------------------------------

_curl_probe = None


def curl_usable():
    """True when curl exists and is new enough for --aws-sigv4. Probed ONCE
    per process: the hook may call send() several times in a run, and a
    subprocess per call to ask the same question is pure latency."""
    global _curl_probe
    if _curl_probe is None:
        _curl_probe = False
        try:
            r = subprocess.run(
                ["curl", "--version"], capture_output=True, text=True, timeout=5
            )
            m = CURL_VERSION_RE.match((r.stdout or "").strip())
            if r.returncode == 0 and m:
                _curl_probe = (int(m.group(1)), int(m.group(2))) >= CURL_MIN
        except (OSError, subprocess.SubprocessError, ValueError):
            _curl_probe = False
    return _curl_probe


def payload_for(cfg, subject, body):
    return {
        "FromEmailAddress": cfg["from"],
        "Destination": {"ToAddresses": [cfg["to"]]},
        "Content": {
            "Simple": {
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body}},
            }
        },
    }


def endpoint(region):
    return "https://email.%s.amazonaws.com/v2/email/outbound-emails" % region


def _send_file(transport, blob):
    """The test seam. Writes the payload where a real send would have gone.
    The directory is NOT created: a missing one is the failure-path fixture."""
    d = transport.split(":", 1)[1]
    try:
        fd, p = tempfile.mkstemp(dir=d, prefix="mail-", suffix=".json")
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
    except OSError as exc:
        return "file transport %s: %s" % (d, exc)
    return ""


def _send_curl(cfg, blob):
    """POST via curl with SigV4. The key pair rides a `-K -` config on stdin
    so it never appears in argv; the body rides a temp file for the same
    reason plus the argv size limit."""
    tmp = ""
    try:
        fd, tmp = tempfile.mkstemp(prefix="wl-mail-", suffix=".json")
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        # The response BODY rides a second temp file and is quoted on failure:
        # the first live failure reported a bare "SES HTTP 403" while the body
        # said "The security token included in the request is invalid", which
        # is the difference between "check the signature code" and "the key
        # was rotated out" -- a diagnosis the error must carry itself.
        bfd, btmp = tempfile.mkstemp(prefix="wl-mail-resp-", suffix=".json")
        os.close(bfd)
        cmd = [
            "curl", "-sS", "-X", "POST", endpoint(cfg["region"]),
            "--aws-sigv4", "aws:amz:%s:ses" % cfg["region"],
            "-H", "Content-Type: application/json",
            "--data", "@" + tmp,
            "-K", "-",
            "-o", btmp,
            "-w", "%{http_code}",
        ]
        r = subprocess.run(
            cmd,
            input='user = "%s:%s"\n' % (cfg["key"], cfg["secret"]),
            capture_output=True,
            text=True,
            timeout=SEND_TIMEOUT_S,
        )
        try:
            resp_body = open(btmp, "r", encoding="utf-8", errors="replace").read(200)
        except OSError:
            resp_body = ""
        finally:
            try:
                os.unlink(btmp)
            except OSError:
                pass
        code = (r.stdout or "").strip()[-3:]
        if r.returncode != 0:
            return "curl exit %d: %s" % (r.returncode, (r.stderr or "")[:160])
        if not code.startswith("2"):
            return "SES HTTP %s: %s" % (code or "?", resp_body.strip()[:160])
    except (OSError, subprocess.SubprocessError) as exc:
        return "curl: %s: %s" % (type(exc).__name__, str(exc)[:160])
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return ""


def sigv4_headers(cfg, blob, host, path, service="ses"):
    """The AWS Signature Version 4 header set for one POST. Exists so a box
    with a pre-7.75 curl (or no curl) still has a working channel rather than
    a silently dead one."""
    now = C.utcnow()
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    region = cfg["region"]
    signed = "content-type;host;x-amz-date"
    canonical_headers = "content-type:application/json\nhost:%s\nx-amz-date:%s\n" % (
        host,
        amzdate,
    )
    canonical = "\n".join(
        ["POST", path, "", canonical_headers, signed, hashlib.sha256(blob).hexdigest()]
    )
    scope = "%s/%s/%s/aws4_request" % (datestamp, region, service)
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amzdate,
            scope,
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        ]
    )

    def mac(key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k = mac(("AWS4" + cfg["secret"]).encode("utf-8"), datestamp)
    for part in (region, service, "aws4_request"):
        k = mac(k, part)
    sig = hmac.new(k, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Amz-Date": amzdate,
        "Authorization": "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s"
        % (cfg["key"], scope, signed, sig),
    }


def _send_urllib(cfg, blob):
    url = endpoint(cfg["region"])
    host = "email.%s.amazonaws.com" % cfg["region"]
    req = urllib.request.Request(
        url, data=blob, method="POST",
        headers=sigv4_headers(cfg, blob, host, "/v2/email/outbound-emails"),
    )
    try:
        with urllib.request.urlopen(req, timeout=SEND_TIMEOUT_S) as resp:
            if resp.status // 100 != 2:
                return "SES HTTP %s" % resp.status
    except urllib.error.HTTPError as exc:
        return "SES HTTP %s: %s" % (exc.code, exc.read()[:160].decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return "urllib: %s: %s" % (type(exc).__name__, str(exc)[:160])
    return ""


def send(cfg, subject, body):
    """"" on success, a short error string on failure. Never raises."""
    blob = json.dumps(payload_for(cfg, subject, body)).encode("utf-8")
    transport = os.environ.get("WORKLIST_EMAIL_TRANSPORT", "")
    if transport.startswith("file:"):
        return _send_file(transport, blob)
    if curl_usable():
        return _send_curl(cfg, blob)
    return _send_urllib(cfg, blob)


# ---- candidates and the digest ---------------------------------------------

def candidates(worklist, fold):
    """[(key, kind, text)] for everything the operator has not been mailed
    about yet, oldest first. Keys are the dedup identity, and the two shapes
    differ on purpose: a request is ONE question forever, so its key is its
    id; a deferral is a question per update generation, so its key carries the
    upd stamp and a `--defer`/`--update` re-arms it."""
    out = []
    try:
        reqs = R.read_requests(worklist)
    except Exception:  # noqa: BLE001 -- a corrupt log must not kill the channel
        reqs = {}
    for r in sorted(reqs.values(), key=lambda x: x["at"]):
        if r["to"] != "operator" or r["acked"] or R.request_resolved(r):
            continue
        out.append(
            (
                "req:%s" % r["id"],
                "request",
                "request #%s (asked by %s at %s)\n    %s\n"
                "    Answer it with:\n"
                "      .claude/hooks/stop/worklist.py --answer operator %s '<your answer>'"
                % (r["id"], r["from"], r["at"], r["body"][:BODY_CHARS], r["id"]),
            )
        )
    for rec in sorted(fold.items, key=lambda x: str(x.get("upd", ""))):
        if rec["state"] != "?" or not C.DEFAULT_TOKEN.search(rec.get("text", "")):
            continue
        upd = str(rec.get("upd", ""))
        age = C.stamp_age_min(upd)
        if age is None or age < DEFER_AGE_MIN:
            continue
        left = S.DEFER_WINDOW_MIN - age
        when = (
            "its DEFAULT has already executed or is due now"
            if left <= 0
            else "its DEFAULT executes in about %d min" % left
        )
        out.append(
            (
                "defer:%s:%s" % (rec["id"], upd),
                "defer",
                "deferral #%s (owner %s, last touched %s, %d min ago; %s)\n    %s\n"
                "    Decide it by telling the session what to do, or let the DEFAULT run."
                % (
                    rec["id"],
                    rec.get("owner") or "unowned",
                    upd or "?",
                    age,
                    when,
                    rec.get("text", "")[:BODY_CHARS],
                ),
            )
        )
    return out


def digest(me8, root, rows):
    """(subject, body) for one stop's whole batch."""
    subject = "[worklist %s] %d question(s) pending" % (me8, len(rows))
    body = [
        "%d question(s) from session %s in %s are waiting on you." % (len(rows), me8, root),
        "",
    ]
    for i, (_k, _kind, text) in enumerate(rows, 1):
        body.append("%d. %s" % (i, text))
        body.append("")
    body.append(
        "Answer by telling the session to run:\n"
        "    .claude/hooks/stop/worklist.py --answer operator <request-id> '<your answer>'\n"
        "A deferral has no request id: reply to the session in words, and it will "
        "either act on your decision or let the DEFAULT execute."
    )
    return subject, "\n".join(body)


# ---- the pump --------------------------------------------------------------

def pump(root, worklist, session_id, fold):
    """Send at most one digest, return the note that rides the stop report.

    "" means quiet, which is the overwhelmingly common answer: no candidates,
    or inside the cooldown, or inside a failure backoff, or another session
    holds the lock. Only a SEND, a FAILURE or an UNCONFIGURED channel speaks,
    because a channel that narrates its own silence every stop is noise.

    Called from run_stop AFTER the poll fast path has exited, so a 5-minute
    no-op poll never pays for reading the ledger, let alone for a subprocess.
    """
    import worklist_messages as M

    if DISABLED:
        return ""
    me8 = (session_id or "unknown")[:8]
    rows = candidates(worklist, fold)
    if not rows:
        return ""
    cfg, env_path = credentials(root)
    if cfg is None:
        # LATCHED PER SESSION, and an allow-path note rather than a block: an
        # unconfigured mail channel is an operator setup gap, not a session's
        # unfinished work, and blocking on it would hold a turn hostage to a
        # file the session may not be allowed to create.
        marker = unconfigured_marker(worklist, session_id)
        if marker.exists():
            return ""
        try:
            marker.write_text(C.stamp_now(), encoding="utf-8")
        except OSError:
            pass
        return M.N_EMAIL_UNCONFIGURED % (env_path, len(rows))
    ledger = read_ledger(worklist)
    already = sent_keys(ledger)
    rows = [r for r in rows if r[0] not in already]
    if not rows:
        return ""
    last_sent = _newest_age_min(ledger, "sent")
    if last_sent is not None and last_sent < COOLDOWN_MIN:
        return ""  # delay, never loss: they ride the next digest
    # MAIL IS OPTIONAL (operator, 2026-07-31: "it should be skipped if there
    # is no successful commit. Just put a warning in the output"). A channel
    # that has FAILED with the current credentials is skipped outright: one
    # warning per session, no retry drumbeat. The health key is the key id,
    # so swapping in fresh credentials re-arms the channel by itself; a
    # ledger row of ev=sent newer than the last fail also re-arms it.
    last_fail = _newest_age_min(ledger, "fail")
    last_sent_any = _newest_age_min(ledger, "sent")
    failed_since_success = last_fail is not None and (
        last_sent_any is None or last_fail < last_sent_any
    )
    if failed_since_success:
        fail_key = next(
            (str(r.get("keyid", "")) for r in reversed(ledger) if r.get("ev") == "fail"),
            "",
        )
        if not fail_key or fail_key == cfg["key"][-6:]:
            warn = unconfigured_marker(worklist, session_id).with_suffix(".failwarned")
            if warn.exists():
                return ""
            try:
                warn.write_text(C.stamp_now(), encoding="utf-8")
            except OSError:
                pass
            last_err = next(
                (str(r.get("err", "")) for r in reversed(ledger) if r.get("ev") == "fail"),
                "?",
            )
            return M.N_EMAIL_SKIPPED % (len(rows), last_err[:200])
    with open(ledger_lock_path(worklist), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return ""  # another stop is sending; it wins, this one retries
        # RE-READ INSIDE THE LOCK. Between the read above and this line another
        # session may have sent the very same digest; without this the two-stop
        # race sends twice, which is the one thing the ledger exists to stop.
        ledger = read_ledger(worklist)
        already = sent_keys(ledger)
        rows = [r for r in rows if r[0] not in already]
        if not rows:
            return ""
        last_sent = _newest_age_min(ledger, "sent")
        if last_sent is not None and last_sent < COOLDOWN_MIN:
            return ""
        rows = rows[:MAX_QUESTIONS]
        subject, body = digest(me8, root, rows)
        err = send(cfg, subject, body)
        stamp = C.stamp_now()
        if err:
            # keyid (last 6 of the access key) makes the failure attributable
            # to a CREDENTIAL: fresh credentials re-arm the skipped channel.
            payloads = [{"ev": "fail", "at": stamp, "err": err[:300], "by": me8,
                         "keyid": cfg["key"][-6:]}]
        else:
            payloads = [
                {"ev": "sent", "at": stamp, "kind": kind, "key": key, "by": me8}
                for key, kind, _t in rows
            ]
        with open(ledger_path(worklist), "a", encoding="utf-8") as f:
            f.write(
                "".join(json.dumps(p, separators=(",", ":")) + "\n" for p in payloads)
            )
    if err:
        return M.N_EMAIL_FAIL % (len(rows), err[:300], RETRY_MIN)
    # A success clears the one-per-session skip warning so a LATER failure
    # with different credentials can warn again.
    try:
        unconfigured_marker(worklist, session_id).with_suffix(".failwarned").unlink()
    except OSError:
        pass
    return M.N_EMAIL_SENT % (len(rows), cfg["to"], COOLDOWN_MIN)
