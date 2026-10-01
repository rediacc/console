#!/usr/bin/env python3
"""Entry point for the ported Linux runner sampler.

The logic lives in `rediacc_ci.ci.profiler_sampler_linux`; this file is the path the profiler action and the probe workflow spawn, so a `python3` call needs no `PYTHONPATH`.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.ci import profiler_sampler_linux

if __name__ == "__main__":
    raise SystemExit(profiler_sampler_linux.main(sys.argv[1:]))
