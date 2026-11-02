"""check:ci-region-consistency: the seven account targets (stable and edge in eu, us, asia, plus bench) are one shape.

The entry point is .ci/scripts/quality/check_region_consistency.py. This module only dispatches: the offline checks and the target model are in `region_consistency_offline`, the Cloudflare half (`--live`) in `region_consistency_live`, and the planted controls (`--selftest`) in `region_consistency_controls`. Read the offline module's docstring for what each class means.

Usage: [--root DIR] [--live] | --selftest. Exit 0 consistent, 1 drift, 2 no verdict (an unreadable input, or with --live a listing that could not be read).
"""

from __future__ import annotations

import json
import pathlib
import sys
import tomllib

from rediacc_ci import paths
from rediacc_ci.quality import region_consistency_controls as controls
from rediacc_ci.quality import region_consistency_live as live_layer
from rediacc_ci.quality import region_consistency_offline as core


def main(argv: list[str]) -> int:
    args = list(argv)
    if "--selftest" in args:
        return controls.run()
    root = paths.repo_root()
    if "--root" in args:
        i = args.index("--root")
        root = pathlib.Path(args[i + 1])
        del args[i : i + 2]
    live = "--live" in args
    unknown = [a for a in args if a != "--live"]
    if unknown:
        print(
            "%s: unknown argument(s) %s; usage: [--root DIR] [--live] | --selftest"
            % (core.SELF, " ".join(unknown)),
            file=sys.stderr,
        )
        return 2
    try:
        inputs, targets, found = core.load(root)
        findings = core.offline(inputs, targets, found)
    except (core.NoVerdictError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        print("%s: NO VERDICT: %s" % (core.SELF, exc), file=sys.stderr)
        return 2
    classes: tuple[str, ...] = core.CLASSES
    unchecked: list[tuple[str, str | None, str]] = []
    if live:
        live_findings, unchecked, live_classes = live_layer.run(targets, inputs)
        findings += live_findings
        classes = core.CLASSES + live_classes
    for (tid, field), why in sorted(core.SHAPE_EXCEPTIONS.items()):
        print("%s: exempt %s %s: %s" % (core.SELF, tid, field, why))
    for line in core.report(targets, findings, classes, unchecked):
        print(line)
    shape = (
        "%d target(s), %d account + %d proxy toml(s), %d profile(s), %d bench payload key(s)"
        % (
            len(targets),
            len(inputs.account),
            len(inputs.proxy),
            len(targets),
            len(inputs.bench_payload),
        )
    )
    if unchecked:
        for cls, where, why in unchecked:
            print(
                "%s: UNCHECKED %s (%s): %s" % (core.SELF, cls, where or "every target", why),
                file=sys.stderr,
            )
    if findings:
        print(
            "%s: %d drift finding(s) over %s:" % (core.SELF, len(findings), shape), file=sys.stderr
        )
        for f in findings:
            print(f.line(), file=sys.stderr)
        print(
            "  Fix the declaration that disagrees with the other targets. Do not add an exemption to quiet one.",
            file=sys.stderr,
        )
        return 1
    if unchecked:
        print(
            "%s: NO VERDICT: %d live check(s) could not run; unknown is not consistent"
            % (core.SELF, len(unchecked)),
            file=sys.stderr,
        )
        return 2
    print(
        "%s: consistent: %s%s"
        % (
            core.SELF,
            shape,
            ", live layer included" if live else " (core.offline only; --live adds Cloudflare)",
        )
    )
    return 0
