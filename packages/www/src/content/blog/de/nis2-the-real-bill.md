---
title: "Was uns Einkäufer im ersten NIS2-Prüfzyklus berichtet haben"
description: "Der Fünf-Tool-Compliance-Stack, den mittelständische wesentliche Einrichtungen 2026 still aufbauen, was eine selbst gehostete Control Plane zusammenführt und welche Posten in jedem Fall bei Ihnen bleiben."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - einkaufsführer
  - compliance
  - kosten
  - mittelstand
featured: false
language: de
sourceHash: "3fbb581ec14e3f80"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
translatedFrom: en
---

> **Kurzfassung.** Die NIS2-Erstprüfungen der deutschen Welle liegen hinter uns. Alle Einkäufer, mit denen wir seit Dezember gesprochen haben, beschreiben eine Variante desselben Stacks: fünf Tools, drei Verträge, zwei sich überschneidende Audit-Logs und eine Lücke, die sie nicht schließen können. Dieser Beitrag ist die strukturelle Version jener Gespräche. Was eine selbst gehostete Control Plane konsolidiert, was in jedem Fall im Budget bleibt und warum der richtige Rahmen für einen Verlängerungszyklus 2026 nicht "günstiger als Veeam" lautet, sondern "weniger Registereinträge, weniger Überschneidungen, dieselben Lücken ehrlich benannt."
>
> - Frontier Economics beziffert die EU-weiten NIS2-Compliance-Kosten auf EUR 31,2 Milliarden pro Jahr. Die Realität pro Organisation im Mittelstand: "Wir hatten bereits einen Security-Stack; NIS2 hat sichtbar gemacht, was fehlte."
> - Der Fünf-Tool-Stack: Backup, DR, Datenmaskierung oder Testdaten, Penetrationstest-Vertrag, GRC. Jeder Baustein deckt einen Teil ab. Keiner das Ganze.
> - Rediacc konsolidiert Backup, DR, Fork als Testdaten und Sofortwiederherstellung in einer Control Plane mit einem Audit-Log. GRC, Zertifizierungen, Schulungen, unternehmensweites MFA, Penetrationstests sowie SIEM und SOC werden nicht konsolidiert.
> - Die ehrliche "Bleibt bei Ihnen"-Tabelle ist der strukturelle Kern dieses Beitrags. Wer daraus schließt, Rediacc ersetze Drata, wird seinen Prüfer enttäuschen.

Im Dezember 2025 verschickte das BSI in Deutschland 47 formelle Bescheide an Einrichtungen, die nach seiner Einschätzung NIS2-pflichtig, aber noch nicht registriert waren. ANSSI in Frankreich startete eine parallele Initiative. ACN in Italien nahm Kontakt zu rund 2.000 Einrichtungen auf, die als nicht registriert galten. Die erste Welle mittelständischer wesentlicher und wichtiger Einrichtungen trat in ihren ersten NIS2-Prüfzyklus ein.

Wir haben seitdem mit etwa dreißig von ihnen gesprochen. Verschiedene Branchen, verschiedene Unternehmensgrößen, überwiegend Deutschland und Italien mit einigen aus den Niederlanden und Estland. Die Gespräche gleichen sich. Jedes Team hat einen Backup-Anbieter, einen DR-Plan, der möglicherweise nie getestet wurde, eine Staging-Lösung, die nur halb so solide ist wie behauptet, und ein Beschaffungsbudget, das genehmigt wurde, bevor NIS2 auf irgendjemandes Foliensatz stand.

Dieser Beitrag ist die strukturelle Version jener Gespräche. Was ein CFO oder Einkäufer 2026 tatsächlich unterzeichnet, was eine selbst gehostete Control Plane an der Rechnung verändert und wie die ehrliche Restkosten-Bilanz aussieht. Es ist bewusst kein TCO-Rechner. Die Einkäufer, mit denen wir sprechen, brauchen keine weitere Tabellenkalkulation; sie brauchen eine strukturelle Karte, wo das Geld hinfließt und welche Posten sich überschneiden.

