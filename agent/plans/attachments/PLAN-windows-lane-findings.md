<!-- Attachment of agent/plans/PLAN-windows-lane.md. Source: console-6c's Windows test night 2026-11-26/27 on the win11-spike VM (/var/lib/libvirt/images/win11-spike/FINDINGS.md, copied 2026-11-27). Every finding was reproduced on real Windows 11 26H2; statuses are as of the copy. -->

# rdc on Windows 11: findings ledger (night of 2026-11-26/27)

**Headline:** by 02:06 a Windows 11 host provisions a working rdc ops cluster (`rdc ops up --basic --backend hyperv`) from zero with no manual steps, after 13 ops-path fixes found and verified tonight. Released stable 3.0.1 still has the Windows host-key bug (fixed on 1121-1, release needs operator go-ahead).

Tester: console-6c (win11-spike VM). Implementer/planner: drain-promoted-plans-writers (console d778be9d, branch 1121-1, local, not pushed).
Every finding was reproduced on a real Windows 11 Enterprise Eval 26H2 (26300.9457) VM, nested on the KVM host. Bundles were built from the main checkout and are named by sha256 in the batch messages. "Verified" means rerun on Windows after the fix landed.

## Status by area

### Host keys / SSH client
| ID | Finding | Status |
|----|---------|--------|
| keyscan | Windows' bundled ssh-keyscan (OpenSSH_for_Windows 9.5p2/LibreSSL) returns 0 keys from OpenSSH 9.6+ (sntrup761 KEX); rdc swallowed the error → `scan-keys` fails, `vscode connect` "no host key in vault". **Released stable 3.0.1 is affected** | Fixed dd79642d (ssh2 scan), verified; release needs operator go-ahead |
| exit | `scan-keys` exited 0 on failure | Fixed 4e9005d4, verified (exit 6) |
| envelope | JSON `success:true` with exit 6 | Fixed (28 sites reordered), verified |
| W1 | ssh-agent: `ssh-agent -s` can't work on Windows (it's a service, disabled by default) → 10 s timeout per term/vscode command | Fixed 9f6bb01e, verified (6.3 s, no warning) |
| W2 | Windows ssh-agent persists added keys in HKCU (DPAPI) forever | Fixed (no agent use on win32, temp key files with -i), verified |
| W6 | term 6.0 s on Windows vs 3.9 s on Linux | Profiled: no single culprit (VM vCPU, uncached `where renet`); renet path cache added |

### VS Code
| ID | Finding | Status |
|----|---------|--------|
| DEP0190 | code.cmd launched with shell:true | Fixed, verified |
| vscode | `rdc vscode connect` works end to end on Windows (settings.json, config_rediacc, Remote-SSH) | Verified |

### Sync / rsync / MSYS2
| ID | Finding | Status |
|----|---------|--------|
| sftp | No rsync → SFTP fallback works, unicode + spaces roundtrip | Works |
| W3 | Broken MSYS2 rsync (partial pacman upgrade, 0xC0000135) → "Upload failed", no reason, no fallback | Fixed (probe + SFTP fallback + exit/stderr), verified |
| W4 | `sync status` missed local-only files | Fixed, verified |
| W5 | --mirror didn't report deletes; SFTP --mirror silently skipped deletes | Fixed (count; SFTP refuses), verified |
| P1 | `rdc tools install rsync` (pinned MSYS2 packages, sha256) | Landed, verified |
| B1/B2 | tools rsync rejected by probe (exits -1); `tools list` omitted it | Fixed, verified |
| B4 | tools rsync: empty etc/ → no cygdrive "/" → `/c/...` paths fail | Fixed (etc/fstab + nsswitch), verified |

### doctor / ops check / ops setup
| ID | Finding | Status |
|----|---------|--------|
| P2 | doctor on Windows: wrong rsync hint, no VS Code/OpenSSH/agent rows, dev noise | Fixed, verified |
| B3 | DPAPI probe flaky under load + Linux keyctl hint on Windows | Fixed, verified |
| O1 | `ops setup`: winget without --source → msstore cert error → exit 1 but "Prerequisites installed successfully" | Fixed d859b2f8, verified: QEMU removed → setup installs it (hash verified, 135 s); nit: already-installed prints "Warning: exit status 0x8a15002b" |
| O2 | QEMU installer doesn't add PATH; ops check said not found | Fixed (probe Program Files; hint → rdc ops setup), verified |

