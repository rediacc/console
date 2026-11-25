---
title: Sicherheitsmodell
description: Wer im Konfigurationsspeicher was sehen kann, wie Schlüssel abgegrenzt sind, worauf Agenten und Remote-MCP zugreifen können und was sich wiederherstellen lässt.
category: Guides
tags:
  - security
  - account
subcategory: account
order: 14
language: de
sourceHash: "bd31f15e75569945"
sourceCommit: "45ae253620c97f781ac426d3a84bca6b9a8bc528"
---

# Sicherheitsmodell

Diese Seite beschreibt, was der Konfigurationsspeicher schützt, welcher Schlüssel was öffnet und worauf jede Art von Aufrufer zugreifen kann. Die Einrichtung steht unter [Konfigurationsspeicher](/de/docs/config-storage), Sitzungen und Token unter [Kontosicherheit & API-Schlüssel](/de/docs/account-security).

## Wer was sehen kann

Eine gespeicherte Konfiguration ist dreifach verschlüsselt. Die SDK-Schicht und die Schicht der Organisations-Passphrase werden vom Server verwaltet. Die mittlere Schicht ist der Content Encryption Key (CEK), den nur Inhaber eines Key-Slots entsperren können: Ein Slot-Geheimnis auf dem Gerät wirkt mit einem Geheimnis auf dem Server zusammen, und keine der beiden Hälften öffnet ihn allein.