Wer das Supply-Chain-Risikoargument hinter der These "Selbst hosten ist wichtig" sucht, findet es im [Begleitbeitrag zu Artikel 21(2)(d)](/de/blog/nis2-supply-chain-self-hosted). Wer das SRE-seitige Argument lesen möchte, warum jährliche Penetrationstests nicht mehr ausreichen, findet es im [Begleitbeitrag zur kontinuierlichen Wirksamkeit](/de/blog/nis2-effectiveness-without-theatre). Dieser Beitrag steht zwischen beiden, auf der Ebene des Budgetgesprächs.

## Die Makrozahl und was sie bedeutet und nicht bedeutet

Die Studie von Frontier Economics aus dem Jahr 2024 für die Europäische Kommission beziffert die direkten jährlichen Compliance-Kosten von NIS2 in der EU auf EUR 31,2 Milliarden. Die Zahl wird viel zitiert; sie wird auch oft falsch gelesen.

Die EUR 31,2 Milliarden verteilen sich auf rund 160.000 wesentliche und wichtige Einrichtungen. Pro Organisation liegt der Durchschnitt zwischen EUR 150.000 und EUR 250.000, wobei Branche und Unternehmensgröße den Großteil der Streuung erklären. Eine wesentliche Einrichtung im Mittelstand mit 250 Beschäftigten in der Fertigungs- oder Gesundheitsbranche liegt eher am oberen Ende dieser Spanne. Eine wichtige Einrichtung mit 60 Beschäftigten in einem weniger datenintensiven Sektor eher am unteren Ende.

Die eigenen Umsetzungskosten-Leitlinien der ENISA (Anhang IV der Durchführungsverordnung (EU) 2024/2690) stimmen mit der Frontier-Zahl überein, schlüsseln sie aber anders auf: etwa 35 bis 45 Prozent für Tooling, 30 bis 40 Prozent für Personal und Schulungen, 15 bis 20 Prozent für Zertifizierung und Prüfung, 5 bis 10 Prozent für Incident-Response-Retainer und Managed Services.

Was das für einen CFO bedeutet, der ein Budget für 2026 unterzeichnet: Die Tooling-Schicht beläuft sich im Mittelstand auf rund EUR 50.000 bis EUR 120.000 pro Jahr, abhängig davon, was bereits vorhanden ist. Durch diese Tooling-Schicht werden wir uns im Folgenden arbeiten.

Was es nicht bedeutet: dass der Kauf eines NIS2-fertigen Bundles das Problem löst. Die Personal- und Schulungsbudgets sowie die Zertifizierungskosten sind für die meisten Teams größer als das Tooling-Budget, und kein Tooling-Anbieter reduziert diese. Ein Anbieter, der eine 50-prozentige NIS2-Kostenreduktion verspricht, rechnet fast immer nur gegen den Tooling-Posten, nicht gegen die Gesamtprogrammkosten.

## Der Fünf-Tool-Stack, den Mittelstandsteams still aufgebaut haben

In neunzig Prozent der dreißig Einkäufergespräche sieht der Stack identisch aus. Fünf Kategorien, mit einem oder zwei namentlich genannten Anbietern pro Kategorie. Die Kategorienbezeichnungen sind stabil; die Anbieterauswahl variiert.

**1. Backup-Anbieter.** Veeam Data Platform Foundation oder Premium ist die häufigste Antwort. Cohesity DataProtect, Rubrik Security Cloud, Commvault, Acronis Cyber Protect bei kleineren Einrichtungen. Jahreskosten im Bereich von EUR 15.000 bis EUR 60.000 für den Mittelstand. Meist der älteste Budgetposten; besteht seit Jahren vor NIS2.

