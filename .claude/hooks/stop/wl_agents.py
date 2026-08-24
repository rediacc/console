"""wl_agents: which specialist agent this session should have been told about.

A deterministic matcher over the `description` frontmatter of the agent files
in `.claude/agents/`. No model call, no network, no writes: this runs on EVERY
stop, and `wl_judge.py:20-39` records what a second paid call costs (4.9-20.0s,
and one live timeout that BLOCKED a stop).

WHY IT EXISTS. On 2026-08-14 the operator had to hint twice by hand ("there is
bench server deployment", "@.claude/agents/ may help for ops as well") because
nothing surfaced the seven specialists that already existed. The word "bench"
appeared ZERO times across all seven `description` fields and exactly once in
the whole directory -- in a BODY. The knowledge existed; the matching surface
did not.

THREE DESIGN DECISIONS THAT ARE MEASUREMENTS, NOT PREFERENCES
(the numbers are from PLAN-agent-hints-implementation.md sections 2, 3.2, 3.5):

  1. DESCRIPTIONS ONLY. Bodies were prototyped and made the matcher measurably
     WORSE: they bought zero rescued cases and cost a false positive, because
     every word a 33 KB body mentions in passing is a word that stops
     discriminating. Descriptions yield 27-59 discriminative terms per agent;
     bodies yield 118-734. Do not widen this corpus without beating 12/0/0.
  2. TOKENIZE ONCE, INTERSECT SETS. A regex per term against the haystack
     measured 17.4 ms per stop; this measures 1.4 ms for byte-identical
     verdicts. The set form also kills the `read`-matches-`README` bug class BY
     CONSTRUCTION, rather than by remembering a lookaround.
  3. NO CACHE. Caching 1.4 ms would be an optimisation of nothing, and a cache
     is precisely what would let a DELETED agent keep being recommended. The
     corpus is re-read from disk on every call.

Errors are RETURNED, never raised: this module is consulted on the path that
ends every turn in every session, so an exception here is a session that cannot
stop. A corpus that cannot be read degrades to silence plus a loud note.
"""

import os
import pathlib
import re

import wl_core as C

# ---- knobs (WORKLIST_* convention, wl_checks.py:36-63) -----------------------
# Read at import: every stop is a fresh process, and the CI gate wants the same
# defaults the hook runs with rather than a configuration nothing executes.
ENABLED = os.environ.get("WORKLIST_AGENT_HINT", "on").strip().lower() not in (
    "off",
    "0",
    "false",
    "no",
)
MIN_SCORE = float(os.environ.get("WORKLIST_AGENT_HINT_MIN_SCORE", "2"))
# 1, not 2. Measured against five realistic composite haystacks (brief + open
# items + last message + paths, ~500 chars, the shape the stop path actually
# assembles): all four threshold settings gave IDENTICAL verdicts, because a
# real match pulls far away (top 20.0 against next 1.0). The one-line specimens
# in the CI gate are the sensitive case, which is why they are one-liners.
MIN_MARGIN = float(os.environ.get("WORKLIST_AGENT_HINT_MIN_MARGIN", "1"))
# Per-agent re-show window and the hard per-session cap. HYPOTHESIS, both:
# plausible rather than derived, which is exactly why they are env-tunable.
REFRESH_MIN = int(os.environ.get("WORKLIST_AGENT_HINT_REFRESH_MIN", "720"))
MAX_PER_SESSION = int(os.environ.get("WORKLIST_AGENT_HINT_MAX_PER_SESSION", "3"))

# ---- tokenisation -----------------------------------------------------------
# A path-ish token: anything carrying a `/` or a `.` inside it. These are the
# high-value terms and they sit verbatim in the descriptions already
# (`./run.sh`, `scripts/dev/deploy-bench.sh`, `bench.rediacc.com`).
PATH_RE = re.compile(r"[A-Za-z0-9_-]*(?:[./][A-Za-z0-9_-]+)+")
# `{2,}` = three characters minimum, and it is deliberate and measured. A
# four-character minimum silently discards `ops`, `rdc`, `k3s`, among the most
# discriminative tokens this repo has; admitting three-character words took the
# case table from 11/1/0 to 12/0/0, and the rescued case was `"rdc ops up
# --basic"`, a phrase the operator actually types. The stopword list below
# carries the cost of that admission.
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

