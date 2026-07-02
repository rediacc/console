---
title: "PCI DSS-Konformität"
description: "So erfüllt Rediacc die PCI DSS-Anforderungen: unveränderbare Sicherungen, automatische Netzwerksegmentierung und Zugriffskontrolle auf Infrastruktur-Ebene."
category: "Legal"
order: 6
language: de
sourceHash: "05ca01c69d8bab61"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Mal ehrlich: PCI DSS v4.0.1. ist nicht optional, wenn Sie Karteninhaberdaten verarbeiten. Version 4.0.1. läuft auf eine Anforderung hinaus: infrastrukturelle Isolierung von allem anderen.

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
| **Anf. 10**, Protokollieren und überwachen | Alle Zugriffe auf Systemkomponenten und Karteninhaberdaten protokollieren und überwachen | 70+ Ereignistypen (Auth, API-Tokens, Config, Lizenzierung, Maschinenoperationen). Admin-Dashboard und Portal mit Filterung nach Benutzer, Team, Typ und Datum, plus JSON-Export für programmatische Nutzung. Maschinenoperationen auch in Systemlogs für Defense in Depth. |
| **Anf. 12**, Organisatorische Richtlinien | Informationssicherheit mit organisatorischen Richtlinien und Programmen unterstützen | Self-Hosted eliminiert den Drittanbieter-Verarbeiter-Scope (Anf. 12.8). Reduziert die PCI DSS-Konformitätsgrenze. |

## Netzwerksegmentierung

PCI DSS setzt hart auf Segmentierung. Ich sehe immer wieder Teams, die iptables-Regeln auf unzureichende Isolierung aufsetzen. Das funktioniert nicht. Die Teams, die bestehen, haben Segmentierung in die Architektur eingebaut. Rediacc liefert Ihnen das standardmäßig:

- Jedes Repository läuft in seinem eigenen Docker Daemon unter `/var/run/rediacc/docker-<networkId>.sock`
- Repositories haben isolierte Loopback-IP-Subnetze (127.0.x.x/26, 61 nutzbare IPs pro Netzwerk)
- Von renet erzwungene iptables-Regeln blockieren jeglichen Daemon-übergreifenden Verkehr
- Container verschiedener Repositories können auf Netzwerkebene nicht kommunizieren

Ein Zahlungsverarbeitungs-Repository läuft auf seinem eigenen Docker Daemon und seinem eigenen Loopback-Subnetz, netzwerkisoliert von jeder anderen Anwendung auf derselben Maschine. Keine zusätzlichen Firewall-Regeln zu schreiben.

## Scope-Reduktion

Self-Hosted Rediacc reduziert den PCI DSS-Konformitätsumfang. Sie müssen die Netzwerksegmentierung nicht manuell konfigurieren; sie ist automatisch nach Design. Unsere Dokumentation für diesen Teil muss noch verbessert werden, aber die Isolierung ist solide.

- Kein Drittanbieter-Cloud-Provider im Karteninhaberdatenfluss
- Kein SaaS-Anbieter zur Bewertung unter Anf. 12.8 (Drittanbieter-Dienstleister)
- Physische Sicherheitskontrollen unter Ihrer direkten Verwaltung
- Verschlüsselungsschlüssel nur in der lokalen Konfiguration des Operators gespeichert

## Durchsetzungsfälle

Die meisten PCI-Audit-Ausfälle sind auf eines von zwei Dingen zurückzuführen: Segmentierung, die niemals ordnungsgemäß isoliert war, oder Verschlüsselung, die niemals gegen echte Angriffe getestet wurde.

- Heartland Payment Systems (2008): Angreifer bewegten sich lateral über 48 Datenbanken aufgrund schlechter Netzwerksegmentierung und legten 130 Millionen Kartennummern offen. [Die Gesamtkosten überstiegen 200 Millionen Dollar.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): Angreifer wechselten vom Netzwerkzugang eines HVAC-Lieferanten zu Point-of-Sale-Systemen aufgrund flacher Netzwerkarchitektur und erbeuteten 40 Millionen Zahlungskarten. [Einigung auf 18,5 Millionen Dollar mit 47 Staatsanwaltschaften.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