**2. DR-Standort oder DR-as-a-Service.** Entweder eine sekundäre Cloud-Region mit Runbook, eine Veeam Cloud Connect- oder Rubrik Cloud Vault-Instanz oder ein Vertrag mit einem Managed-DR-Anbieter. Jahreskosten EUR 8.000 bis EUR 35.000. In der Praxis selten getestet; das Runbook ist meistens eher Wunschdenken als operativ belastbar.

**3. Testdaten- oder Datenmaskierungs-Tool.** Delphix (jetzt Perforce DevOps Data) ist der Enterprise-Standard. Tonic.ai, Redgate Test Data Manager, gelegentlich ein selbst gebautes rsync-und-Maskierungs-Skript. Jahreskosten EUR 25.000 bis EUR 90.000 für lizenzierte Lösungen. Die meisten Teams in unseren Gesprächen haben diesen Posten nicht; sie verlassen sich auf ein Staging, das sie für ausreichend halten. Das Prüfgespräch zu Artikel 21(2)(e) bringt ihn ins Budget.

**4. Penetrationstest-Vertrag.** Ein Retainer bei einem Sicherheitstestunternehmen oder einer autonomen Plattform wie Pentera oder Horizon3.ai. Jahreskosten EUR 15.000 bis EUR 50.000 für autonome Tools, EUR 20.000 bis EUR 80.000 für menschengeführte Engagements. Die meisten Teams haben dies. Die meisten führen es ein- oder zweimal im Jahr durch.

**5. GRC-Plattform.** Drata, Vanta, OneTrust, AuditBoard, Hyperproof, DataGuard, Kertos. Bei den kleinsten Teams gelegentlich eine selbst gepflegte Tabellenkalkulation. Jahreskosten EUR 12.000 bis EUR 60.000. Genutzt für das Lieferantenregister, die Kontrollrahmen-Attestierung, die Beweissicherung und zunehmend für SOC 2- oder ISO-27001-Prüfungsunterstützung.

Fünf Posten, drei bis fünf namentlich genannte Anbieter, typischerweise EUR 75.000 bis EUR 295.000 pro Jahr vor Personal und Schulungen. Die Streuung ist groß, aber die Struktur ist konsistent.

Die fünf Verträge kommunizieren häufig nicht miteinander. Die Audit-Logs sind nicht vereinheitlicht. Die Exit-Pläne werden separat verfasst. Die Anbieterprüfungen werden separat durchgeführt, manchmal von verschiedenen Beschaffungsverantwortlichen. Das ist die strukturelle Form, die NIS2 unbequem macht.

## Wo die Überschneidungen liegen

Jede Kategorie im Stack überschneidet sich mit mindestens einer anderen.

**Backup überschneidet sich mit DR.** Moderne Backup-Anbieter behaupten alle, DR-fähig zu sein. Veeam Data Platform mit Cloud Connect ist ein DR-Produkt. Rubrik mit Cloud Vault ist ein DR-Produkt. Die beiden Posten bezahlen oft benachbarte Funktionen beim gleichen Anbieter. Einkäufer, die die Posten historisch nicht konsolidiert haben, hatten operative Gründe dafür (separate Teams, separate SLAs); unter der NIS2-Erwartung einer "einzigen Quelle der Wahrheit für die Wiederherstellung" verliert diese Begründung an Gewicht.

**Backup überschneidet sich mit Testdaten.** Veeam Instant Recovery, Rubrik Live Mount und Cohesity SmartFiles bieten alle eine Form von einbindbaren Backups für Testzwecke. Sie sind kein vollwertiger Delphix-Ersatz (die Maskierungsschicht ist separat, die Datenbankintegration flacher), aber für viele Testdaten-Anwendungsfälle ist das Backup-Tool bereits die halbe Lösung. Die meisten Teams erkennen das nicht.

**Penetrationstest überschneidet sich mit autonomem Testen.** Der Retainer-basierte menschengeführte Penetrationstest und das kontinuierliche Testen im Pentera-Stil werden manchmal als Alternativen, manchmal als Ergänzungen positioniert. In der Praxis zahlt ein Einkäufer mit beiden Optionen zweimal für benachbarte Fähigkeiten. Ein Einkäufer ohne beides hat eine Lücke nach Artikel 21(2)(f).