# ---- morphology --------------------------------------------------------------
# WHY THIS EXISTS, and it is a regression fix rather than a refinement. The
# sentence that motivated this whole feature -- "there is bench server
# DEPLOYMENT, why you don't utilize it?" -- did not fire. account-dev's
# description carries `deploy`, `deploying` and `deploys`, hand-enumerated, and
# not `deployment`, so the query lost that hit to morphology, landed on `bench`
# alone at 1.0, and died against MIN_SCORE. Somebody wrote out three variants of
# one verb by hand and still missed the fourth: that is the hand-maintained-list
# staleness the design explicitly refused for a path->agent table, reappearing
# inside term extraction. Adding "deployment" to a description fixes one query
# and leaves the class open for "provisioning", "deployments", "redeploy".
#
# DUMB AND DETERMINISTIC ON PURPOSE: no stemmer library, no lexicon, no network.
# One suffix, longest match first, and if that match would leave too short a stem
# the word is left ALONE rather than falling through to a shorter suffix -- the
# fall-through is what turns `fixes` into `fixe`.
#
# Applied inside tokenize(), so the corpus and the haystack fold through the
# SAME code and cannot desynchronise. Word terms only: a path term matches
# verbatim, and folding `deploy-bench.sh` would be nonsense.
_FOLD_SUFFIXES = ("ment", "ing", "ed", "s")
# A stem shorter than this is not a word, it is a fragment: `ops` -> `op`,
# `vms` -> `vm`, `k3s` -> `k3` are exactly the discriminative tokens section 3.2
# went out of its way to admit, and stripping them would undo that.
_FOLD_MIN_STEM = 4
# `s` is the dangerous one: these endings are not plurals. Without this,
# `status` -> `statu` and `class` -> `clas`, which is both wrong and unreadable
# in the "Matched on:" line the hint prints.
_FOLD_S_EXCEPT = ("ss", "us", "is", "os")


def fold(word):
    """Strip ONE suffix: `deployment`/`deploying`/`deploys`/`deployed` -> `deploy`.

    Deliberately NOT stripping a trailing `e`, which would fold `restoring` onto
    `restore` and buy one more pairing at the cost of printing stems like
    `restor` at the reader. The hint names its matched terms so that a wrong
    hint is self-refuting in one second; a line full of fragments spends that.
    """
    for suf in _FOLD_SUFFIXES:
        if not word.endswith(suf):
            continue
        if suf == "s" and word.endswith(_FOLD_S_EXCEPT):
            return word
        stem = word[: -len(suf)]
        return stem if len(stem) >= _FOLD_MIN_STEM else word
    return word


def _stem(word):
    """fold() to a fixed point, or "" when any form along the way is a stopword.

    TWO STEPS ARE REAL, not defensive padding: `deployments` strips its plural
    to `deployment` and needs a second pass to reach `deploy`, and `deployments`
    is one of the phrasings a future session will actually type.

    THE STOPWORD CHECK RUNS ON EVERY INTERMEDIATE FORM, which is the whole
    reason this is a loop rather than `fold(fold(w))`. `settings` folds to
    `setting`, a stopword, and must die there; two blind passes would carry it
    on to `sett` and admit a generic word as a discriminative term under an
    unreadable name. Same for `runnings` -> `running`.
    """
    seen = word
    for _ in range(3):
        nxt = fold(seen)
        if nxt == seen:
            return seen
        seen = nxt
        if seen in STOPWORDS or len(seen) < 3:
            return ""
    return seen


PATH_WEIGHT = 3.0
WORD_WEIGHT = 1.0
NAME_WEIGHT = 3.0
# A path term shorter than this is noise (`a.b`, `x/y`): the discriminative
# filter would keep it and it would carry weight 3 for nothing.
PATH_MIN_LEN = 6

