---
title: "Autostart & Wiederherstellung"
description: "Wie Autostart funktioniert, der periodische Reconciler, der Repositories nach dem Start wiederherstellt, und wie man den Wiederherstellungsstatus prüft."
category: "Guides"
order: 5
language: de
sourceHash: "05d8d5234e0901f6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Autostart & Wiederherstellung

Repositories mit aktiviertem Autostart starten beim Boot automatisch auf. Sollte eines später ausfallen, bringt es der periodische Reconciler wieder zurück. Keine Aufforderungen. Kein manueller Neustart.

Informationen zum Aktivieren oder Deaktivieren von Autostart für ein Repository finden Sie unter [Dienste: Autostart beim Start](/de/docs/services#autostart-on-boot).

## Wie Autostart funktioniert

Wenn Sie Autostart für ein Repository aktivieren, generiert Rediacc eine 256-Byte-LUKS-Schlüsseldatei und fügt sie dem LUKS-Slot 1 des verschlüsselten Volumes hinzu. Die Schlüsseldatei wird gespeichert unter:

```
{datastore}/.credentials/keys/{guid}.key
```

Dadurch kann die Maschine das Repository einbinden, ohne nach der Passphrase zu fragen. LUKS-Slot 0 (Ihre Passphrase) wird nicht verändert.

Der Schlüsseldatei-Slot verwendet den schnellen PBKDF2-KDF: Eine 256-Byte-Zufallsschlüsseldatei bringt ihre eigene Sicherheitsmarge mit, sodass ein speicherintensiver KDF nur Einbindungslatenz hinzufügen würde, ohne den Schutz zu erhöhen. Das Einbinden dauert deutlich unter einer Sekunde. Repositories, die vor dieser Optimierung erstellt wurden, zahlen noch die mehrere Sekunden lange Argon2id-Ableitung pro Einbindung; sie lassen sich an Ort und Stelle konvertieren (Repository ausgehängt) mit dem Operator-Befehl `renet repository kdf-migrate --name <guid>` auf der Maschine. Slot 0 behält Argon2id — die richtige Wahl für eine menschliche Passphrase.

Beim Start liest ein einmaliger systemd-Dienst namens `rediacc-autostart.service` die Liste der Autostart-aktivierten Repositories, bindet jedes mit seiner Schlüsseldatei ein, startet den repository-eigenen Docker-Daemon und führt den `up()`-Hook der Rediaccfile aus. Beim Herunterfahren führt der Dienst `down()` aus, stoppt Docker und schließt die LUKS-Volumes.

> **Sicherheitshinweis:** Die Schlüsseldatei ermöglicht Root-Zugriff auf das Repository ohne Passphrase. Jeder mit Root-Zugriff auf den Server kann Autostart-aktivierte Repositories einbinden. Prüfen Sie dies anhand Ihres Bedrohungsmodells, bevor Sie Autostart für sensible Repos aktivieren.

## Die Wiederherstellungslücke

Der Boot-Autostart läuft genau einmal pro Start. Der Router-Watchdog, der danach kontinuierlich läuft, startet nur *Container innerhalb eines bereits laufenden Repos mit einem laufenden Docker-Daemon* neu. Er kann ein LUKS-Volume nicht neu einbinden oder einen per-Netzwerk-Docker-Daemon neu starten, der gestoppt wurde.

Das bedeutet: Wenn das LUKS-Volume eines Repositories ausgehängt wird oder sein Docker-Daemon nach dem Serverstart stoppt, wird weder der Boot-Dienst noch der Watchdog es wiederherstellen. Vor dem Reconciler blieb ein Repo in diesem Zustand ausgefallen, bis ein Operator eingriff.

## Periodischer Reconciler

Der systemd-Timer `rediacc-autostart-reconcile.timer` feuert ungefähr alle 3 Minuten und führt `renet repository reconcile` aus. Für jedes Autostart-aktivierte Repository prüft der Reconciler drei Dinge:

1. Ist das LUKS-Volume eingebunden?
2. Läuft der per-Netzwerk-Docker-Daemon?
3. Sind die Dienste des Repositories aktiv?

Schlägt eine Prüfung fehl, stellt der Reconciler das Repository mithilfe seiner Schlüsseldatei wieder her: Er bindet das Volume ein, startet den Docker-Daemon und führt `up()` aus. Eine Passphrase ist nicht erforderlich.

Repositories, die gesund sind, gerade von einem Cold-Backup-Lauf belegt werden oder sich innerhalb ihres Backoff-Fensters befinden, werden übersprungen.

### Backoff und persistente Fehlermarkierungen

Ein Repository, das nicht wiederhergestellt werden kann, wiederholt den Versuch nicht sofort bei jedem Tick. Der Reconciler verwendet exponentielles Backoff:

| Fehleranzahl | Wartezeit bis nächstem Versuch |
|--------------|-------------------------------|
| 1 | 1 Minute |
| 2 | 2 Minuten |
| 3 | 5 Minuten |
| 4 | 15 Minuten |
| 5+ | 30 Minuten, dann 60 Minuten |

Nach 5 aufeinanderfolgenden Fehlern schreibt der Reconciler eine dauerhafte Markierungsdatei unter:

```
/var/lib/rediacc/reconcile/failed/{guid}
```

Diese Datei überlebt Log-Rotation. Ihre Existenz bedeutet, dass das Repository Operatoren-Eingriff erfordert. Der Reconciler protokolliert den Fehler auf Fehlerebene und stellt keine automatischen Wiederherstellungsversuche mehr für dieses Repository an, bis die Markierung gelöscht wird.

Häufige Ursachen für persistente Wiederherstellungsfehler:

- **Nicht vertrauenswürdige oder abgelaufene Repo-Lizenz**: die Lizenzprüfung läuft vor `up()`.
- **Fehlende Schlüsseldatei**: wurde die Schlüsseldatei unter `{datastore}/.credentials/keys/{guid}.key` gelöscht, kann der Reconciler das Volume ohne Passphrase nicht einbinden.
- **Defektes Rediaccfile**: ein Syntaxfehler oder ein `up()`-Hook, der immer mit einem Fehlercode beendet wird.

### Verhältnis zum Router-Watchdog

Der Reconciler und der Router-Watchdog behandeln verschiedene Fehlerebenen und sind darauf ausgelegt, sich zu ergänzen:

| Ebene | Was behandelt wird |
|-------|-------------------|
| **Router-Watchdog** | Container-Neustarts innerhalb eines laufenden, eingebundenen Repos mit einem aktiven Docker-Daemon |
| **Reconciler (`rediacc-autostart-reconcile.timer`)** | Repository-Wiederherstellung: LUKS neu einbinden, Docker-Daemon neu starten, `up()` erneut ausführen |

Fällt ein einzelner Container in einem gesunden Repo aus, behandelt der Watchdog dies. Stoppt der gesamte Repo-Daemon, behandelt der Reconciler dies.

## Wiederherstellungsstatus prüfen

### Status von Timer und Dienst

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### Reconciler-Protokolle

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### Persistente Fehlermarkierungen

Repositories mit dauerhaften Fehlermarkierungen auflisten:

```bash
ls /var/lib/rediacc/reconcile/failed/
```

Jeder Dateiname ist eine Repository-GUID. Gleichen Sie diese mit `rdc config repository list` ab, um GUIDs auf Repository-Namen abzubilden.

Um eine Markierung nach Behebung des zugrundeliegenden Problems zu löschen, löschen Sie die Datei:

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

Der Reconciler versucht beim nächsten Timer-Tick erneut die Wiederherstellung.

## Verwandte Seiten

- [Dienste: Autostart beim Start](/de/docs/services#autostart-on-boot): Autostart aktivieren und deaktivieren, Schlüsseldateiverwaltung
- [Backup & Wiederherstellung](/de/docs/backup-restore): Interaktion von Cold-Backup mit laufenden Diensten