**GRC überschneidet sich mit allem.** Drata beansprucht Integration mit Backup, DR, Identität, Schwachstellenmanagement, Schulungen und Incident Response. Die Integrationstiefe variiert. Eine GRC-Plattform mit flacher Integration in ein Backup-Tool erzeugt Compliance-Nachweise, die nicht identisch mit den eigenen Nachweisen des Backup-Tools sind; Prüfer fragen zunehmend, welche Quelle als kanonisch gilt.

Die Überschneidungen sind keine Verschwendung. Sie sind die Folge eines Stacks, der über ein Jahrzehnt aufgebaut wurde, bevor NIS2 die Konsolidierungsfrage strukturell gemacht hat.

## Wo die Lücken liegen

Die Lücken sind interessanter als die Überschneidungen, denn die Lücken sind das, was NIS2 sichtbar macht.

**Patch-Validierung gegen echte Produktionsdaten.** Keine der fünf Kategorien löst das gut. Backup-Tools mounten das Backup; die gemountete Umgebung ist das wiederhergestellte Backup, nicht die aktuelle Produktion. Testdaten-Tools maskieren Produktionsdaten; die maskierte Umgebung ist in der Form realistisch, verliert aber die Konfigurationsunterschiede. Penetrationstest-Verträge testen, worauf sie gerichtet werden, und das ist in 90 Prozent der Fälle das Staging. Die Lücke zwischen "wir haben Tools" und "wir können einen CVE-Patch in unter einer Stunde gegen eine aktuelle produktionsäquivalente Umgebung testen" ist real und strukturell.

**Kontinuierliche Wirksamkeitsbewertung.** Der jährliche Rhythmus ist das, was die meisten Teams praktizieren. Artikel 21(2)(f) erwartet etwas Häufigeres. Keine der fünf Kategorien erzeugt standardmäßig wöchentliche oder zweiwöchentliche Nachweise. Der Einkäufer führt entweder benutzerdefinierte Übungen durch (selten, teuer) oder akzeptiert den Jahresrhythmus und hofft, dass der Prüfer ihn akzeptiert (was zunehmend nicht mehr der Fall ist).

**Kollaps des Lieferketten-Registers.** Jeder der fünf Anbieter ist ein eigener Registereintrag. Jeder trägt seinen eigenen AVV, SCCs, Unterauftragsverarbeiterliste und Exit-Plan. Das Register hat fünf Tier-1-Einträge, bevor Personal-Schulungs-Tools, Identitäts-Tools, Observability-Tools und IaaS hinzukommen. Das Lieferketten-Gespräch ist im NIS2-Sinne genauso ein Register-Management-Gespräch wie ein Sicherheitsgespräch. (Siehe den [Supply-Chain-Beitrag](/de/blog/nis2-supply-chain-self-hosted) für das strukturelle Argument.)

**Meldeworkflow nach Artikel 23.** Die 24-Stunden-Frühwarnung, die 72-Stunden-Meldung und der Ein-Monats-Bericht werden von keiner der fünf Kategorien automatisch erstellt. Sie erfordern ein SIEM, ein SOC (intern oder ausgelagert) und eine Person, die weiß, wie man beim nationalen CSIRT Meldung erstattet. Kleinere Teams haben das oft nicht. Der erste Vorfall ist die schmerzhafte Lernerfahrung.

## Was Rediacc konsolidiert

Rediacc ist eine Control Plane mit einem einheitlichen Audit-Log, die die Kernfunktionen von vier der fünf Kategorien für selbst gehostete Infrastruktur ersetzt.

