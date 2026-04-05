---
title: "PCI DSS-Konformität"
description: "Wie Rediacc den PCI DSS-Anforderungen zum Schutz von Zahlungskartendaten durch Verschlüsselung, Netzwerksegmentierung und Zugriffskontrolle entspricht."
category: "Legal"
order: 6
language: de
sourceHash: "06528e1f28fc2764"
---

Der Payment Card Industry Data Security Standard (PCI DSS) ist für jede Organisation erforderlich, die Karteninhaberdaten speichert, verarbeitet oder überträgt. Die aktuelle Version ist PCI DSS v4.0.1.

Referenz: [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## Anforderungszuordnung

| PCI DSS Anforderung | Beschreibung | Rediacc-Fähigkeit |
|---------------------|-------------|-------------------|
| **Anf. 1**, Netzwerksicherheitskontrollen | Netzwerksicherheitskontrollen installieren und pflegen | Pro-Repository-iptables-Regeln blockieren jeglichen repositoryübergreifenden Verkehr. Jedes Repository erhält sein eigenes Loopback-IP-Subnetz (/26). |
| **Anf. 2**, Sichere Konfigurationen | Sichere Konfigurationen auf alle Systemkomponenten anwenden | Rediaccfile-Lebenszyklus-Hooks erzwingen deterministische, reproduzierbare Konfigurationen. Keine Standard-Anmeldedaten. LUKS-Schlüssel werden vom Operator generiert. |
| **Anf. 3**, Gespeicherte Kontodaten schützen | Gespeicherte Kontodaten mit Verschlüsselung schützen | LUKS2 AES-256-Verschlüsselung auf allen Repository-Volumes. Verschlüsselung ist obligatorisch, nicht optional. Kryptographische Löschung via LUKS-Schlüsselzerstörung. |
| **Anf. 4**, Daten bei Übertragung schützen | Karteninhaberdaten mit starker Kryptographie bei der Übertragung schützen | Alle Remote-Operationen über SSH. Backup-Transport Ende-zu-Ende verschlüsselt. Keine unverschlüsselten Datenpfade. |
| **Anf. 6**, Sichere Entwicklung | Sichere Systeme und Software entwickeln und pflegen | CoW-Kloning erstellt isolierte Testumgebungen, ohne Produktions-Karteninhaberdaten Entwicklungsnetzwerken auszusetzen. Fork-Test-Promote-Workflow. |
| **Anf. 7**, Zugriff einschränken | Zugriff auf Systemkomponenten und Karteninhaberdaten nach Geschäftsbedarf einschränken | Pro-Repository-Docker-Daemon-Sockets. Zugang zu einem Repository gewährt keinen Zugang zu einem anderen. SSH-Schlüssel-basierte Authentifizierung. |
| **Anf. 8**, Benutzer identifizieren und authentifizieren | Benutzer identifizieren und Zugang zu Systemkomponenten authentifizieren | SSH-Schlüssel-Authentifizierung. API-Tokens mit IP-Bindung und bereichsbezogenen Berechtigungen. Zwei-Faktor-Authentifizierung (TOTP). |
| **Anf. 9**, Physischen Zugang einschränken | Physischen Zugang zu Karteninhaberdaten einschränken | Self-Hosted: physische Sicherheit unter Ihrer direkten Kontrolle. LUKS-Verschlüsselung macht gestohlene Laufwerke unlesbar. |
| **Anf. 10**, Protokollieren und überwachen | Alle Zugriffe auf Systemkomponenten und Karteninhaberdaten protokollieren und überwachen | Über 40 Ereignistypen auf Kontoebene (Auth, API-Tokens, Config, Lizenzierung). Admin-Dashboard mit Filterung nach Benutzer, Team und Datum. `rdc audit` CLI für programmatischen Export. Operationen auf Maschinenebene über SSH und Systemlogs auditierbar. |
| **Anf. 12**, Organisatorische Richtlinien | Informationssicherheit mit organisatorischen Richtlinien und Programmen unterstützen | Self-Hosted eliminiert den Drittanbieter-Verarbeiter-Scope (Anf. 12.8). Reduziert die PCI DSS-Konformitätsgrenze. |

## Netzwerksegmentierung

PCI DSS legt großen Wert auf Netzwerksegmentierung zur Isolation der Karteninhaberdatenumgebung (CDE). Rediacc bietet dies architekturbedingt:

- Jedes Repository läuft in seinem eigenen Docker Daemon unter `/var/run/rediacc/docker-<networkId>.sock`
- Repositories haben isolierte Loopback-IP-Subnetze (127.0.x.x/26, 61 nutzbare IPs pro Netzwerk)
- Von renet erzwungene iptables-Regeln blockieren jeglichen Daemon-übergreifenden Verkehr
- Container verschiedener Repositories können auf Netzwerkebene nicht kommunizieren

Ein Zahlungsverarbeitungs-Repository ist netzwerkisoliert von allen anderen Anwendungen auf derselben Maschine. Keine zusätzliche Firewall-Konfiguration erforderlich.

## Scope-Reduktion

Self-Hosted Rediacc reduziert den PCI DSS-Konformitätsumfang:

- Kein Drittanbieter-Cloud-Provider im Karteninhaberdatenfluss
- Kein SaaS-Anbieter zur Bewertung unter Anf. 12.8 (Drittanbieter-Dienstleister)
- Physische Sicherheitskontrollen unter Ihrer direkten Verwaltung
- Verschlüsselungsschlüssel nur in der lokalen Konfiguration des Operators gespeichert

## Durchsetzungsfälle

Schlechte Netzwerksegmentierung und fehlende Verschlüsselung haben zu kostspieligen PCI DSS-Durchsetzungsmaßnahmen geführt:

- Heartland Payment Systems (2008): Angreifer bewegten sich lateral über 48 Datenbanken aufgrund schlechter Netzwerksegmentierung und legten 130 Millionen Kartennummern offen. [Die Gesamtkosten überstiegen 200 Millionen Dollar.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): Angreifer wechselten vom Netzwerkzugang eines HVAC-Lieferanten zu Point-of-Sale-Systemen aufgrund flacher Netzwerkarchitektur und erbeuteten 40 Millionen Zahlungskarten. [Einigung auf 18,5 Millionen Dollar mit 47 Staatsanwaltschaften.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
