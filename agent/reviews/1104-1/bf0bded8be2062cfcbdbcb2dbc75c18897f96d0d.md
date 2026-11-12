# Review bf0bded8: feat(ci): onprem lab helpers, an air-gap for ops VMs and a throwaway CA

Commit: bf0bded8be2062cfcbdbcb2dbc75c18897f96d0d
Repo: console
Branch: 1104-1
Parent: bba72d908dc41473df7072f5a37d3a651eab59d7
Patch-Id: f0b2ee5b04e54a03319157f3f1e640654087f00e
Reviewed-At: 2026-11-12T13:15:23Z
Model: claude-haiku-5-5
Cost: $0.0100 USD, 1 call(s), 66.4s
Diff: 20788 bytes, 6 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature,ci why=Adds CI lab tooling (air-gap helper, test CA) with no user-facing product change.
Dropped: 0
Body-Sig: 7b3fc5309dd64eb0

## Findings

### bf0bded8.1 [medium] .ci/rediacc_ci/onprem/airgap.py:46
Anchor: in-diff
Claim: is_ops_vm_ip accepts any 192.168.111.x, including .254, which the module docstring names as the host gateway; `apply --vm 192.168.111.254` would set OUTPUT DROP on the host, contrary to the docstring's 'no other machine may be cut off by this tool'. No test covers .254 or the .0/.255 edges.
Class: other
Resolution: open

### bf0bded8.2 [low] .ci/rediacc_ci/onprem/testca.py:63
Anchor: in-diff
Claim: san_entry refuses wildcards, whitespace and ',;=' but not '/', so a host such as 'a/../x' is joined into the output path for the key and cert unchecked; the write goes to the operator-chosen directory tree, not a checked filename.
Class: other
Resolution: open

### bf0bded8.3 [low] .ci/rediacc_ci/onprem/testca.py:107
Anchor: in-diff
Claim: The openssl-failure branch of main (CalledProcessError/FileNotFoundError -> exit 1) is new behaviour with no test; test_onprem_airgap.py only exercises the success and wildcard-refusal paths.
Class: missing-control-test
Resolution: open

### bf0bded8.4 [low] .ci/rediacc_ci/tests/test_onprem_airgap.py:41
Anchor: in-diff
Claim: The remove verb is covered only by a substring assertion on remove_script(); no test sends `remove` through the transport or checks that it deletes the tagged rules, so a broken remove path would still pass the suite.
Class: missing-control-test
Resolution: open