**Backup** läuft in zwei Modi. Hot ist ein crash-konsistenter BTRFS-Snapshot. Kein Ausfallzeit. Cold macht einen Stop-Snapshot-Start-Zyklus. Beide planen auf systemd-Timern. Beide liefern an viele Ziele via rclone. Volumes sind LUKS-verschlüsselt. Der Betreiber hält den Schlüssel. Rediacc OÜ sieht niemals Klartext. Siehe [Backup & Restore](/de/docs/backup-restore) und [Cross Backup Strategy](/de/docs/cross-backup).

**DR**: Gleiche Primitive wie beim Backup, plus `rdc repo migrate` für maschinenübergreifende Datenbewegung, plus das Fork-Primitiv für den schnellen Aufbau des wiederhergestellten Zustands auf einer parallelen Maschine. Der DR-Standort kann eine andere Hetzner-Maschine, eine OVH-Maschine, ein On-Premises-Rack oder jeder andere per SSH erreichbare Standort sein. Kein DR-Anbieter-Cloud in der Datenpfad.

**Testdaten und Full-Stack-Klonen** läuft auf BTRFS-Reflink. Der Fork ist zeitkonstant, unabhängig von der Repository-Größe. Full-Stack bedeutet Daten, Konfigurationen, Container und Dienste. Ein 128-GB-Repository wurde in 7,2 Sekunden in unserem [PocketOS-Test](/de/blog/i-tested-rediacc-against-the-pocketos-incident) geforkt. Der Fork ist aktuelle Produktion, keine abgespeckte Staging-Kopie. Siehe [Risikofreie Upgrades](/de/docs/risk-free-upgrades).

**Sofortwiederherstellung**: `rdc repo backup pull` von einem beliebigen rclone-Ziel in einen frischen Fork, der unter einer Fork-spezifischen Subdomain bereitgestellt wird, die durch das Wildcard-Zertifikat des übergeordneten Repositorys abgedeckt ist. Kein DNS-Durcheinander, kein Zertifikatstanz.

**Einheitliches Audit-Log.** Mehr als 70 Ereignistypen über die gesamte Control Plane. Sie erfassen Anmeldungen, API-Token, Konfigurations-Writes, Repository-Lifecycle, Backup, Sync, Terminal-Sitzungen und Maschinenoperationen. Die Kette ist hash-verknüpft auf der Workstation des Betreibers. `rdc audit verify` prüft sie von Ende zu Ende.

Für eine wesentliche Einrichtung im Mittelstand mit 250 Beschäftigten bedeutet die Konsolidierung: von vier namentlich genannten Anbietern (Backup, DR, Testdaten, Sofortwiederherstellung) auf einen. Eine Lizenz, ein Audit-Log, ein Satz von Upgrade-Entscheidungen, ein Registereintrag.

Die fünfte Kategorie, GRC, wird nicht konsolidiert. Darauf kommen wir zurück.

## Was in jedem Fall bei Ihnen im Budget bleibt

Dies ist der Abschnitt, der bestimmt, ob der Rest des Beitrags ehrlich ist. Die zweispaltige Tabelle:

| Von Rediacc entfernt | Bleibt bei Ihnen, Posten für Posten |
|---|---|
| Backup-Anbieter-Lizenz | GRC-Plattform (Drata, Vanta, OneTrust, AuditBoard, DataGuard) für das Lieferantenregister, die Kontrollrahmen-Attestierung, die Beweissicherung und SOC-2- oder ISO-27001-Prüfungsunterstützung |
| DR-Standort-Vertrag oder DR-as-a-Service-Instanz | Zertifizierungsprüfungskosten (ISO 27001, SOC 2, BSI C5 falls benötigt; Rediacc selbst ist noch nicht zertifiziert, Sie tragen diese Kosten also vorerst) |
| Testdaten- oder Maskierungs-Tool-Lizenz | Personal-Schulungs- und Security-Awareness-Budget (NIS2 Artikel 21(2)(g)) |
| Sofortwiederherstellungs-Lizenz beim Backup-Anbieter | Unternehmensweite MFA-Lösung; Rediacc hat TOTP im Portal, keine unternehmensweite MFA-Plattform |
| | Penetrationstest-Vertrag oder autonome Testplattform; Rediacc liefert die Zielumgebung, nicht die Testfähigkeit |
| | SIEM und SOC für Erkennung und Meldung nach Artikel 23; Rediacc liefert forensisch-qualitative Artefakte, nicht die operative Meldeschicht |
| | IaaS-Anbieter (Hetzner, OVH, Ihr Colocation, Ihr Bare Metal); Rediacc läuft auf, nicht anstelle von, Infrastruktur |
| | Personal, das das Programm betreibt. Rediacc ist eine Tooling-Schicht, kein Sicherheitsteam |

