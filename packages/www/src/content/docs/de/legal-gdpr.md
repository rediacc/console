---
title: "DSGVO-Konformität"
description: "Wie die Self-Hosted-Architektur von Rediacc den DSGVO-Anforderungen für Datenschutz und Privatsphäre entspricht."
category: "Legal"
order: 1
language: de
sourceHash: "e3d383739190bb30"
---

Die Datenschutz-Grundverordnung (DSGVO) ist das Datenschutzgesetz der Europäischen Union, in Kraft seit Mai 2018. Sie regelt, wie Organisationen personenbezogene Daten von Personen in der EU erheben, verarbeiten und speichern.

Volltext: [Verordnung (EU) 2016/679](https://gdpr-info.eu/)

## Artikelzuordnung

Die folgende Tabelle ordnet spezifische DSGVO-Artikel den technischen Fähigkeiten von Rediacc zu.

| Artikel | Anforderung | Rediacc-Fähigkeit |
|---------|-------------|-------------------|
| [Art. 5](https://gdpr-info.eu/art-5-gdpr/), Grundsätze | Datenminimierung, Integrität, Vertraulichkeit | CoW-Klone (`cp --reflink=always`) duplizieren Daten auf derselben Maschine ohne Netzwerktransfer. LUKS2 AES-256 verschlüsselt alle Daten im Ruhezustand. |
| [Art. 17](https://gdpr-info.eu/art-17-gdpr/), Recht auf Löschung | Personenbezogene Daten auf Anfrage löschen | `rdc repo destroy` löscht das LUKS-Volume kryptographisch. Das Löschen eines Forks entfernt die geklonte Kopie vollständig. |
| [Art. 25](https://gdpr-info.eu/art-25-gdpr/), Datenschutz durch Technikgestaltung | Datenschutz durch Voreinstellung | Verschlüsselung ist obligatorisch, nicht optional. Jedes Repository erhält einen isolierten Docker Daemon und ein eigenes Netzwerk. Keine Datenfreigabe zwischen Repositories. Der Config Store verwendet Zero-Knowledge-Verschlüsselung: Configs werden clientseitig mit AES-256-GCM vor dem Upload verschlüsselt, sodass der Server keine Klartextdaten lesen kann. |
| [Art. 28](https://gdpr-info.eu/art-28-gdpr/), Auftragsverarbeiter | Pflichten bei Drittanbieter-Datenverarbeitung | Self-Hosted: Rediacc läuft auf Ihrer Infrastruktur. Keine Daten verlassen Ihre Maschine während Fork-, Klon- oder Backup-Operationen. Keine SaaS-Komponente verarbeitet personenbezogene Daten. |
| [Art. 30](https://gdpr-info.eu/art-30-gdpr/), Verarbeitungsverzeichnis | Verzeichnis von Verarbeitungstätigkeiten führen | Audit-Logging verfolgt über 40 Ereignistypen auf Kontoebene: Authentifizierung, API-Tokens, Config-Store-Operationen und Lizenzierung. Export über `rdc audit` CLI oder Admin-Dashboard. |
| [Art. 32](https://gdpr-info.eu/art-32-gdpr/), Sicherheit der Verarbeitung | Angemessene technische Maßnahmen | LUKS2 AES-256-Verschlüsselung im Ruhezustand, Netzwerkisolation via iptables und separate Docker Daemons, Loopback-IP-Subnetze (/26) pro Repository. Der Config Store verwendet dreischichtige Verschlüsselung: zeitlich begrenzte SDK-Schlüssel, Split-Key-CEK-Ableitung (Passkey + Server-Geheimnis) und Organisations-Passphrase-Verschlüsselung. |
| [Art. 33](https://gdpr-info.eu/art-33-gdpr/), Meldung von Datenschutzverletzungen | 72-Stunden-Meldung mit forensischem Trail | Audit-Logs bieten einen forensischen Trail aller Operationen. Die Self-Hosted-Architektur begrenzt den Wirkungsradius auf einzelne Repositories. |

## Datenresidenz

CoW-Klone verlassen niemals die Quellmaschine. Der Befehl `rdc repo fork` erstellt eine Kopie auf Dateisystemebene mittels Reflinks. Es werden keine Daten über das Netzwerk übertragen.

Für maschinenübergreifende Operationen überträgt `rdc repo backup push/pull` Daten über SSH. Das Backup-Ziel empfängt LUKS-verschlüsselte Volumes, die ohne die Anmeldedaten des Operators nicht gelesen werden können.

## Umgebungskloning und Datenmaskierung

Beim Klonen von Produktionsumgebungen für Entwicklung oder Tests führt der Rediaccfile-Lebenszyklus-Hook `up()` Bereinigungsskripte nach dem Erstellen eines Forks aus: PII aus Datenbanken entfernen, echte E-Mail-Adressen durch Testadressen ersetzen, API-Tokens und Sitzungsdaten entfernen, Logdateien anonymisieren. Die Entwicklungsumgebung erhält die Produktionsstruktur ohne Produktionsidentitäten und erfüllt damit den Grundsatz der Datenminimierung ([Art. 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/)).

## Zero-Knowledge-Config-Store

Der optionale Config Store ermöglicht die Synchronisation von CLI-Konfigurationen über Geräte hinweg. Er ist so konzipiert, dass der Server keinerlei Kenntnis der Config-Inhalte hat:

- **Clientseitige Verschlüsselung**: Configs werden vor dem Upload mit AES-256-GCM verschlüsselt. Der Verschlüsselungsschlüssel (CEK) wird aus einem Passkey-PRF-Geheimnis und einem serverseitigen Geheimnis mittels HKDF mit Domain-Separation abgeleitet. Keine der beiden Parteien kann den Schlüssel allein ableiten.
- **Server sieht nur opake Blobs**: SSH-Schlüssel, Anmeldedaten, IP-Adressen, Netzwerktopologie. Nichts davon ist für den Server sichtbar. Nur Metadaten (Config-IDs, Versionen, Zeitstempel) werden im Klartext gespeichert.
- **Mitgliederzugang via X25519**: Wenn ein Teammitglied hinzugefügt wird, wird der CEK mit dessen X25519-Public-Key verschlüsselt und über den Server weitergeleitet. Der Server sieht den CEK niemals im Klartext.
- **Sofortiger Widerruf**: Das Entfernen eines Mitglieds löscht den gewrappten CEK und widerruft dessen Tokens. Zukünftige Configs verwenden neue SDK-Epochen, auf die das entfernte Mitglied keinen Zugriff hat.
- **Rotierende Tokens**: Die CLI-Authentifizierung verwendet rotierende Einmal-Tokens (3-Request-Toleranzfenster), IP-gebunden bei erster Nutzung, mit automatischem 24-Stunden-Ablauf.

Selbst eine vollständige Kompromittierung des Servers kann Config-Inhalte nicht offenlegen. Der Server hat niemals den Schlüssel.

Weitere Details finden Sie unter [Config Storage](/de/docs/config-storage).

## Datenverantwortlicher und Auftragsverarbeiter

Da Rediacc eine Self-Hosted-Software ist, ist Ihre Organisation sowohl Datenverantwortlicher als auch Auftragsverarbeiter. Rediacc (das Unternehmen) hat keinen Zugriff auf Ihre Daten, verarbeitet oder speichert sie nicht. Für das Self-Hosted-Produkt ist kein Auftragsverarbeitungsvertrag mit Rediacc erforderlich, da keine personenbezogenen Daten an Rediacc's Infrastruktur fließen.

Der Config Store ist die einzige Komponente, die Rediacc's Server berührt (zur Synchronisation), aber sein Zero-Knowledge-Design bedeutet, dass der Server nur verschlüsselte Blobs speichert, die er nicht entschlüsseln kann.
