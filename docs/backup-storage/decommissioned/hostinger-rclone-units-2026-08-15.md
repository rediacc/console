# Removed production backup units (hostinger), 2026-08-15

Deleted on the operator's instruction as part of the OneDrive/rclone decommission.
Captured verbatim BEFORE deletion because the code that generated them
(`buildDestinationCommand`) is gone, so the schedule-push command can no longer
recreate them: restoring these means writing the files by hand.

Both pinned slot `0.0.0-dev`, which `./rdc.sh` overwrites on every invocation,
so they were already running the locally-built renet rather than an insulated
release binary.

```ini
===== rediacc-backup-weekly-cold.timer
# /etc/systemd/system/rediacc-backup-weekly-cold.timer
[Unit]
Description=Rediacc Backup Timer (weekly-cold)

[Timer]
OnCalendar=Sun *-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
===== rediacc-backup-weekly-cold.service
# /etc/systemd/system/rediacc-backup-weekly-cold.service
[Unit]
Description=Rediacc Scheduled Backup (weekly-cold)
After=network-online.target

[Service]
Type=oneshot
TimeoutStartSec=infinity
TimeoutStopSec=90
EnvironmentFile=/etc/rediacc/backup-weekly-cold.env
ExecStart=/usr/lib/rediacc/renet/0.0.0-dev/renet backup sync push --datastore /mnt/rediacc --rclone-backend onedrive --mode cold --rclone-bucket hostinger --rclone-folder cold --rclone-param bwlimit=6M

[Install]
WantedBy=multi-user.target
===== rediacc-backup-twiceweekly-hot.timer
# /etc/systemd/system/rediacc-backup-twiceweekly-hot.timer
[Unit]
Description=Rediacc Backup Timer (twiceweekly-hot)

[Timer]
OnCalendar=Tue,Thu *-*-* 22:00:00
Persistent=true

[Install]
WantedBy=timers.target
===== rediacc-backup-twiceweekly-hot.service
# /etc/systemd/system/rediacc-backup-twiceweekly-hot.service
[Unit]
Description=Rediacc Scheduled Backup (twiceweekly-hot)
After=network-online.target

[Service]
Type=oneshot
TimeoutStartSec=infinity
TimeoutStopSec=90
EnvironmentFile=/etc/rediacc/backup-twiceweekly-hot.env
ExecStart=/usr/lib/rediacc/renet/0.0.0-dev/renet backup sync push --datastore /mnt/rediacc --rclone-backend onedrive --mode hot --rclone-bucket hostinger --rclone-folder hot --rclone-param bwlimit=6M --exclude-repo demo-stackoverflow,miscellaneous

[Install]
WantedBy=multi-user.target
```
