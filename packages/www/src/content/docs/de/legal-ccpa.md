---
title: "CCPA-Konformität"
description: "Wie das Self-Hosted-Modell von Rediacc die Anforderungen des California Consumer Privacy Act zum Schutz von Verbraucherdaten erfüllt."
category: "Legal"
order: 4
language: de
sourceHash: "8d0fc1ff16c1be28"
---

Der California Consumer Privacy Act (CCPA) ist ein Landesgesetz, das Verbrauchern in Kalifornien Rechte über ihre persönlichen Daten einräumt, einschließlich des Rechts zu erfahren, welche Daten erhoben werden, des Rechts auf Löschung und des Rechts, dem Verkauf zu widersprechen.

Referenz: [California Attorney General, CCPA](https://oag.ca.gov/privacy/ccpa)

## Zuordnung der Verbraucherrechte

CCPA konzentriert sich auf Verbraucherrechte in Bezug auf persönliche Daten. Rediacc ist ein Self-Hosted-Tool, das auf Ihrer Infrastruktur bereitgestellt wird, und kein Drittanbieter-Dienst, der Verbraucherdaten erhebt oder verkauft. Die folgende Tabelle zeigt, wie Rediacc die CCPA-Konformität Ihrer Organisation unterstützt.

| CCPA-Recht | Anforderung | Rediacc-Fähigkeit |
|-----------|-------------|-------------------|
| Auskunftsrecht (1798.100) | Offenlegung der Kategorien und Zwecke erhobener Daten | Audit-Logs verfolgen alle Datenoperationen. Self-Hosted: Ihre Organisation behält die vollständige Übersicht über vorhandene Daten in jedem Repository. |
| Löschungsrecht (1798.105) | Löschung persönlicher Daten des Verbrauchers auf Anfrage | `rdc repo destroy` löscht das LUKS-verschlüsselte Volume kryptographisch. Fork-Löschung entfernt geklonte Kopien vollständig. |
| Widerspruchsrecht (1798.120) | Keine Weitergabe oder kein Verkauf persönlicher Daten | Self-Hosted-Architektur: Keine Datenübertragung an Rediacc oder Dritte. Daten verbleiben auf Ihren Servern. Die Config-Store-Synchronisation verwendet Zero-Knowledge-Verschlüsselung. Selbst der Synchronisationsserver kann die Daten nicht lesen. |
| Datensicherheit (1798.150) | Angemessene Sicherheitsmaßnahmen implementieren | LUKS2 AES-256-Verschlüsselung, Netzwerkisolation, ausschließlicher SSH-Zugang, isolierte Docker Daemons, Audit-Logging. Der Config Store verwendet dreischichtige Verschlüsselung mit Split-Key-Ableitung und rotierenden Einmaltoken. |

## Status als Dienstleister

Rediacc als Software greift nicht auf Verbraucherdaten zu, verarbeitet sie nicht und speichert sie nicht. Ihr IT-Team betreibt Rediacc auf Ihrer eigenen Infrastruktur. Es fließen keine Daten an das Unternehmen Rediacc. Die Konsequenzen:

- Rediacc ist kein "Dienstleister" im Sinne des CCPA (es verarbeitet keine Daten in Ihrem Auftrag)
- Für das Self-Hosted-Produkt ist kein Datenverarbeitungsvertrag mit Rediacc erforderlich
- Ihre CCPA-Pflichten bestehen zwischen Ihrer Organisation und Ihren Verbrauchern

## Dateninventar

Jedes Rediacc-Repository ist eine diskrete, verschlüsselte Dateneinheit mit einer eindeutigen GUID. Sie können genau inventarisieren, welche Daten wo vorhanden sind:

- `rdc machine query --name <machine> --repositories` listet alle Repositories auf einer Maschine mit Größe und Mount-Status auf
- Jedes Repository ist auf Dateisystem-, Netzwerk- und Container-Ebene isoliert
- Fork-Beziehungen werden verfolgt, sodass Sie alle Kopien eines Datensatzes identifizieren können

CCPA erfordert Daten-Mapping. Das Repository-Modell von Rediacc bietet genau das: eine GUID pro Datensatz, aufzählbar pro Maschine, mit nachverfolgter Fork-Herkunft.
