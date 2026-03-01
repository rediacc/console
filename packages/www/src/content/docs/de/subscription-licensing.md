---
title: "Abonnement & Lizenzierung"
description: "Abonnements und Maschinenlizenzen für lokale Bereitstellungen verwalten."
category: "Guides"
order: 7
language: de
sourceHash: "84215f54750ac4a4"
---

# Abonnement & Lizenzierung

Maschinen in lokalen Bereitstellungen benötigen eine Abonnementlizenz, um planbasierte Ressourcenlimits durchzusetzen. Die CLI liefert automatisch signierte Lizenz-Blobs über SSH an entfernte Maschinen — keine manuelle Aktivierung oder Cloud-Verbindung seitens des Servers erforderlich.

## Überblick

1. Anmeldung mit `rdc subscription login` (öffnet den Browser zur Authentifizierung)
2. Beliebigen Maschinenbefehl verwenden — Lizenzen werden automatisch verwaltet

Wenn Sie einen Befehl ausführen, der eine Maschine anspricht (`rdc machine info`, `rdc repo up`, usw.), prüft die CLI automatisch, ob die Maschine eine gültige Lizenz besitzt. Falls nicht, wird eine vom Account-Server abgerufen und über SSH ausgeliefert.

## Anmeldung

```bash
rdc subscription login
```

Öffnet einen Browser zur Authentifizierung über den Device-Code-Flow. Nach der Genehmigung speichert die CLI ein API-Token lokal unter `~/.config/rediacc/api-token.json`.

| Option | Erforderlich | Standard | Beschreibung |
|--------|----------|---------|-------------|
| `-t, --token <token>` | Nein | - | API-Token (überspringt Browser-Flow) |
| `--server <url>` | Nein | `https://account.rediacc.com` | Account-Server-URL |

## Status prüfen

```bash
# Status auf Account-Ebene (Plan, Maschinen)
rdc subscription status

# Lizenzdetails von einer bestimmten Maschine einbeziehen
rdc subscription status -m hostinger
```

Zeigt Abonnementdetails vom Account-Server an. Mit `-m` wird zusätzlich eine SSH-Verbindung zur Maschine hergestellt und deren aktuelle Lizenzinformationen angezeigt.

## Lizenz erzwungen aktualisieren

```bash
rdc subscription refresh -m <machine>
```

Stellt eine neue Lizenz erzwungen aus und liefert sie an die angegebene Maschine. Dies ist normalerweise nicht nötig — Lizenzen werden bei normaler CLI-Nutzung automatisch alle 50 Minuten aktualisiert.

## Funktionsweise

1. **Anmeldung** speichert ein API-Token auf Ihrer Workstation
2. **Jeder Maschinenbefehl** löst eine automatische Lizenzprüfung über SSH aus
3. Wenn die entfernte Lizenz fehlt oder älter als 50 Minuten ist, führt die CLI Folgendes durch:
   - Auslesen der Hardware-ID der entfernten Maschine über SSH
   - Aufruf der Account-API zur Ausstellung einer neuen Lizenz
   - Auslieferung sowohl der Maschinenlizenz als auch des Abonnement-Blobs an die entfernte Maschine über SSH
4. Ein 50-Minuten-In-Memory-Cache verhindert redundante SSH-Roundtrips innerhalb derselben Sitzung

Jede Maschinenaktivierung verbraucht einen Platz in Ihrem Abonnement. Um einen Platz freizugeben, deaktivieren Sie eine Maschine über das Account-Portal.

## Kulanzfrist & Degradierung

Wenn eine Lizenz abläuft und nicht innerhalb der 3-tägigen Kulanzfrist aktualisiert werden kann, fallen die Ressourcenlimits der Maschine auf die Community-Plan-Standardwerte zurück. Sobald die Lizenz aktualisiert wird (durch Wiederherstellung der Verbindung und Ausführung eines beliebigen `rdc`-Befehls), werden die ursprünglichen Plan-Limits sofort wiederhergestellt.

## Plan-Limits

### Floating-Lizenz-Limits

| Plan | Floating-Lizenzen |
|------|-------------|
| Community | 2 |
| Professional | 5 |
| Business | 20 |
| Enterprise | 50 |

### Ressourcenlimits

| Ressource | Community | Professional | Business | Enterprise |
|----------|-----------|--------------|----------|------------|
| Bridges | 0 | 1 | 2 | 10 |
| Max reserved jobs | 1 | 2 | 3 | 5 |
| Job timeout (hours) | 2 | 24 | 72 | 96 |
| Repository size (GB) | 10 | 100 | 500 | 2,048 |
| Jobs per month | 500 | 5,000 | 20,000 | 100,000 |
| Pending per user | 5 | 10 | 20 | 50 |
| Tasks per machine | 1 | 2 | 3 | 5 |

### Feature-Verfügbarkeit

| Feature | Community | Professional | Business | Enterprise |
|---------|-----------|--------------|----------|------------|
| Permission groups | - | Yes | Yes | Yes |
| Queue priority | - | - | Yes | Yes |
| Advanced analytics | - | - | Yes | Yes |
| Priority support | - | Yes | Yes | Yes |
| Audit log | - | Yes | Yes | Yes |
| Advanced queue | - | - | Yes | Yes |
| Custom branding | - | Yes | Yes | Yes |
| Dedicated account | - | - | - | Yes |