# The usual closed class, plus the verbs every description and every task
# sentence in this repo shares. Kept HERE, as one module constant, so the CI
# gate scores against the same list the hook does -- a gate with its own copy
# proves a configuration nothing runs.
_STOPWORD_TEXT = (
    "the and for with from that this than then they them their there these those "
    "into onto over under about above after before between during without within "
    "not but its are was were been being have has had having does did doing "
    "can could should would will shall may might must "
    "you your yours our ours mine his her hers theirs "
    "all any both each few more most other others some such only own same "
    "too very just also which what when where who whom whose why how "
    "one two three every everything something anything nothing per via etc "
    "run runs running work works working make makes making "
    "use used uses using new old need needs needed "
    "get gets getting set sets setting put puts "
    "add adds adding fix fixes fixing "
    # `word` is ordinary English that happens to be unique to ONE description
    # ("per-word timings", media-pipeline), which is all `discriminative()` asks.
    # Uniqueness in a 13-document corpus is a weak proxy for specificity, and
    # this is where the two came apart: `wording` folds to `word`, so "there is
    # no local way to check the changelog wording" was pushed back to the
    # narration agent. Raising the -ing fold floor instead was tried and is
    # WORSE -- the fold is load-bearing, `failing` -> `fail` -> stopword, and
    # blocking it let `failing` through as a term for e2e-local.
    "word words "
    # `touch` is in SEVEN of the twelve agent descriptions ("anything touching
    # TTS...", "before touching any translation", ...), so it discriminates
    # nothing -- and it fired a media-pipeline hint at a session whose message
    # merely said a file was "not touched". Same class as run/work/use/fix above.
    "touch touches touching touched"
)
STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def tokenize(text):
    """The term set of a string: {(kind, text)}, kind in {"path", "word"}.

    THE SAME function for descriptions and for haystacks, which is
    load-bearing rather than tidy: sharing it is what makes scoring a set
    intersection, and a set intersection is what makes the substring bug
    (`read` matching inside `README`) impossible instead of merely unlikely.
    """
    terms = set()
    if not text:
        return terms
    low = text.lower()
    for m in PATH_RE.finditer(low):
        tok = m.group(0).strip("./-_")
        if len(tok) >= PATH_MIN_LEN and ("/" in tok or "." in tok):
            terms.add(("path", tok))
    for m in WORD_RE.finditer(low):
        tok = m.group(0).strip("-_")
        # STOPWORDS BEFORE THE FOLD AS WELL AS DURING IT, and neither is
        # redundant. Before: the list enumerates surface forms (`running`,
        # `fixes`), and folding those first would hand `runn` and `fixe`
        # through as terms. During: `settings` is not in the list and folds to
        # `setting`, which is (_stem returns "" for both cases).
        if len(tok) < 3 or tok in STOPWORDS:
            continue
        tok = _stem(tok)
        if tok:
            terms.add(("word", tok))
    return terms


def _weight(term):
    return PATH_WEIGHT if term[0] == "path" else WORD_WEIGHT


# ---- the corpus -------------------------------------------------------------


def agents_dir():
    """Where the agent files live.

    `hook_repo_root()`, never `project_root()`: `.claude/agents` is a sibling
    of `.claude/hooks/stop`, and hook_repo_root is immune to cwd by
    construction. WORKLIST_AGENTS_DIR is the seam the suite and the CI gate
    point at fixtures, the same way WORKLIST_REPORTS_DIR is.
    """
    env = os.environ.get("WORKLIST_AGENTS_DIR")
    if env:
        return pathlib.Path(env)
    root = C.hook_repo_root()
    if root is None:
        # The hook file is somewhere unexpected (a copied fixture, a vendored
        # tree). Answer a path rather than None so every caller keeps one
        # shape; load_corpus reports the absent directory as an error.
        root = pathlib.Path(__file__).resolve().parents[3]
    return pathlib.Path(root) / ".claude" / "agents"


def _frontmatter(path):
    """({key: value}, error) for one agent file, reading the HEAD only.

    Stops at the closing `---`, so a 33 KB body is never read and a stray
    `---` inside prose can never be mistaken for the fence. Continuation
    lines fold into the previous key, so a wrapped `description:` survives.
    """
    fields, key, opened = {}, None, False
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if not opened:
                    if line.strip() == "---":
                        opened = True
                        continue
                    if line.strip():
                        return {}, "%s: no YAML frontmatter fence" % path.name
                    continue
                if line.strip() == "---":
                    return fields, ""
                m = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):[ \t]*(.*)$", line)
                if m:
                    key = m.group(1).strip().lower()
                    fields[key] = m.group(2).strip()
                elif key and line.strip():
                    fields[key] = (fields[key] + " " + line.strip()).strip()
    except OSError as exc:
        return {}, "%s: unreadable (%s)" % (path.name, exc)
    return {}, "%s: frontmatter is never closed" % path.name