### rdc ops on Windows (Hyper-V, nested in KVM)
| ID | Finding | Status |
|----|---------|--------|
| nested | Hyper-V runs nested in the KVM guest (host-passthrough, kvm_intel nested=Y) | Works |
| O3 | `ops up --debug` forwarded to renet → "unknown flag" | Fixed, verified |
| O5 | Hyper-V driver used "localhost" → ::1 first on Windows, WinNAT is IPv4-only → SSH never ready | Fixed 5a5eff62 (127.0.0.1), verified without workaround |
| O6 | renet's Hyper-V NAT = 192.168.111.0/24 = the KVM fleet subnet → route clash on a Windows host that is also a fleet client | Design rule in PLAN-windows-lane (own VM_NET_BASE, explicit exemption list keyed on VM addresses, report existing Get-NetNat) |
| O7 | Key distribution exec'd ssh-copy-id (absent on Windows; Git's script isn't exec-able by Go) | Fixed fdd716b7 |
| O7b/c | New key install piped the key via stdin → Win32 ssh.exe hangs; no timeout | Fixed 1f7250c7 (base64 in cmd, -n, 2 min deadline), verified (mesh in 3 s) |
| O8 | `ops ssh` passed "127.0.0.1:22211" as hostname; VMInfo had no port | Fixed 562bdb8c + CLI, verified |
| down | `rdc ops down --backend hyperv`: VMs, NAT mappings and per-VM disks removed; NAT network, switch and base image kept (130 s). Nit: also tries VMs 12/21/22/23 that a --basic fleet never created | Works (nit open) |
| O9 | Worker/bridge copied renet.exe to Linux VMs | Fixed cd05116a (sibling renet-linux-<arch> / RENET_LINUX_BINARY), verified |
| O10 | Remote Linux paths built with filepath → `\usr\lib\...` in remote bash | Fixed (lease d66a4ebc, path.Dir + quoting), verified on both VMs |
| O11 | Win32 ssh.exe spawned by Go os/exec stalls: pipes hang on ANY remote output; regular files hang once ~96 KB is in flight (also with O_APPEND, separate files, no reader); NUL and PowerShell Start-Process -RedirectStandardOutput complete. `renet setup` output exceeds 96 KB → [4/4] hangs. Repro: tests/sshgo-repro | -n/BatchMode/deadlines + file capture landed (helps small outputs only); real fix needed: in-process x/crypto/ssh (or a .NET-style redirect launcher) |
| O11e | In-process x/crypto/ssh + sftp on Windows (ssh.exe off the ops path) | Landed bb806837..c6bea0a7, verified to [3/4] from zero (mesh 13 s) |
| O12 | worker renetMissing recognizes only *exec.ExitError; in-process returns *sshexec.ExitError → "exit status 1" on fresh VMs is fatal | Fixed (sshexec.ExitCode), verified |
| O13 | Hyper-V New-VM leaves Dynamic Memory on (min 512 MB) → VMs balloon to ~600 MB → `renet setup` "insufficient memory … for LUKS"; also VM_RAM was ignored | Fixed 20108cba, verified (static RAM, nested boot ~47 s/VM) |
| **FULL** | **`rdc ops up --basic --backend hyperv` on Windows FROM ZERO, no hand steps (02:06): 2 Hyper-V VMs, mesh, worker setup + CRIU, bridge Docker + registry, exit 0 in 461 s; cluster verified (ops status/ssh, registry 200 from worker)** | **PASS** |
| O11c | File capture with stdout+stderr on one file: streams overwrite each other (lost "out") | Reported |

### term
| ID | Finding | Status |
|----|---------|--------|
| term | Inline `term connect` to the fleet and the hostinger fork | Works |
| T1 | --external used the remote repo path as the local cwd → ENOENT → silent inline fallback | Fixed, verified (window opens) |
| T2 | Mismatch hint suggested `scan-keys <IP>` | Fixed, verified |
| T3 | External window: parent deleted the temp key before ssh read it | Fixed, verified (auth works) |
| T4 | External: carets inside quotes + newlines in the remote bootstrap through cmd.exe → garbage, cleanup lost (key leaked in %TEMP%) | Fixed b1d60c07 (.cmd + gzip/base64 + stale sweep), verified: live shell, all temp files removed on exit; nits fixed and verified (clean self-delete, single banner) |