| Angreifer besitzt | Sieht Konfigurationsinhalt | Grund |
|---|---|---|
| Nur eine Datenbankkopie | Nein | Konfigurations-Blobs liegen im Objektspeicher, nicht in der Datenbank |
| Datenbank und Objektspeicher | Nein | Die Schicht der Organisations-Passphrase braucht das Worker-Geheimnis, die CEK-Schicht ein Slot-Geheimnis |
| Eine vollständige Server-Kompromittierung | Nicht ohne Slot-Geheimnis | Die Server-Schichten fallen, aber der CEK bleibt hinter der Passkey-PRF-Ausgabe oder dem 160-Bit-Wiederherstellungs-Kit, und keines von beiden ist erratbar |
| Das Gerät eines entfernten Mitglieds | Was bereits abgerufen wurde | Spätere Versionen bleiben nach einer CEK-Rotation verschlossen |
| Eine durchgesickerte Agent-URL | Eine Konfiguration, als dieser Benutzer | Siehe [Agenten und Remote-MCP](#agents-and-remote-mcp) |

Der Server sieht weiterhin Metadaten (Konfigurations-IDs, Teams, Versionen, Zeitstempel, Blob-Größen) und kann Anfragen ablehnen, verzögern oder löschen. Wer bösartigen Portal-Code ausliefert, kann Schlüssel im Browser auslesen. Jeder Blob ist an Speicher, Konfiguration, Team und Version gebunden, deshalb kann der Server keinen Blob unbemerkt austauschen oder ändern, und die CLI lehnt jede Version ab, die älter ist als eine bereits gesehene.

## Schlüsselbereiche

- Ein Konfigurationsspeicher pro Organisation und ein CEK pro Speicher. Teams sind serverseitige Zugriffskontrolle, keine kryptografische Isolation: Ein Wiederherstellungs-Kit oder Key-Slot öffnet den CEK der gesamten Organisation.
- Key-Slots sind je Speicher, Benutzer und Methode eindeutig, daher gibt es pro Benutzer und Organisation ein Wiederherstellungs-Kit. Wer in zwei Organisationen ist, hat zwei Kits, und es gibt kein Team-Kit.
- Ein Maschinengeheimnis gilt pro Maschine und Organisation und bindet eine Headless-Maschine ein.
- Jede Konfiguration hat unter dem CEK ihren eigenen Inhaltsschlüssel. Eine Agent-Freigabe enthält den Inhaltsschlüssel genau einer Konfiguration, daher lässt sich damit keine andere Konfiguration der Organisation öffnen.
- Die Autorisierungsrichtlinie jeder Konfiguration ist ein eigener Datensatz unter einem Schlüssel, der aus dem CEK und dem Zeiger des Datensatzes abgeleitet wird. Wer einen Richtlinienschlüssel besitzt, öffnet nur die Datensätze dieses Zeigers.

## Agenten und Remote-MCP

Eine Agent-Freigabe ist der Schlüsselinhaber-Typ hinter einer Remote-MCP-URL. Sie enthält den Inhaltsschlüssel einer Konfiguration sowie die Richtlinienschlüssel der Team-Konfiguration der Freigabe und der Konfiguration auf Organisationsebene, aber nie den CEK. Ein Agent liest also genau das, was die zugehörige Person liest.

- **Lebensdauer.** Eine URL gilt standardmäßig 7 Tage und höchstens 30 Tage, danach läuft sie ab oder wird widerrufen. Eine abgelaufene Freigabe wird abgelehnt, und der Client autorisiert neu.
- **Umfang.** Eine Freigabe erreicht eine Konfiguration und gehört zu einer Region (eu, us oder asia). Eine URL, die bei einer anderen Region vorgelegt wird, wird mit Nennung der richtigen Region abgelehnt und nie weitergeleitet. On-Premise-Installationen bestehen aus einer einzigen Region.
- **Richtlinie.** Ein Agent handelt nur dort, wo ein menschliches Opt-in und die Richtlinienobergrenze es beide erlauben. Die Obergrenze ist die Organisationsrichtlinie, eingeschränkt durch die Teamrichtlinie. Ein Agent kann weder die Richtlinie bearbeiten noch Geheimniswerte lesen noch seine eigene Freigabe erweitern.
- **Schadensradius.** Eine durchgesickerte URL handelt als dieser Benutzer auf ihrer einen Konfiguration, bis sie abläuft oder widerrufen wird. Außerhalb des gehosteten Executors ihrer Region öffnet sie nichts.

Die Tool-Ausgabe erreicht den Modellanbieter, den der Benutzer verbindet. Diesen wählt Rediacc nicht aus.

### On-Premise

Es gibt keine Cloudflare-Komponente im Pfad. Die Worker-Geheimnisse der Cloud werden zu Umgebungsvariablen oder Konfiguration auf dem Kundenhost, daher ersetzt der Hostzugriff die Worker-Geheimnis-Grenze aus der Tabelle oben, und Tool-Aufrufe laufen auf dem eigenen Daemon-Executor des Kunden.

## Richtlinie

Die Richtlinie ist ein eigener Datensatz, pro Konfigurationseintrag versiegelt, mit authentifizierten Daten, die Speicher, Konfiguration, Team, Version und Schlüsselgeneration binden. Der Server kann ihn nicht lesen, und ein wiedereingespielter oder vertauschter Datensatz scheitert an seinem Integritäts-Tag. Richtliniendatensätze der Version 1 werden abgelehnt.

Die Organisationsrichtlinie schreibt nur ein Organisationsinhaber oder -admin, und die Richtlinie eines Teams nur ein Team-Admin (oder ein Inhaber oder Admin). Ein Schreibzugriff erfordert 2FA und eine erhöhte Sitzung, und einen gebundenen Passkey, wenn der Speicher Passkeys verlangt. Jedes Mitglied und jeder Executor, der es bedient, liest die Richtlinie. Ein Schlüssel, den die Organisation sperrt, wird in einer Teamrichtlinie ignoriert.

## Was sich wiederherstellen lässt

| Situation | Wiederherstellung |
|---|---|
| Passkey verloren | Mit dem Wiederherstellungs-Kit entsperren, dann einen neuen Passkey registrieren |
| Kit verloren | Über einen funktionierenden Passkey neu erzeugen; der alte Ausdruck wird ungültig |
| Beides verloren | Ein Inhaber oder Admin fügt das Mitglied über die Mitglieder-Übergabe erneut hinzu |
| Letzter Schlüsselinhaber verliert beides | Nicht wiederherstellbar, deshalb wird ein zweiter Schlüsselinhaber empfohlen |
| Mitglied entfernt | Seine Slots und Token verfallen sofort; eine CEK-Rotation verschließt spätere Versionen vor einem Schlüssel, den es behalten hat |
| CEK-Rotation | Verpackt den CEK unter einer neuen Generation neu und macht jedes Wiederherstellungs-Kit ungültig |

Der Server lehnt das Löschen eines Slots, das Entfernen eines Mitglieds oder das Verlassen durch ein Mitglied ab, wenn danach weniger als zwei Schlüsselinhaber und kein Wiederherstellungs-Slot übrig wären. Jedes Mitglied erhält bei der Einrichtung ein verpflichtendes Wiederherstellungs-Kit, und dessen Aufbewahrung liegt in der Verantwortung des Mitglieds.