def load_corpus(agents_dir_path):
    """({name: {"desc", "path", "terms"}}, [error]) for one directory.

    Errors are RETURNED, never raised and never swallowed: a file with no
    `name:` or no `description:` is an ERROR ENTRY, not a silent skip. A
    silent skip is how an agent stops being reachable while everything still
    looks healthy -- the exact failure this whole feature exists to end.
    """
    corpus, errors = {}, []
    d = pathlib.Path(agents_dir_path)
    try:
        files = sorted(d.glob("*.md"))
    except OSError as exc:
        return corpus, ["%s: cannot list agent directory (%s)" % (d, exc)]
    if not files:
        # NOT an error. An empty directory is a repo with no specialists, and
        # a note on every stop about that would be the wallpaper this design
        # refuses to become. The CI gate is what refuses to be vacuous.
        return corpus, errors
    for path in files:
        fields, err = _frontmatter(path)
        if err:
            errors.append(err)
            continue
        name = fields.get("name", "").strip()
        desc = fields.get("description", "").strip()
        if not name:
            errors.append("%s: frontmatter has no `name:`" % path.name)
            continue
        if not desc:
            errors.append("%s: frontmatter has no `description:` (it can never be matched)" % name)
            continue
        if name in corpus:
            errors.append("%s: two agent files claim the name (%s)" % (name, path.name))
            continue
        terms = {t: _weight(t) for t in tokenize(desc)}
        corpus[name] = {"desc": desc, "path": path, "terms": terms}
    return corpus, errors


def discriminative(corpus):
    """{name: {term: weight}} keeping ONLY terms unique to one description.

    With 7-8 documents this is a cheaper and sharper substitute for IDF, and
    it is what stops `config`, `session`, `gate` and `repo` -- words every
    description in this repo contains -- from ever triggering anything.

    The agent's OWN NAME is injected afterwards at weight 3 and is never
    subject to the filter, so "ask the i18n-guardian" matches even when the
    prose shares nothing else with that description.
    """
    seen = {}
    for entry in corpus.values():
        for term in entry["terms"]:
            seen[term] = seen.get(term, 0) + 1
    uniq = {}
    for name, entry in corpus.items():
        kept = {t: w for t, w in entry["terms"].items() if seen.get(t) == 1}
        kept[("word", name.lower())] = NAME_WEIGHT
        uniq[name] = kept
    return uniq


# ---- scoring ----------------------------------------------------------------


def score(haystack, uniq):
    """[(score, name, hits)] for EVERY agent, best first.

    Every agent is present, including the ones that scored zero, because the
    runner-up is what the margin is measured against and an absent runner-up
    would silently read as "no competition".
    """
    hay = tokenize(haystack)
    ranked = []
    for name, terms in uniq.items():
        hits = set(terms) & hay
        total = sum(terms[t] for t in hits)
        shown = [t[1] for t in sorted(hits, key=lambda t: (-terms[t], t[1]))]
        ranked.append((float(total), name, shown))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    return ranked


def best_hint(haystack, uniq, min_score=None, min_margin=None):
    """(name, score, hits), or None when the evidence does not distinguish one.

    TIES ARE SILENCE BY CONSTRUCTION: a tie makes the margin 0, which is below
    any positive threshold, so no tie-break rule exists to get wrong. Never
    break a tie by name order, corpus order or mtime -- a tie means the
    evidence does not distinguish two specialists, and inventing a winner is
    how a matcher starts lying.

    NEAR-MISSES ARE SILENCE TOO, and are deliberately not logged: "you almost
    matched X" is a hint with extra words. When a domain repeatedly scores just
    under threshold the fix is to sharpen that description, and the CI gate is
    what surfaces it.
    """
    if not uniq:
        return None
    floor = MIN_SCORE if min_score is None else float(min_score)
    margin = MIN_MARGIN if min_margin is None else float(min_margin)
    ranked = score(haystack, uniq)
    top_score, top_name, top_hits = ranked[0]
    runner = ranked[1][0] if len(ranked) > 1 else 0.0
    if top_score < floor or (top_score - runner) < margin:
        return None
    return (top_name, top_score, top_hits)


