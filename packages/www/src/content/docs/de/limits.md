---
title: Limits & Kontingente
description: >-
  Referenz für die Limits, Maximalwerte und Kontingente, die für Rediacc
  Repositories, Dienste, Netzwerk und Speicher gelten.
category: Reference
order: 99
language: de
sourceHash: "e663f13b2f78bc65"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# Limits & Kontingente

Diese Seite dokumentiert die festen und weichen Limits, die für Rediacc-Deployments gelten. Das Verständnis dieser Limits hilft bei der Kapazitätsplanung und vermeidet unerwartete Einschränkungen.

---

## Dienste pro Repository

Jedes Repository unterstützt bis zu **61 Dienste**, die gleichzeitig ausgeführt werden.

Dies ist ein festes Limit, das durch den Netzwerkadressraum bestimmt wird, der jedem Repository zugewiesen ist. Jeder Dienst erhält seine eigene dedizierte private IP-Adresse, und der Adressblock jedes Repositories bietet Platz für genau 61 Dienst-Slots.

Wenn Sie sich diesem Limit nähern, konsolidieren Sie kleinere Dienste (z. B. verschieben Sie Sidecars oder Monitoring-Agenten in ein separates Repository mit eigener Isolationsgrenze) oder refaktorisieren Sie, um die Anzahl der unabhängig laufenden Prozesse innerhalb einer einzelnen Anwendung zu reduzieren.

---

## Repositories pro Maschine

Es gibt kein festes Limit, das von Rediacc erzwungen wird. Das praktische Limit hängt von den Ressourcen Ihrer Maschine ab:

| Ressource | Auswirkung |
|-----------|------------|
| Festplattenspeicher | Jedes Repository ist ein verschlüsseltes Disk-Image. Eine Maschine mit 1 TB nutzbarem Speicher kann viele Repositories aufnehmen, aber die Gesamtgröße aller Images muss in den Datastore-Pool passen. |
| RAM | Jedes laufende Repository startet seinen eigenen Docker-Daemon und Container. Der Speicherverbrauch hängt von Ihren Workloads ab. |
| CPU | Parallele Repository-Operationen (Start, Backup, Fork) erzeugen vorübergehende CPU-Last. |

**Typische Deployments** führen 10 bis 50 Repositories pro Maschine problemlos aus. Maschinen mit 32 GB+ RAM und 500 GB+ Speicher betreiben regelmäßig 100+ Repositories.

### Systemweites Netzwerk-ID-Limit

Jedem Repository wird eine eindeutige **Netzwerk-ID** zugewiesen, eine Zahl, die zur Berechnung seines privaten IP-Adressbereichs verwendet wird. Dieser Pool wird von allen Maschinen und Repositories geteilt, die von derselben Rediacc-Konfiguration verwaltet werden.

| Limit | Wert |
|-------|------|
| Verfügbare Netzwerk-IDs insgesamt | ~261.944 |
| Geltungsbereich | Pro Konfiguration (geteilt über alle Maschinen in einer Konfiguration) |

Wenn ein Repository gelöscht wird, wird seine Netzwerk-ID freigegeben und steht zur Wiederverwendung bereit. Rediacc weist IDs sequenziell zu und sucht erst nach freigegebenen Lücken, wenn der Vorwärtszähler sich der Obergrenze nähert. In der Praxis wird dieses Limit nie erreicht. Es würde erfordern, Hunderttausende von Repositories über die Lebensdauer einer einzelnen Konfiguration zu erstellen und zu verwalten.

---

## Forks

Es gibt kein Limit für die Anzahl aktiver Forks eines Repositories. Jeder Fork ist ein vollständiger Copy-on-Write-Klon mit eigenem verschlüsseltem Speicher, eigenen Netzwerkadressen und eigenem Docker-Daemon. Forks verbrauchen Festplattenspeicher proportional zu den Daten, die nach der Erstellung geschrieben werden (nicht die volle Größe des Eltern-Repositories).

---

## Externe Ports

### Immer aktive Ports

Ports werden erst geöffnet, wenn Sie eine öffentliche IP mit `rdc config infra set --public-ipv4` konfigurieren. Bis dahin sind keine Ports auf der Maschine geöffnet. Nach der Konfiguration:

| Port | Protokoll | Zweck |
|------|-----------|-------|
| 80 | TCP | HTTP: wird von Traefik verarbeitet; gibt 404 für nicht konfigurierte Domains zurück, wird an keinen Dienst weitergeleitet |
| 443 | TCP | HTTPS: wie oben; Anfragen ohne passende Route werden auf der Proxy-Ebene abgelehnt |
| 10000–10010 | TCP | Dynamischer Bereich für Rediacc-verwaltete TCP-Weiterleitung |

HTTP/HTTPS unterscheiden sich von rohen TCP-Ports: Obwohl 80 und 443 geöffnet sind, wird jede Anfrage vom Reverse Proxy gegen eine explizite Routing-Tabelle validiert. Ohne einen konfigurierten Dienst und eine passende Domain wird kein Anwendungscode erreicht und keine Daten werden offengelegt.

