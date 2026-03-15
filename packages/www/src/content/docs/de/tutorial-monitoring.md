---
title: "Überwachung & Diagnose"
description: "Maschinengesundheit prüfen, Container inspizieren, systemd-Dienste überprüfen, Host-Schlüssel scannen und Umgebungsdiagnosen ausführen."
category: "Tutorials"
order: 4
language: de
sourceHash: "af9f17a05dfb13b9"
---

# Infrastruktur mit Rediacc überwachen und diagnostizieren

Um die Infrastruktur gesund zu halten, benötigen Sie Einblick in den Maschinenzustand, den Container-Status und die Dienst-Gesundheit. In diesem Tutorial führen Sie Umgebungsdiagnosen aus, prüfen die Maschinengesundheit, inspizieren Container und Dienste, überprüfen den Vault-Status und verifizieren die Konnektivität. Am Ende wissen Sie, wie Sie Probleme in Ihrer gesamten Infrastruktur identifizieren und untersuchen können.

## Voraussetzungen

- Die `rdc` CLI installiert mit einer initialisierten Konfiguration
- Eine bereitgestellte Maschine mit mindestens einem laufenden Repository (siehe [Tutorial: Repository-Lebenszyklus](/de/docs/tutorial-repos))

## Interaktive Aufzeichnung

![Tutorial: Überwachung & Diagnose](/assets/tutorials/monitoring-tutorial.cast)

### Schritt 1: Diagnose ausführen

Beginnen Sie damit, Ihre lokale Umgebung auf Konfigurationsprobleme zu prüfen.

```bash
rdc doctor
```

Prüft Node.js, CLI-Version, renet-Binary, Konfiguration und Virtualisierungsunterstützung. Jede Prüfung meldet **OK**, **Warning** oder **Error**.

### Schritt 2: Maschinengesundheitsprüfung

```bash
rdc machine health server-1
```

Ruft einen umfassenden Gesundheitsbericht von der Remote-Maschine ab: Systembetriebszeit, Festplattennutzung, Datastore-Nutzung, Container-Anzahl, Speicher-SMART-Status und erkannte Probleme.

### Schritt 3: Laufende Container anzeigen

```bash
rdc machine containers server-1
```

Listet alle laufenden Container über alle Repositories auf der Maschine auf und zeigt Name, Status, Zustand, Gesundheit, CPU-Nutzung, Speichernutzung und welchem Repository jeder Container gehört.

### Schritt 4: systemd-Dienste prüfen

Um die zugrunde liegenden Dienste zu sehen, die den Docker-Daemon und die Netzwerke jedes Repositorys betreiben:

```bash
rdc machine services server-1
```

Listet Rediacc-bezogene systemd-Dienste (Docker-Daemons, Loopback-Aliase) mit ihrem Zustand, Unterzustand, Neustart-Anzahl und Speichernutzung auf.

### Schritt 5: Vault-Statusübersicht

```bash
rdc machine vault-status server-1
```

Bietet einen Überblick über die Maschine: Hostname, Betriebszeit, Speicher, Festplatte, Datastore und Gesamtzahl der Repositories.

### Schritt 6: Host-Schlüssel scannen

Wenn eine Maschine neu aufgebaut wurde oder sich ihre IP geändert hat, aktualisieren Sie den gespeicherten SSH-Host-Schlüssel.

```bash
rdc config machine scan-keys server-1
```

Ruft die aktuellen Host-Schlüssel des Servers ab und aktualisiert Ihre Konfiguration. Dies verhindert Fehler wie "host key verification failed".

### Schritt 7: Konnektivität überprüfen

Eine schnelle SSH-Konnektivitätsprüfung, um zu bestätigen, dass die Maschine erreichbar ist und antwortet.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Der Hostname bestätigt, dass Sie mit dem richtigen Server verbunden sind. Die Betriebszeit bestätigt, dass das System normal läuft.

## Fehlerbehebung

**Gesundheitsprüfung läuft ab oder zeigt "SSH connection failed"**
Überprüfen Sie, ob die Maschine online und erreichbar ist: `ping <ip>`. Stellen Sie sicher, dass Ihr SSH-Schlüssel korrekt konfiguriert ist mit `rdc term <machine> -c "echo ok"`.

**"Service not found" in der Dienstliste**
Rediacc-Dienste erscheinen erst, nachdem mindestens ein Repository bereitgestellt wurde. Wenn keine Repositories existieren, ist die Dienstliste leer.

**Container-Liste zeigt veraltete oder gestoppte Container**
Container aus früheren Bereitstellungen können bestehen bleiben, wenn `repo down` nicht sauber ausgeführt wurde. Stoppen Sie sie mit `rdc repo down <repo> -m <machine>` oder inspizieren Sie direkt über `rdc term <machine> <repo> -c "docker ps -a"`.

## Nächste Schritte

Sie haben Diagnosen ausgeführt, die Maschinengesundheit geprüft, Container und Dienste inspiziert und die Konnektivität verifiziert. Um mit Ihren Bereitstellungen zu arbeiten:

- [Monitoring](/de/docs/monitoring) — vollständige Referenz für alle Überwachungsbefehle
- [Troubleshooting](/de/docs/troubleshooting) — häufige Probleme und Lösungen
- [Tutorial: Tools](/de/docs/tutorial-tools) — Terminal, Dateisynchronisierung und VS Code-Integration