def hint_for(haystack, agents_dir_path=None):
    """((name, score, hits) or None, [error]) -- the whole flow, one call.

    The convenience the hook and the gate both use: load, discriminate, score,
    threshold. Kept here rather than in wl_checks so the gate exercises the
    same path the stop does instead of a re-implementation of it.
    """
    corpus, errors = load_corpus(agents_dir() if agents_dir_path is None else agents_dir_path)
    if not corpus:
        return None, errors
    return best_hint(haystack, discriminative(corpus)), errors


# =============================================================================
# THE PUSH-BACK: a session giving up on a domain a specialist already covers.
# =============================================================================
#
# WHY THIS EXISTS, and it is one specific failure rather than a theory.
# On 2026-08-16 a session wrote, about a red Ceph E2E job:
#
#     "It doesn't reproduce: neither local worker has /etc/ceph or rbd."
#
# and moved on. The answer was in the file it had just been reading.
# `ops-vms.md` says `VM_CEPH_NODES` is load-bearing, that a default `ops up`
# leaves the Ceph trio as bare OS images, and that bare VMs are NOT healed
# incrementally -- three lines below the passage the session quoted. An empty
# /etc/ceph was not evidence that local testing is impossible; it was the
# documented SYMPTOM of Ceph never having been provisioned, with the remedy
# printed underneath. The operator had to push back by hand, and was right.
#
# The existing hint (agent_hint_queue) could not have caught this: it is
# advisory, priority 3, allow-path only, and it fires on TOPIC alone. This
# session had already been shown the file. What it needed was not discovery,
# it was a challenge at the moment of abandonment.
#
# WHY THE CONJUNCTION IS THE WHOLE DESIGN. Firing on give-up language alone
# would be unbearable: "cannot", "not reproducible" and "pre-existing" are
# ordinary, frequently CORRECT things to write, and CLAUDE.md rule 3 does not
# forbid concluding impossibility -- it forbids concluding it WITHOUT PROBING.
# Firing on topic alone is the existing hint, which is already throttled to
# near-silence for good reason. Only the pair is worth interrupting for: a
# claim of impossibility about a domain where a written specialist names the
# exact command that would test the claim.
#
# GENERAL OVER THE DIRECTORY, never a hand-maintained list of domains. The
# corpus is the same one load_corpus() reads from disk on every call, so an
# agent added next month is covered the day its file lands, and a deleted one
# stops being cited immediately. That is the same reason wl_agents refuses to
# cache: a hand-kept table is exactly what goes stale without anyone noticing.
#
# WHAT IT DOES NOT DO. It does not judge whether the give-up was CORRECT --
# it cannot, and pretending otherwise would make it an oracle instead of a
# prompt. It asks for the probe. A session that has already run the probe
# answers in one line and moves on; that is the intended cost.

# Give-up markers, as whole-phrase regexes over the session's own last message.
# Grouped by the CLAIM each one makes, because the reply differs: an
# impossibility claim wants a probe, a dismissal claim wants ownership proof.
#
# Deliberately NOT included: "flaky", "timeout", "rate limit", "quota". Those
# name an observed condition rather than a decision to stop, and every one of
# them was a TRUE statement somewhere in the session that motivated this file.
_RX_IMPOSSIBLE = (
    r"\b(?:can(?:'|no|)?t\s+be\s+(?:done|tested|run|reproduced|verified|checked)"
    r"|not\s+possible|impossible\s+to|no\s+way\s+to)\b"
)
_RX_NO_REPRO = (
    r"\b(?:does(?:\s+not|n'?t)\s+reproduce"
    r"|can(?:'|no|)?t\s+reproduce"
    r"|not\s+reproducible"
    r"|(?:only|just)\s+(?:reproducible\s+)?in\s+CI"
    r"|CI[- ]only)\b"
)
_RX_NO_LOCAL = (
    r"\b(?:not\s+available\s+locally|no\s+local\s+(?:way|path|equivalent)"
    r"|cannot\s+(?:be\s+)?tested?\s+locally"
    r"|(?:would\s+)?requires?\s+infrastructure)\b"
)
_RX_DISMISSED = (
    r"\b(?:pre-?existing|environmental|not\s+(?:my|mine|this\s+wave'?s)"
    r"|out\s+of\s+scope\s+(?:here|for\s+this))\b"
)

