# hostinger: mail and gitlab restarts on the renet with the deep re-own

Designed 2026-11-07 by a read-only Plan agent from /tmp/m/dryrun-equivalent.txt (mail 4030 paths, gitlab 9956) and agent/d778be9d/hostinger-runbook.md. Runs after PLAN-renet-restart-cycle-defects D1 lands and `machine setup hostinger` installs it; stop if `./rdc.sh repo admin ownership --help` lacks `--root-owned`, `--dry-run`, `--undo`.

`R="./rdc.sh --config eu-bench"`, `RO="REDIACC_NO_PROVISION=1 $R"`. Repo content sits under `<mount>/mail` and `<mount>/gitlab/server`.

## Facts that decide it

- Compose runs with `userns_mode: host` (private/renet/pkg/compose/wrapper.go:424): container root is host root, and the mail and gitlab daemons start as root and drop privileges, so 7111-owned files stay readable to them.
- The re-own changes owner and group (Lchown uid, gid), not modes.
- The shallow per-up re-own (private/renet/pkg/orchestration/lifecycle.go:292-309) flips root-owned files in root-owned dirs back to 7111 on every unprivileged up(), so a chown back to root on one path does not stick: undo is a whole-repo step.
- OpenSSH checks a host key's owner only when it equals the sshd uid; gitlab's sshd run script is disabled (`sshd-disabled-run`).
- OpenDKIM keys matter only if `ENABLE_OPENDKIM` is on (the infra doc says Rspamd signs).

## Mail

Container name is discovered (template `mailserver`, infra doc `mail-server`): `MS` from `docker ps`.

1. Baseline to /tmp/m/mail-before/: `machine health -o json`, `machine status --containers`, `docker ps`, Rediaccfile and compose (secrets redacted), `docker exec $MS env | grep -E '^(ENABLE_|SSL_|TLS_)'`, owners of mail/data/config, mail/data/state, the tls keys, `postfix status`, `postconf -h smtpd_tls_cert_file smtpd_tls_key_file`, `postqueue -p`, tails of mail.log and rspamd.log; from outside, `openssl s_client` subject, issuer, dates and sha256 fingerprint on 465, 993, 587 (-starttls smtp), 25 (-starttls smtp), 143 (-starttls imap) for mail.rediacc.io, the port-25 banner, DKIM TXT for rediacc.com and rediacc.io; and `repo admin ownership mail --root-owned --dry-run` compared with the 4030-path list.
   Pass: all ports open, one certificate fingerprint on 465/993/587/25, queue empty, existing warnings noted.
2. No path is excluded: tls keys (270, about 90 exported hostnames, rewritten by the 5-minute cert export), config copied to /etc at DMS start, postfix spool pid and etc re-created at start, roundcube/www web assets, probe.eml.
3. `$R machine restart-services hostinger --include-docker --repo mail --json`, then `$R job logs <id> -m hostinger --follow` and `job status`; allow the 15-minute budget (DMS start_period 120 s, ClamAV slow), never `job cancel`. Then confirm `.rediacc/state/ownership-v2` and a manifest of about 4030 lines.
4. Verify to /tmp/m/mail-after/: containers `Up (healthy)`; the same handshakes with `Verify return code: 0 (ok)` and an unchanged fingerprint (or a renewed one shared by all four ports); EHLO on 465 shows AUTH; `doveadm auth test` or `doveadm user '*'` runs; a grep of mail.log and rspamd.log for permission denied, not owned by, insecure, cannot open, ssl key or cert failures, opendkim security, fatal finds nothing new; `postfix check` prints nothing; supervisord programs RUNNING; queue unchanged; `rspamadm configtest` OK; roundcube answers 200 or its login redirect.
5. Rollback: `$R repo admin ownership mail --root-owned --undo`, compare owners with the baseline, restart the repo on the new renet; a single spool path: chown root:root it and `postfix reload`, recorded since the next up() flips it; fallback `repo down` and `repo up`, never a wipe.

## GitLab

1. Baseline to /tmp/m/gitlab-before/: health, containers, Rediaccfile and compose (redacted; the template's `chmod -R 755 ./config ./logs ./data` fails as 7111 on a root-owned tree, which is why the re-own matters here), `gitlab-ctl status`, VERSION, tails of production.log and gitlab_error.log, owners of server/config and server/data including ssh_host_* and gitlab-secrets.json, HTTP codes for /users/sign_in, /-/readiness, /api/v4/version, the 443 certificate fingerprint, and the dry run (about 9956 paths).
   Pass: sign_in and readiness 200, every `gitlab-ctl status` line `run:`.
2. No path is excluded: logs (9908, svlogd runs as root), chef output under server/data, ssh host keys, gitlab-secrets.json and gitlab.rb read by chef as root. `skip-auto-reconfigure` stays; do not run `gitlab-ctl reconfigure`.
3. Restart as for mail (3 to 8 minutes to healthy), then the marker and a manifest of about 9956 lines.
4. Verify to /tmp/m/gitlab-after/: sign_in, readiness and liveness 200, version endpoint as before, VERSION unchanged, every service `run:`, no new permission errors in /var/log/gitlab/*/current and the rails logs, optional `gitlab-rake gitlab:check SANITIZE=true`, 443 fingerprint unchanged.
5. Rollback: `--undo` then `repo down` and `repo up`; one tree: `chown -R --from=7111 root:root server/logs` and `docker restart`, recorded; fallback as for mail.

## Order

The runbook keeps mail inside 00:00-01:00Z (step 7); gitlab after mail, one repo at a time. After both, `machine health` shows no stale_binary entry. Keep the before and after folders for the plan tick.