### Other
| ID | Finding | Status |
|----|---------|--------|
| guard | Agent guard Windows PEB path: allowed with the override at the boundary, refused when injected below | Works |
| C1 | Config with a UTF-8 BOM (PowerShell 5.1 / Notepad) → "not valid JSON" | Fixed, verified |
| M1 | `mcp serve --help` started the server | Fixed, verified |
| mcp | `rdc mcp serve` on Windows: 102 tools, identical to Linux | Works |
| import | `config import-machine` dropped repo networkIds | Fixed 00f9cc36 |
| dpapi | ci-quality "Secure Storage (dpapi)" reproduced locally: 34 passed, receipt ran 22 | Works |
| install | ct-install-methods Windows x64 binary test reproduced locally | Works |
| tunnel | `repo tunnel` | Untested (needs a running container; prod services not started) |

## Bake / local CI lessons (for PLAN-windows-lane)
1. Install with ONE NIC. A 2nd virtio NIC during Windows Setup hangs OVMF on Setup's first reboot; normal boots with 2 NICs are fine.
2. OpenSSH capability (~10-14 min via Windows Update) is the long pole; set its firewall rule to -Profile Any (libvirt NICs are Public).
3. Permanent autologon (AutoAdminLogon, NoLockScreen, InactivityTimeoutSecs=0), or desktop-session tests silently don't run.
4. Defender: exclusions (Tamper Protection blocks disabling).
5. Add a qemu-guest-agent channel: host-side file reads and exec without SSH.
6. winget is available on Enterprise 26H2; always pass `--id … -e --source winget --accept-*`. Splatting args in PS 5.1 broke one install (use explicit args).
7. Use tar.exe, not Expand-Archive (388 s for 14k files). `git archive` yields only LICENSE (export-ignore); zip `git ls-files` instead.
8. Harness: call npm via cmd/npm.cmd (npm.ps1 is blocked by the execution policy); `powershell -ExecutionPolicy Bypass -File`; read exit codes with $LASTEXITCODE, not `cmd /c "… & echo %ERRORLEVEL%"`; PYTHONIOENCODING=utf-8.
9. GUI tests: run in the desktop session via `schtasks /create /it` + `/run`.
10. Golden image: shut down + copy qcow2 + nvram + swtpm state (19 s) → clone per run.
11. Nested Hyper-V: Enable-WindowsOptionalFeature Microsoft-Hyper-V-All + 1 reboot; the fleet NIC must not share renet's Hyper-V subnet (O6).
13. Block Windows Update in test VMs: at 01:55 an automatic update rebooted win11-spike mid `ops up` and killed the run. Set NoAutoUpdate/AUOptions=1 policy (HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU), NoAutoRebootWithLoggedOnUsers=1, and stop/disable wuauserv + UsoSvc in the bake (re-bake from a fresh ISO every <90 days instead of patching).
12. Win32-OpenSSH quirks: no ssh-copy-id; ssh.exe hangs with piped stdin; ssh.exe spawned by Go never exits when the remote prints (pipes) or prints > ~96 KB (files); use in-process SSH; `localhost` = ::1 first.

## Assets
- VM handbook: README-for-agents.md (same folder)
- Bake: cfg/autounattend.xml, cfg/spike/setup.ps1 (v2), v1/ (first run)
- Harness: tests/run-all.sh, rdc-win-tests.ps1, win-term-sync-guard.ps1, win-sync-advanced.ps1, win-batch{2,3,5,7}.ps1, mcp-probe.js, vsc-desktop.cmd; logs tests/ops-up-*.log
- Tools: /tmp/winspike-tools/{vtype.py,click.sh} (keyboard/mouse into the VM)
- Production touch: hostinger fork demo-stackoverflow:winspike — DELETED via eu-bench at the end (grand repo intact); prod key/config removed from host and VM