# label -> regex. The label is PRINTED back at the session, so it must read as
# the thing being claimed rather than as a rule name.
_GIVEUP_PATTERNS = (
    ("impossible", _RX_IMPOSSIBLE),
    ("does-not-reproduce", _RX_NO_REPRO),
    ("no-local-path", _RX_NO_LOCAL),
    ("dismissed", _RX_DISMISSED),
)
_GIVEUP_RES = tuple((label, re.compile(rx, re.IGNORECASE)) for label, rx in _GIVEUP_PATTERNS)

# The push-back is a ONE-SHOT PER AGENT PER SESSION. Not a nag: the operator's
# own intervention was a single sentence, and a check that fires every stop
# until satisfied would be answered by writing around its regex rather than by
# running the probe. One challenge, then it is the session's call and the
# record shows what it chose.
PUSHBACK_ENABLED = os.environ.get("WORKLIST_AGENT_PUSHBACK", "on").strip().lower() not in (
    "off",
    "0",
    "false",
    "no",
)
# Lower than the hint's floor ON PURPOSE. The hint competes with every other
# advisory for one slot and must be near-certain to be worth a line; this one
# only ever speaks when the session has ALSO just claimed something is
# impossible, and that conjunction carries most of the precision. Requiring the
# hint's full confidence on top would silence it in exactly the case that
# motivated it -- "neither local worker has /etc/ceph" is a thin haystack.
PUSHBACK_MIN_SCORE = float(os.environ.get("WORKLIST_AGENT_PUSHBACK_MIN_SCORE", "1"))
PUSHBACK_MIN_MARGIN = float(os.environ.get("WORKLIST_AGENT_PUSHBACK_MIN_MARGIN", "0.5"))


# A MENTION IS NOT A CLAIM, and this is a live regression rather than a
# precaution: the first message written after this check shipped was a summary
# OF THE CHECK, quoting its own trigger phrases -- `"cannot"`, `"not
# reproducible"`, and the ops-vms sentence verbatim -- and the check duly
# accused its author of giving up on pr-babysitter. A session that writes ABOUT
# surrender is not surrendering, exactly as a doc that explains a retired
# command is not teaching it.
#
# Same shape and same remedy as `loop_finished_declared` (wl_checks.py:667),
# which strips quoted and backticked spans before reading a declaration. Fenced
# blocks go too: quoting a transcript must never be readable as speech.
# NEWLINES ALLOWED INSIDE A QUOTE, bounded rather than greedy: the message that
# exposed this wrapped its quotations across lines, so a `[^"\n]*` rule saw no
# quotation at all and the fix silently did nothing. The 400-char bound is what
# keeps an UNBALANCED quote from blanking the rest of the document.
#
# NO SINGLE-QUOTE RULE, deliberately. An apostrophe is not a quote mark, and
# "doesn't ... don't" would pair across a real claim and blank it -- turning a
# false positive into a false negative, which is strictly worse: this check is
# only worth having if it still fires on the sentence that motivated it.
_QUOTED_RE = re.compile(
    r"```.*?```|`[^`]*`|\"[^\"]{0,400}\"|\u201c[^\u201d]{0,400}\u201d",
    re.DOTALL,
)


def unquoted(text):
    """`text` with every quoted, backticked and fenced span blanked out.

    Blanked to a SPACE rather than removed, so two words either side of a quote
    cannot fuse into a third that matches something neither of them did.
    """
    return _QUOTED_RE.sub(" ", text or "")