### Optionale TCP/UDP-Weiterleitung

Alle anderen Ports (Datenbanken, Caches, Message Broker, DNS, Mail) sind **standardmäßig geschlossen** und müssen explizit geöffnet werden. Dies hält die Angriffsfläche der Maschine minimal.

Um einen Port eines bestimmten Dienstes freizugeben:

```yaml
labels:
  - "rediacc.tcp_ports=5432"   # expose PostgreSQL from this container
  - "rediacc.udp_ports=53"     # expose DNS from this container
```

Um einen Port auf Maschinenebene zu öffnen (verfügbar für alle Dienste):

```bash
rdc config infra set -m server-1 --tcp-ports 25,587,993   # mail server
rdc config infra push -m server-1
```

> Geben Sie niemals Datenbank- oder Cache-Ports extern frei, es sei denn, Sie haben eine spezifische Anforderung. Verwenden Sie HTTPS-Auto-Routen für Webdienste und halten Sie Speicherdienste intern.

---

## Datastore

Der Datastore ist ein Pool fester Größe, der bei der Ersteinrichtung einer Maschine erstellt wird. Seine Größe wächst nicht automatisch.

- **Empfohlene Mindestgröße**: 50 GB
- **Maximale Größe**: Begrenzt durch Ihre Festplatte. Ein einzelner Pool kann eine gesamte Festplatte umfassen.
- **Größenanpassung**: Verwenden Sie `rdc datastore resize`, um einen bestehenden Pool zu erweitern. Verkleinern wird nicht unterstützt.
- **Dateisystem**: Rediacc verwendet intern BTRFS für Copy-on-Write-Snapshots und effizientes Forking. Erfordert eine Maschine mit **Linux Kernel 6.1 oder neuer** für volle Produktionsstabilität.

Jedes Repository-Image hat eine feste maximale Größe, die bei der Erstellung festgelegt wird (Standard: 10 GB). Verwenden Sie `rdc repo resize`, um ein einzelnes Repository zu erweitern. Die Summe aller maximalen Repository-Größen darf die Datastore-Pool-Größe nicht überschreiten.

---

## HTTP-Routen

Jeder Dienst mit dem Label `rediacc.service_port` erhält automatisch eine HTTPS-Route. Es gibt kein Limit für die Anzahl der Dienste mit Routen, vorbehaltlich des Maximums von 61 Diensten pro Repository.

Wildcard-TLS-Zertifikate werden pro Repository beim ersten Deployment über Let's Encrypt (Cloudflare DNS-01 Challenge) bereitgestellt. Let's Encrypt hat ein Limit von **50 Zertifikaten pro registrierter Domain pro Woche**. Da Rediacc ein Wildcard-Zertifikat pro Repository verwendet (nicht pro Dienst), kann ein Deployment mit 50+ neuen Repositories in einer einzelnen Woche dieses Limit erreichen.

Forks verwenden das vorhandene Wildcard-Zertifikat des Eltern-Repositories wieder und verbrauchen kein Zertifikatskontingent.

---

## Checkpoint / Restore (CRIU)

Live-Migration über CRIU hat folgende Einschränkungen:

- **Opt-in**: Nur Container mit dem Label `rediacc.checkpoint=true` werden gesichert. Datenbanken und zustandslose Dienste sind standardmäßig ausgeschlossen und starten bei der Wiederherstellung neu.
- **Kernel-Anforderung**: Linux 6.1+ auf sowohl der Quell- als auch der Zielmaschine.
- **Netzwerkmodus**: CRIU erfordert den Host-Netzwerkmodus. Container mit benutzerdefinierten Netzwerkkonfigurationen können nicht gesichert werden.
- **Arbeitsspeicher**: Die Größe der Checkpoint-Daten entspricht dem residenten Speicher des gesicherten Prozesses. Große In-Memory-Datensätze (z. B. eine Node.js-App, die 4 GB Daten zwischenspeichert) erzeugen 4 GB Checkpoint-Dateien.
- **TCP-Verbindungen**: Anwendungen müssen Verbindungsverluste bei der Wiederherstellung tolerieren. Aktive TCP-Verbindungen bleiben **nicht** erhalten, der wiederhergestellte Prozess sieht Sockets als geschlossen und muss die Verbindung neu aufbauen. Dies gilt sowohl für Wiederherstellungen auf derselben Maschine als auch für maschinenübergreifende Wiederherstellungen.
- **Live-Fork auf derselben Maschine wird nicht unterstützt**: `rdc repo fork --parent X --tag Y --checkpoint` erfasst den Checkpoint erfolgreich, aber das anschließende `rdc repo up` auf derselben Maschine schlägt mit `criu failed: type RESTORE errno 0` fehl, solange das Eltern-Repository noch läuft. Dies wird durch Upstream-CRIU-Bugs [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) und [checkpoint-restore/criu#514](https://github.com/checkpoint-restore/criu/issues/514) verursacht, die mit `network_mode: host` interagieren. Für die In-Place-Prozesszustandserhaltung auf derselben Maschine verwenden Sie stattdessen `rdc repo down --checkpoint` + `rdc repo up`. Für Live-Migration verwenden Sie `rdc repo push --checkpoint` auf eine andere Maschine.

---

## Backups

| Limit | Wert |
|-------|------|
| Backup-Ziele pro Repository | Unbegrenzt |
| Gleichzeitige Backup-Jobs | 1 pro Repository (Jobs werden in die Warteschlange gestellt, wenn sie gleichzeitig ausgelöst werden) |
| Backup-Häufigkeit | Kein Mindestintervall erzwungen; begrenzt durch Ihre Speicherbandbreite. Verwenden Sie `rdc config backup-strategy set --name <name> --bwlimit "6M"` zum Begrenzen der Upload-Geschwindigkeit |
| Aufbewahrung | Gesteuert durch Ihren Speicheranbieter (S3, Cloudflare R2, usw.). Rediacc erzwingt keine Aufbewahrungsrichtlinien. |
| Maschinenübergreifendes Backup | Unterstützt; die Zielmaschine muss über ausreichend Datastore-Speicherplatz verfügen |

---

## CLI & API

| Limit | Wert |
|-------|------|
| Gleichzeitige `rdc`-Befehle gegen dieselbe Maschine | Unbegrenzt (jeder Befehl öffnet seine eigene SSH-Verbindung) |
| Standard-Parallelität beim Repository-Start | 3 (anpassbar mit `--concurrency`) |
| SSH-Verbindungs-Timeout | 30 Sekunden für die initiale Verbindung |
| `rdc`-Sitzungsdauer | Kein Timeout; lang laufende Operationen halten die Verbindung aufrecht |

---

## Unterstützte Betriebssystemversionen

Remote-Maschinen müssen eines der folgenden Systeme ausführen, um die Kernel-, Dateisystem- und Netzwerkisolationsanforderungen von Rediacc zu erfüllen. Diese Liste ist der maßgebliche CI-getestete Satz (Bridge Workers-Matrix) und muss synchron mit [Anforderungen](/en/docs/requirements) bleiben:

| Betriebssystem | Mindestversion | Standard-Kernel | Hinweise |
|----------------|----------------|-----------------|----------|
| Ubuntu | 24.04 LTS *(empfohlen)* | 6.8 | AppArmor Standard. |
| Debian | 13 (Trixie); 12 Bookworm funktioniert ebenfalls | 6.12 (6.1 auf Debian 12) | |
| Fedora | 43 | 6.12 | SELinux enforcing Standard. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor Standard. |
| Oracle Linux | 10 (UEK) | UEK 7+ | UEK behält btrfs; SELinux enforcing Standard. |

**Erforderlicher Mindest-Kernel: 6.1.** Maschinen mit älteren Kernels werden bei der Einrichtung mit einer klaren Fehlermeldung abgelehnt.

> **Warum Kernel 6.1?** Rediacc verwendet BTRFS für verschlüsselten Repository-Speicher und Copy-on-Write-Forking. Linux 6.1 führte kritische BTRFS-Verbesserungen ein, die die Mount-Zeiten für große Datastores erheblich reduzieren, die Leistung beim Löschen von Snapshots verbessern und Datenintegritätsprobleme früherer Kernel beheben. Kernel 6.1 wird auch für die Netzwerkisolations-Hooks auf Kernel-Ebene benötigt, die die Repository-übergreifende Isolation erzwingen, indem sie `bind()`-Aufrufe transparent umschreiben und Verbindungen zwischen Repositories blockieren.

> **Warum nicht Rocky Linux 10 / RHEL 10 Stock-Kernel?** Der Stock-Kernel von RHEL 10 wird ohne das `btrfs`-Modul ausgeliefert (`modprobe btrfs` schlägt mit "Module btrfs not found" fehl). Rediacc's verschlüsseltes Storage-Backend kann ohne btrfs nicht laufen. **Oracle Linux 10 ist das einzige RHEL-kompatible Ziel auf der unterstützten Liste**, weil es standardmäßig den Unbreakable Enterprise Kernel (UEK) verwendet, der btrfs beibehält. Siehe [Anforderungen: Warum UEK?](/en/docs/requirements) für die vollständige Erläuterung.

### Kernel-Feature-Matrix

Operatoren können diese Matrix als Übersicht nutzen, was jedes CI-getestete Betriebssystem out-of-the-box bereitstellt. Alle fünf erfüllen jede Anforderung; die Matrix ist eine operatorbezogene Referenz, kein Auswahlkriterium.

| Betriebssystem | btrfs-Modul | cgroups v2 | Landlock (ABI >= 1) | eBPF cgroup Hooks |
|----------------|-------------|------------|---------------------|-------------------|
| Ubuntu 24.04 | im Kernel | unified hierarchy | ja (5.13+) | ja |
| Debian 13 | im Kernel | unified hierarchy | ja | ja |
| Fedora 43 | im Kernel | unified hierarchy | ja | ja |
| openSUSE Leap 16.0 | im Kernel | unified hierarchy | ja | ja |
| Oracle Linux 10 (UEK) | im Kernel (via UEK) | unified hierarchy | ja | ja |
