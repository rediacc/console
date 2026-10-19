#!/usr/bin/env python3
"""Entry point for the aws resolver gate.

The rules and the controls live in `rediacc_ci.quality.aws_resolver`; this file exists so the registry can invoke it BY PATH, the same split `check_backup_credential_isolation.py` uses. The `---- gate ----` header is HERE and not on the module, because `gate-bind` reads the file package.json names.

---- gate ----
step: aws resolver
lane: quality-static
why: every R2 read and write runs the aws CLI, and until 2026-10-19 each of
     twenty-three modules exec'd a bare "aws" after its own presence check, so
     the version that wrote production R2 was whatever the runner carried.
     rediacc_ci.core.awscli resolves AWS_BIN, PATH, then the pinned install;
     this keeps a new call site, a require_cmd("aws") or a bare `aws s3` in a
     workflow or .ci shell script from walking around it.
---- end gate ----
"""

import sys

import _cipath
from rediacc_ci.quality import aws_resolver

if __name__ == "__main__":
    raise SystemExit(aws_resolver.main(sys.argv[1:]))
