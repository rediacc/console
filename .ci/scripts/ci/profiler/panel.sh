#!/bin/bash
# Turn a sampler TSV into the job's summary panel, and decide whether a
# degenerate profile is a warning or a failure.
#
# WHY A SEPARATE SCRIPT: the JS action's post hook must stay tiny and
# dependency-free, and the aggregation has to be runnable by hand against a
# saved TSV when someone is arguing about a runner choice. Everything policy-
# shaped lives here; index.js only starts and stops a process.
#
# PANEL PLACEMENT: a summary panel's title is the JOB's `name:`, and every step
# summary in a job CONCATENATES into that one panel. So this appends a section
# to the job's own panel; it cannot open a separately-titled one from inside a
# job. Limits are 1 MiB per step summary (overflow = failed upload plus an error
# annotation) and 20 step summaries displayed per job, so the panel is size-
# checked here rather than discovered broken in the UI.
#
# STRICT: findings from report.awk are real defects (nothing sampled, a flat
# zero series, a host leak). Because `continue-on-error` is banned repo-wide,
# the failure is gated on PROFILER_STRICT instead: false emits ::warning::
# annotations and still writes the panel, true exits non-zero. Strict flips to
# true once the profiler has run clean across the job matrix; until then a
# profiler bug must not turn CI red.
#
# Usage:
#   .ci/scripts/ci/profiler/panel.sh
#
# Required env:
#   PROFILER_SAMPLE_FILE  TSV written by sampler-linux.sh
#
# Optional env:
#   PROFILER_STRICT       'true' to exit non-zero on findings (default false)
#   PROFILER_WALL_S       elapsed seconds measured by the action (authoritative)
#   PROFILER_TITLE        heading suffix, normally the job name
#   PROFILER_NOTE         one-line note from the action (e.g. "sampler died")
#   PROFILER_DECLARED_S   the job's own declared timeout in seconds; forwarded
#                         to report.awk, which otherwise assumes 840 (14 min)
#   PROFILER_HARD_S       the platform hard cap in seconds; report.awk assumes
#                         900 (slim). Both are passed ONLY when non-empty, so an
#                         unset variable keeps the aggregator's own default
#                         rather than overwriting it with an empty string.
#   GITHUB_JOB            the job id the machine row is keyed by (set by GitHub)
#   GITHUB_STEP_SUMMARY   panel to append to; stdout when unset
#
# THE MACHINE ROW. Besides the human panel this emits exactly one `::notice`
# carrying the advisory text and a single-line, machine-parseable row of the
# numbers behind it. That annotation is the ONLY durable artifact of a profile:
# a step summary cannot be read back through the API, while annotations can,
# which is how .ci/scripts/quality/check_runner_advice.py --refresh harvests a
# sizing baseline from real runs instead of from hand-entered numbers.
#
# Run locally:
#   PROFILER_SAMPLE_FILE=/tmp/p.tsv .ci/scripts/ci/profiler/panel.sh
#
# Exit: 0 clean or non-strict, 1 findings under strict, 2 usage error.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_AWK="$SCRIPT_DIR/report.awk"

SAMPLE_FILE="${PROFILER_SAMPLE_FILE:-}"
STRICT="${PROFILER_STRICT:-false}"
WALL_S="${PROFILER_WALL_S:-0}"
TITLE="${PROFILER_TITLE:-}"
NOTE="${PROFILER_NOTE:-}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"

# 1 MiB is a hard platform limit and the failure mode is an unhelpful upload
# error, so the panel is trimmed well short of it.
MAX_PANEL_BYTES="${PROFILER_MAX_PANEL_BYTES:-900000}"

if [ -z "$SAMPLE_FILE" ]; then
    echo "panel.sh: PROFILER_SAMPLE_FILE must be set" >&2
    exit 2
fi
if [ ! -r "$REPORT_AWK" ]; then
    echo "panel.sh: missing aggregator: $REPORT_AWK" >&2
    exit 2
fi

emit_finding_annotations() {
    local file="$1" line
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        if [ "$STRICT" = "true" ]; then
            echo "::error::profiler: $line"
        else
            echo "::warning::profiler: $line"
        fi
    done <"$file"
}

