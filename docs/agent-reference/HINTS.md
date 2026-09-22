# Behavioral hints

A rotating one-line reminder the Stop hook appends to an ordinary allow-path stop, drawn at random from this corpus. Every entry restates a rule or incident already documented elsewhere in this repo; the file's job is resurfacing an existing rule at the moment it is needed, not originating one. An entry with no grounding is not eligible for display -- see `Source:` below.

This is a reminder mechanism, not an enforcement mechanism. A session that reads a displayed hint and does not act on it has not violated anything the Stop hook can detect, and no code path may ever check whether a hint's advice was followed: the evidence for that does not exist in any artifact the hook reads, and a check built on the subject's own account of its behavior is
satisfied by writing the right sentence.

Boundary with `docs/agent-reference/TRAPS.md`: TRAPS.md is what a session did not know; this file is what a session knew and did not do. If an entry describes a way a session gets fooled, it belongs in TRAPS.md, and a hint here may cite it with `trap:<id>`.

### Entry schema

    ## <the hint itself, one imperative sentence, <= 160 chars>
    Hint-Id: <stable-kebab-case>
    Source: <pointer>[, <pointer>...]
    Status: active | retired

    <optional body paragraph: the incident or rule that paid for this hint, for
    the human reader only. The hook never displays a body.>

The `## ` heading is the displayed text, so it must stand alone as a complete reminder. `Source:` pointers use the grammar `wl_planrec.resolve` already implements: `file:<path>[:<line>]`, `trap:<Trap-Id>`, `gate:<npm id>`, `plan:<slug>`. Only `Status: active` entries are eligible for display; a retired entry stays in the file with its history intact rather than being deleted. A
`Hint-Id` is never renumbered and never reused after retirement.

## An order given in conversation is not tracked until it is in the store; worklist.py --add is what survives a restart and a compaction
Hint-Id: record-the-order
Source: file:CLAUDE.md:53, file:CLAUDE.md:59
Status: active

CLAUDE.md's own worklist section states the store is per-repo and per-session, and that the Stop hook refuses to end a turn while a tracked item stays open. An instruction that lives only in the transcript does not survive a compaction; the verb table beginning at `CLAUDE.md:59` is the whole interface.

## Derived, mechanical work with a pre-existing oracle and a loud failure goes to a Haiku sub-agent, not inline
Hint-Id: haiku-for-derived-work
Source: file:CLAUDE.md:135, file:docs/agent-reference/model-routing.md:1
Status: active

The model-routing rule is by task shape, never by language or domain: a port, a translation, a mechanical sweep or a read-only survey where a pre-existing oracle (a shadow ledger, a golden differential, a gate that already reds) decides correctness, and being wrong is loud rather than a silent gap.

## A question that means sweeping several files or packages goes to read-only Explore agents, several at once, asking for file:line evidence rather than file dumps
Hint-Id: investigate-with-fan-out
Source: file:CLAUDE.md:126
Status: active

Reading and thinking parallelize well; writing does not. Read-only fan-out is cheap, and this kind of dispatch defaults to Haiku since the tree already holds the answer and a citation that does not resolve is caught on sight.

## Before calling a bug fixed, grep for its siblings; one bad call site usually has several
Hint-Id: sweep-the-class
Source: file:CLAUDE.md:44, file:.claude/hooks/stop/wl_classsweep.py:1
Status: active

A fix that only shows its own instance fixed, with no evidence the same defect was searched for elsewhere, is exactly what the Stop hook's own class-sweep judge asks about on every fix-shaped commit or worklist tick.

## A clean result is not evidence until the check has been made to go red on known-bad input through the same path
Hint-Id: control-before-green
Source: trap:check-cannot-fail
Status: active

A check that has never been observed failing has not been observed at all; it could pass on anything. This is the single most common way a session gets fooled into trusting an instrument that cannot actually fail.

## "Cannot be done here" is a claim, so run the command that would refute it before making it
Hint-Id: probe-the-impossible
Source: file:CLAUDE.md:119
Status: active

Closing an item as impossible without running the command that proves it is how work gets abandoned while sounding diligent. A capability reported as missing infrastructure was one command away from confirming the opposite.

## The commit log is evidence, and it is the evidence nobody reads; git log on the file in hand usually answers the question already
Hint-Id: read-the-history
Source: trap:read-the-history-before-you-guess <!-- style-ok -->
Status: active

A question about why code looks the way it does, or whether a pattern has broken before, is frequently already answered in the history of the exact file, at the cost of one command nobody thought to run first.

## Read stdout and stderr separately, and never redirect stderr to /dev/null; a swallowed stream is where the answer was
Hint-Id: stderr-separately
Source: trap:read-stdout-and-stderr-separately
Status: active

Output, exit-code and error-path defects are invisible to code reading and to mocked tests. A wrapper that swallows output, or progress text landing on the wrong stream, only shows up in the raw bytes of both streams read on their own.

## Before creating a new file, gate, doc or provider, search the tree for one that already exists under another name
Hint-Id: search-before-creating
Source: file:CLAUDE.md:161
Status: active

Several campaign boxes closed by finding the work already landed and only the record was stale, not by doing it again. The search costs one command; a duplicate mechanism costs a second one to reconcile later.

## A sub-agent's report is accurate about intent and quietly wrong about placement; check the artifact, not the summary of it
Hint-Id: check-the-artifact
Source: file:CLAUDE.md:133, trap:ruling-from-an-artifact-is-a-hypothesis
Status: active

Spot-check every agent's output against the artifact, verifying structure across the whole file set it touched, not just the keys or symbols it claimed to change.

## The Remaining section lists what cannot be done right now; "blocked on: nothing" is a confession that the turn ended with work in hand
Hint-Id: remaining-is-not-a-todo
Source: file:CLAUDE.md:87
Status: active

A line belongs there only when it is a genuine operator deferral, a lease to a verifiably live worker, a wait on a specific external run, or a last-resort issue with its door named. Nothing else may appear, and a "next up" or "ready to start" line is a sign the turn is stopping with work still available.

## A lesson this session paid for that is not in this corpus can be proposed with worklist.py --hint-propose
Hint-Id: propose-a-hint
Source: file:docs/agent-reference/HINTS.md:1
Status: active

This is the sole advertisement of the proposal channel: proposals land in an append-only ledger and are promoted into this file only by a reviewed edit, never automatically. Removing this entry silently kills the channel's only way of reaching a session at the moment a lesson is fresh.