# `.!?` only. A COLON IS NOT A BOUNDARY HERE and that is a live regression:
# "It doesn't reproduce: neither local worker has /etc/ceph" splits at the
# colon into a claim with no subject, and the check went silent on the exact
# sentence it was built from. A colon introduces the EVIDENCE for a claim,
# which is the half that names the domain.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _claim_sentences(text):
    """Every sentence carrying a give-up claim, already unquoted by the caller.

    Split on newlines too, not just terminators: the give-up line in a bulleted
    status list frequently has no full stop at all, and treating the whole list
    as one sentence would re-admit every unrelated bullet as evidence.
    """
    return [
        sent
        for sent in _SENT_SPLIT_RE.split(text or "")
        if any(rx.search(sent) for _label, rx in _GIVEUP_RES)
    ]


def giveup_claims(text):
    """Labels of every give-up claim in `text`, in the order they are defined.

    Returns [] for the overwhelmingly common case, so the caller can bail
    before touching the corpus at all. Deduplicated: three phrasings of the
    same surrender are one claim, and printing all three would read as three
    separate accusations.
    """
    if not text:
        return []
    # BOTH this and pushback_for's own unquote() are load-bearing, and the
    # redundancy is deliberate rather than an oversight. Mutation-tested: with
    # either one removed the rule still holds and the gate stays green; only
    # removing BOTH lets a quoted mention be read as a claim, at which point
    # the gate goes red naming the sentence. Do not "simplify" one away on the
    # grounds that the tests still pass -- that is exactly what they would do.
    text = unquoted(text)
    found = []
    for label, rx in _GIVEUP_RES:
        if rx.search(text) and label not in found:
            found.append(label)
    return found


def pushback_for(haystack, agents_dir_path=None):
    """((agent, hits, claims) or None, [error]) -- the conjunction, one call.

    ORDER MATTERS FOR COST, not just for reading: the give-up scan is a handful
    of regexes over one message and answers "no" on nearly every stop, so it
    runs BEFORE the corpus is loaded. On a normal stop this function does not
    touch the disk.
    """
    if not PUSHBACK_ENABLED:
        return None, []
    claims = giveup_claims(haystack)
    if not claims:
        return None, []
    corpus, errors = load_corpus(agents_dir() if agents_dir_path is None else agents_dir_path)
    if not corpus:
        return None, errors
    # SCORE THE SENTENCE THAT MAKES THE CLAIM, NOT THE WHOLE MESSAGE.
    #
    # MEASURED, and it overturned the threshold I first reached for. Scoring the
    # whole message gave a GENERIC report ("It doesn't reproduce and this is
    # pre-existing. Remaining: the wave, console review, commit and check.")
    # a score of 5.0 against pr-babysitter, while the real ceph sentence scored
    # 4.0 against ops-vms. The false positive outranked the true one, so no
    # threshold could separate them -- raising the floor silences the case this
    # check exists for and leaves the noise. That is why there is no
    # push-back-specific stopword list here either: `check`, `commit`, `console`
    # and `review` are legitimately discriminative for pr-babysitter, and
    # banning them would break the agent they legitimately name.
    #
    # A claim is ABOUT something, and that something is in the sentence with it.
    # Restricting the haystack to the claim's own sentences encodes exactly that
    # and needs no list to maintain.
    claim_text = " ".join(_claim_sentences(unquoted(haystack)))
    if not claim_text.strip():
        return None, errors
    # SCORE THE SUBJECT, NOT THE SURRENDER. The give-up phrases are cut out of
    # the haystack before the topic match, and this is a defect the gate's own
    # negative control caught rather than a precaution: `cannot` is a
    # discriminative term in at least one agent description, so
    # "This cannot be done without a token" matched e2e-local ON THE WORD
    # `cannot` alone. That would have made every honest impossibility claim an
    # accusation, pointed at a random specialist -- the precise failure this
    # check exists to avoid, shipped inside the check itself.
    subject = claim_text
    for _label, _rx in _GIVEUP_RES:
        subject = _rx.sub(" ", subject)
    hit = best_hint(
        subject,
        discriminative(corpus),
        min_score=PUSHBACK_MIN_SCORE,
        min_margin=PUSHBACK_MIN_MARGIN,
    )
    if not hit:
        return None, errors
    name, _score, hits = hit
    return (name, hits, claims), errors
