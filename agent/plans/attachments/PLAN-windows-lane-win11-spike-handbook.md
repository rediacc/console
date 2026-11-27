<!-- Attachment of agent/plans/PLAN-windows-lane.md. Source: /var/lib/libvirt/images/win11-spike/README-for-agents.md (copied 2026-11-27). Paths in it refer to that host folder; the bake inputs (cfg/, tests/) stay there because the generated unattend file carries the VM admin password. -->

# win11-spike: Windows 11 test VM for rdc (shared between console-6c and drain-promoted-plans-writers)

Owner/driver: console-6c (tmux 0:6 "windows"). The other session may use it, break it, or rebuild it — just send a heads-up message first so runs don't collide.

## What it is
- libvirt domain `win11-spike` (qemu:///system, the user is in the libvirt group, no sudo needed for virsh)
- Windows 11 Enterprise Evaluation 26H2 build 26300.9457, 4 vCPU / 8 GB / 64 GB qcow2, UEFI Secure Boot + swtpm TPM 2.0
- NIC1 `default` (NAT, internet) IP in guest_ip; NIC2 `renet11` (fleet, DHCP .200-.253) is HOT-PLUGGED after boot (see pitfalls)
- Local admin `rdc`, password in ./admin_password (600). SSH key ./spike_key → `ssh -i spike_key rdc@$(cat guest_ip)` (default shell: Windows PowerShell 5.1)
- qemu-guest-agent channel present: `virsh -c qemu:///system qemu-agent-command win11-spike '{"execute":"guest-ping"}'` (guest-exec / guest-file-* work without SSH)
- Installed by provisioning: OpenSSH Server, virtio guest tools + qemu-ga, Node LTS (26.x), Git for Windows, VS Code (user scope) + ms-vscode-remote.remote-ssh

## Build from zero (unattended, ~25-35 min)
- Inputs: win11-eval.iso (Evaluation Center, 26H2), virtio/virtio-win.iso (fedorapeople stable), cfg/ (autounattend.xml + spike/setup.ps1) → unattend.iso
- The exact virt-install line is in the console-6c transcript; in short: --osinfo win11, q35, uefi secure-boot+enrolled-keys, tpm-crb emulator 2.0, virtio disk boot.order=2, eval ISO sata boot.order=1, virtio ISO + unattend ISO as sata cdroms, ONE virtio NIC on `default`, guest-agent channel, vnc on 127.0.0.1
- Send KEY_ENTER for ~20 s right after start (the CD "press any key" prompt); later reboots fall through to disk on their own
- setup.ps1 logs per-phase timings to C:\spike-setup.log (UTF-16) and touches C:\spike-setup.done
- v1 files (first manual run) kept in ./v1

## Pitfalls already found (feed into the Windows plan)
1. A 2nd virtio NIC present during Windows Setup hangs OVMF on Setup's first reboot (vCPU spins in firmware, black screen, survives reset). Normal boots with the 2nd NIC are fine (tested with rom.bar on and off), so: install with ONE NIC, add the fleet NIC (even persistently) after the install.
2. The OpenSSH capability's firewall rule is Private-only; libvirt NICs come up Public → set the rule to -Profile Any (setup.ps1 v2 does it).
3. Add-WindowsCapability OpenSSH.Server takes ~10 min (Windows Update download) — the long pole of the bake.
4. Defender Tamper Protection refuses DisableRealtimeMonitoring; use exclusions.
5. GUI programs launched over SSH land in session 0 (invisible). Run them in the desktop session with a scheduled task: `schtasks /create /tn X /sc once /st 23:59 /it /ru rdc /tr <cmd>` + `schtasks /run /tn X`.
6. Windows' bundled ssh-keyscan (OpenSSH_for_Windows 9.5p2/LibreSSL) returns 0 keys from OpenSSH 9.6+ servers (sntrup761 KEX) — fixed in rdc by 016c883e80 (ssh2-based scan).
7. Desktop-session tests need PERMANENT autologon: the bake's unattend AutoLogon has LogonCount=1, so after the first reboot the VM sits on the lock screen and every /IT scheduled task silently never runs. Fix (applied 21:18): Winlogon AutoAdminLogon=1 + DefaultUserName/DefaultPassword, no AutoLogonCount, NoLockScreen=1, InactivityTimeoutSecs=0. The bake should set this.
8. Hyper-V is enabled (nested). renet's Hyper-V NAT uses 192.168.111.0/24 inside Windows = the KVM fleet subnet, so the fleet NIC is detached while nested ops VMs exist (O6).
9. Screenshots: `virsh screenshot win11-spike out.png`. Mouse click: /tmp/winspike-tools/click.sh <dom> <x> <y> (QMP input-send-event, 1280x800). Typing: /tmp/winspike-tools/vtype.py.

## Test harness
- tests/run-all.sh <bundle> [sha256]: stages bundle + renet (renet.exe + renet-linux-amd64) + fleet key, runs tests/rdc-win-tests.ps1 (stock PATH), host-key compare vs Linux ssh-keyscan, vscode connect in the desktop session + screenshot, and a Linux regression in an isolated HOME. Results in tests/results-<time>/
- rdc configs on the VM: `winspike` (local-only, fleet machines), `winprod` (local-only, hostinger imported from eu-bench — no account token, so it can never rotate the host's eu-bench login)
- prod/: REMOVED after the night (hostinger key + winprod config deleted from host and VM; fork demo-stackoverflow:winspike deleted via eu-bench).
- Agent honesty on Windows: every rdc run sets CLAUDECODE=1 plus REDIACC_ALLOW_GRAND_REPO=* / REDIACC_ALLOW_CLUSTER_OPS=* at the agent boundary process, mirroring the host session's environment.