# The sampler never ran, or its output vanished. Say that in the panel: a
# missing profile and a zero profile look identical in a log and mean opposite
# things.
if [ ! -s "$SAMPLE_FILE" ]; then
    {
        echo ""
        echo "## Runner Profile${TITLE:+: $TITLE}"
        echo ""
        echo "**Samples:** none - no sample file was produced."
        echo "**Reason:** ${NOTE:-the sampler did not start, or wrote nothing before the job ended}"
        echo ""
        echo "> No profile was collected. Nothing about this job's CPU or memory"
        echo "> footprint can be concluded from this run."
        echo ""
    } >>"$SUMMARY"
    if [ "$STRICT" = "true" ]; then
        echo "::error::profiler: no sample file at $SAMPLE_FILE (${NOTE:-sampler produced nothing})"
        exit 1
    fi
    echo "::warning::profiler: no sample file at $SAMPLE_FILE (${NOTE:-sampler produced nothing})"
    exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PANEL="$WORK/panel.md"
FINDINGS="$WORK/findings.txt"
MACHINE="$WORK/machine.txt"
: >"$FINDINGS"

# A workflow command's message is line-oriented and `%` starts an escape, so
# both must be encoded or the annotation is silently truncated at the newline.
escape_workflow_command() {
    local s="$1"
    s="${s//%/%25}"
    s="${s//$'\r'/%0D}"
    s="${s//$'\n'/%0A}"
    printf '%s' "$s"
}

AWK_ARGS=(-v wall_s="$WALL_S" -v findings_file="$FINDINGS" -v title="$TITLE"
    -v machine_file="$MACHINE" -v job="${GITHUB_JOB:-}")
# Passing `-v declared_s=` would set it to the empty string, which report.awk
# reads as "unset" and replaces with its default anyway -- but relying on that
# would make the defaults live in two places. Pass the flag only when there is
# a value to pass.
if [ -n "${PROFILER_DECLARED_S:-}" ]; then
    AWK_ARGS+=(-v declared_s="$PROFILER_DECLARED_S")
fi
if [ -n "${PROFILER_HARD_S:-}" ]; then
    AWK_ARGS+=(-v hard_s="$PROFILER_HARD_S")
fi

RC=0
awk "${AWK_ARGS[@]}" -f "$REPORT_AWK" "$SAMPLE_FILE" >"$PANEL" || RC=$?
if [ "$RC" -gt 1 ]; then
    echo "panel.sh: aggregator failed with exit $RC" >&2
    exit 2
fi

SIZE="$(wc -c <"$PANEL")"
if [ "$SIZE" -gt "$MAX_PANEL_BYTES" ]; then
    head -c "$MAX_PANEL_BYTES" "$PANEL" >"$PANEL.trimmed"
    {
        echo ""
        echo "**Panel trimmed:** ${SIZE} bytes exceeded the ${MAX_PANEL_BYTES}-byte budget (platform limit is 1 MiB per step summary)."
    } >>"$PANEL.trimmed"
    mv "$PANEL.trimmed" "$PANEL"
fi

if [ -n "$NOTE" ]; then
    echo "**Note:** $NOTE" >>"$PANEL"
    echo "" >>"$PANEL"
fi

cat "$PANEL" >>"$SUMMARY"

# Exactly ONE notice per job. report.awk writes the row only when it produced a
# verdict, so a run it refused to advise on emits no annotation at all rather
# than an unusable one -- and the harvester never has to decide whether a row
# it can see is one it should believe.
if [ -s "$MACHINE" ]; then
    ADVISORY="$(sed -n 's/^\*\*Advisory:\*\* //p' "$PANEL" | head -n 1)"
    # The advisory is read back out of the panel, and the panel can have been
    # trimmed above. Say so rather than emitting a notice that opens with
    # nothing; the row after it is the part a machine reads either way.
    ADVISORY="${ADVISORY:-(advisory text unavailable: the panel was trimmed)}"
    ROW="$(head -n 1 "$MACHINE")"
    echo "::notice title=Runner sizing (profiler)::$(escape_workflow_command "$ADVISORY") | $(escape_workflow_command "$ROW")"
fi

if [ -s "$FINDINGS" ]; then
    emit_finding_annotations "$FINDINGS"
    if [ "$STRICT" = "true" ]; then
        exit 1
    fi
fi
exit 0
