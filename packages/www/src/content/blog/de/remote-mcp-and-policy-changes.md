---
title: "Remote MCP: Ein Agent, der nur liest, was seine Person lesen darf"
description: "Remote MCP läuft auf den drei regionalen Workern. Ein Grant enthält den Schlüssel einer Config und die Policy-Schlüssel seiner Person, nie den Hauptschlüssel, und Tokens überleben den Grant nicht."
author: Rediacc
publishedDate: 2026-11-25
category: announcement
tags:
  - mcp
  - ai-agents
  - security
  - policy
featured: false
language: de
sourceHash: "ce8dbe4241a2d7ab"
sourceCommit: "dda643f43f9dadc19e08a84858e87f115d428f85"
---

> **Kurz gesagt.** Remote MCP gibt einem KI-Agenten eine URL statt eines Terminals. Die Designfrage war nie, wie sich der Agent verbindet, sondern was er nach der Verbindung sehen darf. Die Antwort: genau das, was die Person sieht, die den Grant angelegt hat, und nichts darüber hinaus.
>
> - Ein Grant erreicht **eine Config** und lebt in **einer Region**.
> - Tokens halten höchstens **1 Stunde** (Access) und **30 Tage** (Refresh) und nie länger als der Grant selbst.
> - Der Grant trägt den Inhaltsschlüssel einer Config und zwei **Policy-Lesesschlüssel**, nie den Hauptschlüssel des Config-Stores.
> - Das Format der Policy-Records hat sich geändert. Alte Records werden abgelehnt, einen Migrationspfad gibt es nicht.

## Eine URL statt einer Login-Shell

Der lokale MCP-Server (`rdc mcp serve`) läuft neben dem Agenten und erbt die Zugriffsrechte des Rechners, auf dem er läuft. Der Remote-Server funktioniert anders. Pro Region läuft ein MCP-Worker unter `mcp.<region>.rediacc.cloud`, und jeder Agent verbindet sich mit der URL genau eines Grants: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Tool-Aufrufe laufen auf dem Executor der Organisation, nicht auf dem Laptop einer Entwicklerin oder eines Entwicklers.

Interaktive Clients wie claude.ai melden sich über OAuth 2.1 mit PKCE an. Headless-Agenten senden ein Bearer-Token der Form `rmcp_<grantId>.<secret>`. Beide Formen identifizieren den Grant, die ID in der URL benennt ihn nur.

## Der Grant ist die Grenze

Ein Grant ist ein kleines, konkretes Objekt. Er nennt eine Config, ein Ablaufdatum und einen Scope: ein Read-only-Flag, eine Allowlist von Tools sowie Namensmuster für Maschinen und Repositories.

Aus dieser Form ergeben sich drei Regeln:

- **Eine Config.** Ein `tools/call`, der eine andere Config nennt, wird mit `REDIACC_GRANT_SCOPE` abgelehnt, bevor irgendetwas läuft. Wer drei Configs hat, legt drei Grants an.
- **Eine Region.** Grant-IDs beginnen mit ihrer Region. Eine Anfrage, die beim falschen Worker landet, wird mit HTTP 421 und der richtigen URL beantwortet und nie weitergeleitet.
- **Eine Laufzeit.** Ein Access-Token gilt so lange wie das Minimum aus 1 Stunde und der Restlaufzeit des Grants. Ein Refresh-Token gilt so lange wie das Minimum aus 30 Tagen und der Restlaufzeit des Grants. Jeder Refresh schlägt den Grant erneut nach, ein widerrufener Grant hört also beim nächsten Austausch auf zu funktionieren. Wird ein Refresh-Token zweimal vorgelegt, ist der Grant widerrufen.

Eine Grant-URL gilt standardmäßig 7 Tage, höchstens 30.

## Beurteilt wie die eigene Person

Interessant ist das Schlüsselmaterial. Ein Grant ist ein geteiltes Geheimnis. Der Browser zieht einen Zufallswert und zeigt ihn genau einmal an. Der Account-Server speichert nur einen Hash eines daraus abgeleiteten Tags, und der Executor leitet den Slot-Schlüssel nur ab, solange er beide Hälften hält. Der Slot-Schlüssel öffnet den Inhaltsschlüssel der Config, nie den Hauptschlüssel der Organisation.

Derselbe Slot-Schlüssel öffnet außerdem zwei **Policy-Schlüssel**. Die Policy, also die Autorisierungsregeln eines Config-Eintrags, liegt jetzt in einem eigenen Record, versiegelt unter einem Schlüssel, der aus dem Store-Schlüssel und dem Pointer des Records abgeleitet wird: Store, Config, Team und Schlüsselgeneration. Der Grant trägt den Schlüssel der Team-Config und den der Config auf Organisationsebene. Das sind genau die beiden Policy-Records, die seine Person liest, also liest sie der Executor ebenfalls.

Dadurch wird ein Agent wie seine Person beurteilt. Die Obergrenze ist die Organisations-Policy, eingeschränkt durch die Team-Policy. Der Agent handelt nur dort, wo ein menschliches Opt-in und diese Obergrenze es beide erlauben. Er kann keine Policy ändern, keine Secret-Werte lesen und seinen eigenen Grant nicht erweitern. Ein Schlüssel, den die Organisation sperrt, wird in einer Team-Policy ignoriert, und der Agent erlebt dieses Ergebnis genauso wie die Person.

Die Bindung jedes Schlüssels an einen Pointer hat einen erwähnenswerten Nebeneffekt. Wer einen Policy-Schlüssel hält, öffnet die Records dieses Pointers unter dieser Schlüsselgeneration und keine anderen. Ein Blob, der für einen anderen Store, eine andere Config oder ein anderes Team ausgeliefert oder unter einer anderen Version erneut eingespielt wird, besteht den Integritäts-Tag nicht.

## Was sich für bestehende Setups ändert

- **Policy-Records sind Version 2.** Ein Version-1-Record, der direkt unter dem Store-Schlüssel versiegelt war, lässt sich nicht öffnen. Das ist ein bewusster harter Schnitt.
- **Gehostete Schreibzugriffe unterliegen derselben Policy.** Config-Schreibzugriffe über den gehosteten Executor werden vor dem Speichern gegen die Policy-Obergrenze geprüft.
- **Lokale Agenten behalten dieselbe Obergrenze.** `REDIACC_ALLOW_CONFIG_EDIT` schaltet einen Agenten weiterhin für Config-Änderungen an den genannten Pointern frei, aber nur innerhalb dessen, was die Policy erlaubt.
- **Abgelaufene und rotierte Grants scheitern deutlich.** `initialize` und `tools/list` antworten weiterhin, und jeder Aufruf liefert `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` oder `REDIACC_KEY_ROTATED` mit einer `reauthUrl`.

Jeder Grant erlaubt 60 Aufrufe pro Minute und 5 gleichzeitig.

## Was eine geleakte URL bringt

Eine geleakte URL handelt als dieser Benutzer auf genau seiner einen Config, bis sie abläuft oder widerrufen wird. Sie öffnet keine andere Config der Organisation und nichts außerhalb des gehosteten Executors ihrer Region. Die Tool-Ausgabe erreicht allerdings den Modellanbieter, den der Benutzer anbindet. Rediacc wählt diesen Anbieter nicht aus.

Die Einrichtung steht in [MCP Server Setup](/de/docs/ai-agents-mcp), die Schlüsselstruktur im [Sicherheitsmodell](/de/docs/security-model).