Die rechte Seite der Tabelle ist länger als die linke. Das ist die ehrliche Form dessen, was NIS2 kostet. Das Entfernen der Backup-DR-Testdaten-Überschneidung spart echtes Geld und echte Registereinträge; es verwandelt ein Sicherheitsprogramm nicht in ein SaaS-Abonnement.

Wer diesen Beitrag liest und schlussfolgert "Ich kann Drata durch Rediacc ersetzen", wird seinen Prüfer enttäuschen. Die richtige Lesart: Die Datenebenen-Anbieter-Konsolidierung, die Rediacc ermöglicht, ist das, was GRC-Tools nicht können, und die Register-und-Nachweis-Arbeit, die GRC-Tools leisten, ist das, was Rediacc nicht macht. Die beiden ergänzen sich.

Drei weitere Links für mehr Tiefe. Die öffentliche Zuordnung finden Sie unter [NIS2 und DORA](/de/docs/legal-nis2-dora). Den übergreifenden Rahmen unter [Compliance-Übersicht](/de/docs/legal-overview). Die kommerzielle Seite von Rediacc unter [Abonnement und Lizenzierung](/de/docs/subscription-licensing).

## Ein Referenzszenario, strukturell nicht numerisch

Nehmen wir ein deutsches Fertigungsunternehmen mit 250 Beschäftigten. Einstufung als "wichtige Einrichtung" nach Anhang II. Produktionsdaten auf 4 bis 6 Servern, überwiegend selbst gehostet mit einem oder zwei SaaS-Tools (CRM, Lohnbuchhaltung). EUR 80 Mio. Jahresumsatz. Bestehendes Sicherheitsteam von 3 Personen.

**Vorher**, ihr Datenebenen-Stack:

- Veeam Data Platform Foundation, EUR 24.000/Jahr
- Veeam Cloud Connect für DR, EUR 12.000/Jahr
- Ein selbst gebautes rsync-plus-pg_dump-Schema für Testdaten, lizenzkostenfrei, aber kostet einen SRE alle zwei Wochen einen halben Tag
- Jährlicher Penetrationstest, EUR 22.000
- Drata für GRC, EUR 18.000/Jahr

Fünf Verträge. Zwei davon (Veeam, Veeam Cloud Connect) sind beim gleichen Anbieter, aber mit verschiedenen SKUs. Die Datenebenen-Posten summieren sich auf EUR 36.000/Jahr, ohne Penetrationstest oder GRC zu zählen. Das Team erstellt einen jährlichen Wiederherstellungstest, keine kontinuierlichen Wirksamkeitsnachweise und ein Lieferantenregister mit fünf Einträgen allein auf der Datenebenen-Seite.

**Nachher**, mit Rediacc auf Hetzner für die selbst gehosteten Workloads:

- Rediacc Business-Tier, EUR 8.400/Jahr (deckt ihre Repository-Größe ab)
- Hetzner IaaS für primären und sekundären Standort, EUR 9.600/Jahr kombiniert (bereits im Budget; kein neuer Posten)
- Der Penetrationstest-Vertrag bleibt (EUR 22.000)
- Drata bleibt (EUR 18.000)
- Das selbst gebaute Testdaten-Schema wird abgelöst; der halbe SRE-Tag alle zwei Wochen fließt stattdessen in die wöchentliche Wirksamkeitsroutine

Datenebenen-Konsolidierung: 5 Posten auf 1 (Rediacc) plus die bestehende IaaS-Zeile. Der Datenebenen-Abschnitt des Lieferantenregisters sinkt von 5 auf 2 Einträge. Die kontinuierliche Wirksamkeitsgeschichte besteht jetzt aus wöchentlichen Übungen mit hash-verketteten Audit-Log-Nachweisen; die Wiederherstellungstest-Geschichte wird jetzt durch `rdc machine backup status`-Ausgabe und eine wöchentliche Restore-Übung untermauert.

Die Zahlen sind illustrativ, keine Versprechen. Ihr Stack ist anders. Die Form, vier bis fünf Posten, die sich zu einem plus bestehender IaaS-Zeile zusammenführen, ist das, wie ein echtes Einkäufergespräch aussieht.

## Ein Hinweis darauf, was dies nicht ist

Dieser Beitrag ist kein Veeam-Angriff und kein TCO-Rechner. Veeam hat aus guten Gründen den größten VM-Backup-Marktanteil in Europa; das Produkt ist ausgereift, das Partnernetzwerk ist breit, das NIS2-Marketing ist stark, und ein Einkäufer, der sich 2026 für Veeam entscheidet, macht keinen Fehler. Die Zahlen im Referenzszenario sind illustrativ, aus echten Einkäufergesprächen gewonnen, keine Benchmarks. Führen Sie die strukturelle Analyse gegen Ihre eigenen Verträge durch.

Was dies ist: eine einkäuferseitige Einordnung für einen CFO, der in den nächsten zwölf Monaten einen Backup-, DR- oder Compliance-Vertrag neu verhandelt und wissen möchte, was eine selbst gehostete Control Plane an den Posten verändert.

## Was als nächstes zu tun ist

Wenn Sie in einen Verlängerungszyklus eintreten und das Budget offen ist, drei konkrete Schritte:

1. **Ziehen Sie die drei größten Sicherheits- und Infrastrukturposten des Vorjahres.** Senden Sie diese an Ihren DSB, Ihren CISO und Ihren Prüfer. Fragen Sie, welche davon bereits redundant waren, bevor NIS2 es sichtbar machte. Die meisten Teams finden mindestens eine Überschneidung, für die sie bezahlt haben.
2. **Ordnen Sie Ihren aktuellen Datenebenen-Stack den fünf Kategorien oben zu.** Notieren Sie, für welche Kategorien Sie einen Anbieter haben, für welche zwei und für welche keinen. Die "Kein Anbieter"-Felder sind die Lücken, die NIS2 sichtbar machen wird.
3. **Führen Sie die Lieferantenregister-Übung aus dem [Supply-Chain-Beitrag](/de/blog/nis2-supply-chain-self-hosted)** für jeden Datenebenen-Anbieter durch. Zählen Sie die Registereinträge. Die Zahl ist meistens höher, als das Team erwartet hat.

Wenn wir auf der engeren Auswahl stehen, ist das Angebot konkret. Senden Sie Ihre drei größten Posten aus dem letztjährigen Sicherheits- und Infrastrukturbudget. Wir sagen Ihnen schriftlich innerhalb einer Woche, welche davon konsolidiert werden können und welche nicht. Die Antwort enthält die Lücken, denn das Benennen der Lücken ist das, was den Rest der Antwort vertrauenswürdig macht.

Drei weitere Dokumente für mehr Tiefe. [Kostenfreies Backup](/de/docs/zero-cost-backup) erklärt, warum wir auf der Speicherseite leichter laufen als die etablierten Anbieter. [Cross Backup Strategy](/de/docs/cross-backup) behandelt interkontinentales DR. [Abonnement und Lizenzierung](/de/docs/subscription-licensing) ist die kommerzielle Seite.
