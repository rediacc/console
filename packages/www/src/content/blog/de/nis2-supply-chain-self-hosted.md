---
title: "Article 21(2)(d) ist eine Anbieterfrage. Self-Hosting ist die Antwort, die Sie nicht mehr schulden."
description: "Warum das Drittanbieter-IKT-Register schrumpft, wenn die Datenebene Ihren Mandanten nie verlässt. Eine praxisnahe Lektüre von NIS2 Article 21(2)(d) für CISOs und Einkaufsverantwortliche, die 2026 DVAs neu verhandeln."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - supply-chain
  - self-hosted
  - sovereignty
  - compliance
featured: false
language: de
sourceHash: "98f0b752bc5dbd4d"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
translatedFrom: en
---

> **Zusammenfassung.** NIS2 Article 21(2)(d) macht das Lieferkettenrisiko zur Vorstandsfrage, nicht zur Fußnote im Einkauf. Die Richtlinie schreibt Self-Hosting nicht vor. Sie fragt jedoch, was sich in Ihrem Datenpfad befindet und was mit Ihnen geschieht, wenn einer dieser Anbieter einen schlechten Tag hat. Self-hosted-Infrastruktur kollabiert drei der vier Ebenen auf den meisten SaaS-Datenpfaden. Sie kollabiert nicht alle vier, und wer so tut als ob, begeht den Marketingfehler, der einen CISO vor dem Prüfer in Erklärungsnot bringt.
>
> - Der Richtlinientext und die ENISA-Leitlinien, klar und verständlich.
> - Der Vier-Ebenen-SaaS-Datenpfad, den die meisten Teams vergessen aufzuzeichnen.
> - Was das Zwei-Tool-Modell von Rediacc aus Ihrem Anbieterregister entfernt und was es dort belässt.
> - Eine Sechs-Fragen-Checkliste für Beschaffungsgespräche mit jedem Anbieter, der "NIS2-ready" behauptet.

Im Juli 2020 zahlte Blackbaud ein Lösegeld und informierte die Öffentlichkeit erst später. Das Unternehmen meldete mehr als 13.000 Kundenorganisationen nachträglich einen Vorfall, stand Class Actions in sieben Rechtssystemen gegenüber und zahlte am Ende $49,5 Millionen in Vergleichen mit Generalstaatsanwälten sowie eine SEC-Strafe von $3 Millionen wegen irreführender Offenlegungen. Jede einzelne dieser 13.000 Organisationen hatte einen Auftragsverarbeitungsvertrag (AVV) mit Blackbaud abgeschlossen. Die meisten hatten Blackbauds SOC-2-Bericht geprüft. Viele hatten Blackbaud in einem Anbieterrisiko-Register erfasst, mit Tier-Einstufung, Verlängerungsdatum und namentlich genanntem Verantwortlichen.

All das hat die Kaskade nicht aufgehalten. Die Daten lagen auf Blackbauds Seite der Grenze. Als ihre Backup-Umgebung kompromittiert wurde, waren alle Kundenorganisationen gleichzeitig betroffen.

NIS2 Article 21(2)(d) stellt eine schärfere Frage als "Haben Sie Ihren Anbieter geprüft?" Sie fragt, was sich im Datenpfad befindet und was mit Ihnen geschieht, wenn dieser Anbieter einen schlechten Tag hat. Die Antwort lautet für die meisten Teams: "Wir sind sie, und wir haben es nicht bemerkt."

Dieser Beitrag richtet sich an CISOs und Einkaufsverantwortliche, die 2026 AVVs neu verhandeln. Es ist die Datenpfad-Lektüre von Article 21(2)(d), keine Zertifizierungslektüre. Er ist auch ehrlich darüber, was Self-hosted-Infrastruktur nicht löst, denn der Abschnitt zu den Lücken ist genau das, was ein Prüfer ansprechen und eine Marketingbroschüre überspringen wird.

## Was Article 21(2)(d) tatsächlich verpflichtet

Der Richtlinientext lautet, leicht gekürzt zur Klarheit:

> "Die Mitgliedstaaten stellen sicher, dass wesentliche und wichtige Einrichtungen geeignete und verhältnismäßige technische, operative und organisatorische Maßnahmen ergreifen, um die Risiken für die Sicherheit der Netz- und Informationssysteme, die diese Einrichtungen für ihren Betrieb oder für die Erbringung ihrer Dienste nutzen, zu beherrschen [...] und zumindest Folgendes umfassen: [...] d) Sicherheit der Lieferkette einschließlich sicherheitsbezogener Aspekte der Beziehungen zwischen den einzelnen Einrichtungen und ihren unmittelbaren Anbietern oder Diensteanbietern"

Zwei Dinge in diesem Text sind für Einkäufer entscheidend.

Erstens liegt die Verpflichtung bei Ihnen, nicht beim Anbieter. Die Zertifizierungen des Anbieters, sein SOC 2, sein ISO 27001 sind Eingaben in Ihre Risikobeurteilung. Sie sind kein Ersatz dafür. Wenn Ihr Anbieter eine makellose Compliance-Haltung hat und trotzdem kompromittiert wird, wird die Behörde nach Ihrem Lieferantenrisikomanagement fragen, nicht nach seinem.

Zweitens reicht die Verpflichtung weiter als der Vertrag. ENISAs Umsetzungsleitlinien 2024, Anhang IV der Durchführungsverordnung (EU) 2024/2690 der Kommission, legen die erwartete Praxis fest: Führen Sie ein Register der IKT-Lieferanten, klassifizieren Sie diese nach Kritikalität, bewerten Sie jeden einzelnen auf das Risiko für Ihren Betrieb und die von ihm verarbeiteten Daten, und erneuern Sie die Bewertung in einem definierten Rhythmus. Anhang IV nennt ausdrücklich "die Lieferanten der Lieferanten" als relevant, was der Punkt ist, an dem die meisten Teams feststellen, dass ihr Anbieterregister eigentlich kein Register ist, sondern eine Vertragsliste mit einem Aufkleber.

Wer das aus der Einkaufsperspektive betrachtet, erhält folgende praktische Übersetzung: Jeder Anbieter mit logischem Zugriff auf Ihre Produktionsdaten muss erfasst, bewertet, überwacht und ersetzbar sein. "Ersetzbar" ist der Teil, der die meisten bestehenden Arrangements in Frage stellt.

## Der Vier-Ebenen-SaaS-Datenpfad, den die meisten Teams vergessen aufzuzeichnen

Setzen Sie sich mit einem Einkaufsverantwortlichen zusammen und gehen Sie durch, was passiert, wenn das Produkt eines Backup-Anbieters einen einzelnen Datensatz schreibt. Der ehrliche Datenpfad sieht von oben nach unten so aus:

1. Die **Anbieteranwendung.** Der Code, der Ihre Daten aufnimmt, Routing-Entscheidungen trifft und Geschäftslogik anwendet. Läuft auf der Infrastruktur des Anbieters. Wird vom Anbieter gewartet, gepatcht und überwacht.
2. Die **Anbieter-Cloud.** Die Hyperscaler-Region oder das eigene Rechenzentrum des Anbieters, in dem die Anwendung läuft. Speichervolumes, Netzwerk, IAM. Oft ein Hyperscaler, mit dem der Anbieter einen Unterauftragsverarbeitungsvertrag hat.
3. Die **Schlüsselverwaltung des Anbieters.** Die Verschlüsselungsschlüssel, die ruhende Daten in der Anbieter-Cloud schützen. In den meisten SaaS-Arrangements hält der Anbieter diese. "Kundenverwaltete Schlüssel" ist manchmal als Tier-Upgrade verfügbar; in diesen Arrangements liegen die Schlüssel dennoch in einem Hyperscaler-KMS, das das IAM des Anbieters aufrufen kann.
4. Die **Unterauftragsverarbeiter des Anbieters.** Die Drittanbieterdienste, die der Anbieter nutzt (CDN, Observability, Abrechnung, Kundensupport-Tools), die Ihre Daten oder daraus abgeleitete Metadaten übertragen oder speichern können.

Jede dieser vier Ebenen ist ein Eintrag in Ihrem Article-21(2)(d)-Lieferantenregister. Jede hat ihre eigene Vorfallhistorie, ihren eigenen Schadenradius bei einem Breach, ihre eigene Vertragsverhandlungsfläche. Wenn Sie beim SaaS-Anbieter verlängern, verlängern Sie alle vier implizit, weil der Vertrag des SaaS-Anbieters der einzige ist, den Sie verhandeln können.

Der Blackbaud-Vorfall war ein Layer-2-Breach (Anbieter-Cloud), der sich durch Layer 1 (Anbieteranwendung) ausbreitete und für jeden Kunden sichtbar wurde, weil Layer 3 (Schlüsselverwaltung des Anbieters, in diesem Fall serverseitige Schlüssel ohne mandantenübergreifende Trennung in der betroffenen Datenbank) keine Isolation bot. Die Unterauftragsverarbeiter von Blackbaud waren kein Angriffsvektor, aber Kunden erfuhren von drei davon, die sie nicht erfasst hatten.

## Blackbaud, Druva-artiger Schlüsselgewahrsam und das Kaskadiermuster

Drei Details aus den SEC-Einreichungen von Blackbaud sind für eine NIS2-Lektüre entscheidend.

Erstens hielt Blackbaud die Verschlüsselungsschlüssel für Kundendaten, einschließlich der Backup-Umgebung, die das Angriffsziel war. Kundenverwaltete Schlüssel waren nicht verfügbar. In der nachträglichen SEC-Litigation wurde dies als Kontrolldefizit charakterisiert, nicht als Verstoß, weil Blackbauds Verträge es erlaubten. Die NIS2-Perspektive auf dasselbe Arrangement nach Article 21(2)(d) ist schärfer, weil der Kunde das Risiko einer Kontrolle, in die er keine Einsicht hat, nicht sinnvoll bewerten kann.

Zweitens betraf der Breach Backup-Daten, die älter als die Live-Datenbank waren. Kundenorganisationen, deren Live-Daten bereits aus den Primärsystemen von Blackbaud gelöscht worden waren, hatten dennoch Daten über die Backup-Umgebung exponiert. Das ist das Kaskadiermuster: Eine Anbieterkompromittierung greift auf historische Daten zurück, von denen der Kunde dachte, sie seien bereits außerhalb des Geltungsbereichs.

Drittens erhielten mehr als 13.000 Kundenorganisationen Breach-Meldungen. Viele davon waren kleine gemeinnützige Organisationen und Schulen ohne operative Kapazität zur Reaktion, ohne DR-Runbook, ohne einen zweiten Backup-Anbieter zum Failover. Der Vorfall des Anbieters wurde in diesem Sinne ihr Vorfall.

Bei einem modernen SaaS-Backup im Druva-Stil ist die Architektur an manchen Stellen besser (mandantenübergreifende Schlüsseltrennung ist verbreiteter, BYOK ist bei höheren Tiers verfügbar), aber der Vier-Ebenen-Datenpfad ist identisch. Die Anbieteranwendung, die Anbieter-Cloud (typischerweise AWS), der Schlüsselgewahrsam (manchmal Anbieter, manchmal BYOK im Kunden-KMS, manchmal hybrid), die Unterauftragsverarbeiter. Ein Breach auf einer beliebigen Ebene erreicht alle Kunden gleichzeitig, weil sich die Daten aller Kunden auf derselben Seite der Grenze befinden.

Das ist das strukturelle Argument. Es ist kein Druva-Takedown. Druva führt einen strafferen Betrieb als Blackbaud es tat. Das Argument besagt, dass die Struktur jedes SaaS-by-design-Backup-Produkts Layer-2- und Layer-3-Breaches zu einer Verpflichtung nach Article 21(2)(d) macht, die der Kunde nicht sinnvoll erfüllen kann.

## Self-Hosting kollabiert drei der vier Ebenen

Rediacc ist anders aufgebaut. Die vollständige Architektur ist auf der [Architekturseite](/de/docs/architecture) dokumentiert, aber die lieferkettenrelevante Form sind zwei Binärdateien, die über SSH kommunizieren:

- `rdc` läuft auf der Workstation des Operators. Es liest eine flache JSON-Konfigurationsdatei (unter `~/.config/rediacc/`), verbindet sich über SSH mit den eigenen Maschinen des Operators und verteilt Befehle.
- `renet` läuft mit Root-Rechten auf dem eigenen Server des Operators und verwaltet LUKS-verschlüsselte Disk-Images, isolierte Docker-Daemons und den Reverse Proxy.

Der Operator meldet sich nie in der Infrastruktur von Rediacc als Unternehmen an, um ein Backup, eine Wiederherstellung oder einen Fork durchzuführen. Es gibt keine Rediacc-Unternehmens-Cloud im Datenpfad. Der LUKS-Credential des Repositories wird in der lokalen Konfigurationsdatei des Operators gespeichert (Modus `0600`), nie auf dem Server, nie an Rediacc übermittelt. Der Datenpfad sieht so aus:

1. **Workstation des Operators.** Führt `rdc` aus. Hält den LUKS-Credential.
2. **Eigener Server des Operators.** Führt `renet` aus. Hält die LUKS-verschlüsselten Repositories.
3. **Eigenes Backup-Ziel des Operators.** Jeder rclone-kompatible Speicher (S3, B2, OneDrive, On-Prem-MinIO). Empfängt verschlüsselte Volumes.

Es gibt keine Ebene 4. Rediacc als Unternehmen ist kein Unterauftragsverarbeiter für Operatoren, die nicht den experimentellen [Cloud-Adapter](/de/docs/architecture) nutzen. Für Self-hosted-Operatoren ist die Beziehung zu Rediacc als Unternehmen eine Softwarelizenz, kein Auftragsverarbeitungsvertrag.

Das ist das Datenpfad-Argument, und es ist das richtige Argument, um ein Gespräch über das Lieferantenregister zu eröffnen. Ein SaaS-Wettbewerber kann kundenverwaltete Schlüssel anbieten (die meisten modernen tun es). Ein SaaS-Wettbewerber kann nicht anbieten: "Wir sind kein Unterauftragsverarbeiter."

Der zweite Schritt, nachdem das Datenpfad-Argument angekommen ist, ist der Schlüsselgewahrsam. Bei Rediacc liegt der LUKS-Credential in der Konfigurationsdatei des Operators. Punkt. Es gibt kein Key Escrow, keinen Recovery-Dienst, den Rediacc als Unternehmen ausführen könnte, wenn der Operator den Credential verliert. Das ist auch die empfohlene Architektur für den [Zero-Knowledge-Konfigurationsspeicher](/de/docs/config-storage), bei dem der Verschlüsselungsschlüssel clientseitig aus einer Passkey-PRF-Erweiterung abgeleitet wird und der Server opake Blobs speichert. Der Server kann die SSH-Schlüssel, die LUKS-Credentials, die IP-Adressen oder irgendeine Klartext-Konfiguration nicht lesen. Das Rotieren des Zugangstokens gibt dem Server keinen rückwirkenden Lesezugriff.

Für Article 21(2)(h) (Verschlüsselung) ist das relevant. Für Article 21(2)(d) (Lieferkette) ist es relevanter, weil es den letzten logischen Zugangspfad von Rediacc als Unternehmen zu den Daten des Operators beseitigt.

## Was Self-Hosting nicht kollabiert

Self-Hosting verschiebt die Lieferantenliste, es löscht sie nicht. Drei Punkte, nach denen ein Prüfer noch fragen wird:

**1. Sie haben weiterhin Lieferanten, nur andere.** Den Hardware-Anbieter (Hetzner, Hostinger, OVH, Ihr Colo, Ihr eigenes Bare Metal). Den Hypervisor (KVM, VMware). Das Betriebssystem (Debian, Ubuntu, RHEL). Die Container-Registry (Docker Hub, GHCR, Ihre private Registry). Die Basis-Images, die Ihre Dienste beziehen. Jeder davon ist ein Article-21(2)(d)-Eintrag. Self-Hosting verschiebt die Lieferantenliste, es löscht sie nicht.

**2. Rediacc hat noch kein ISO 27001, SOC 2 oder BSI C5.** Diese befinden sich auf der Roadmap, liegen aber noch nicht vor. Für ein Einkaufsteam, das Zertifizierungen als Gating-Mechanismus nutzt, ist das eine echte Reibung. Die vertretbare Gegenantwort ist jene, die dieser Beitrag die ganze Zeit macht: Das Datenpfad-Argument bedeutet, dass das meiste, was diese Zertifizierungen bescheinigen (Sicherheitskontrollen in der Anbieter-Cloud, Management des Anbieterpersonalzugangs, Management von Unterauftragsverarbeitern), nicht im Geltungsbereich liegt, weil Rediacc als Unternehmen nicht im Datenpfad ist. Dieses Argument muss sorgfältig und vertretbar vorgebracht werden, nicht als Ersatz für Zertifizierungen, wenn Zertifizierungen das sind, was der Einkäufer benötigt.

**3. Die GRC-Ebene liegt weiterhin bei Ihnen.** Rediacc gibt dem Operator ein Hash-verkettetes Audit-Log mit 70+ Ereignissen (`rdc audit verify` validiert die Kette von Ende zu Ende). Es gibt Ihnen kein Lieferantenregister, kein Kontrollrahmenwerk und keinen Workflow zur Evidenzsammlung. Diese kommen weiterhin von Drata, Vanta, OneTrust oder einem der europäischen Anbieter. Der Begleitbeitrag [zur tatsächlichen Rechnung](/de/blog/nis2-the-real-bill) behandelt die Kostenstruktur dieser Komplementarität im Detail.

## Der AVV, den Sie nicht mehr verhandeln müssen

Um das zu konkretisieren: Hier ist eine "Vorher-Nachher"-Registerzeile aus einem echten Beschaffungsgespräch, anonymisiert. Der Einkäufer ist ein deutsches Fertigungsunternehmen mit 280 Mitarbeitern, klassifiziert als "wichtige Einrichtung" nach Anhang II. Der ursprüngliche Lieferantenregistereintrag für Backup sah so aus:

| Feld | Vorher |
|---|---|
| Anbieter | Acme Backup SaaS |
| Tier | Kritisch |
| Verarbeitete Daten | Produktionsdatenbank, Kunden-PII, Finanzdaten |
| Unterauftragsverarbeiter | AWS (eu-central-1), Datadog, Stripe, Zendesk |
| Vertragsstatus | AVV unterzeichnet 2023, SCCs beigefügt, Maßnahmenverzeichnis zuletzt überprüft Jan 2025 |
| Schlüsselgewahrsam | Vom Anbieter verwaltet (BYOK-Option nicht im aktuellen Tier) |
| Exit-Plan | "Anbieter erklärt sich bereit, Daten-Export im CSV-Format innerhalb von 30 Tagen nach Kündigung bereitzustellen" |
| Letzte Bewertung | 2025-Q1, Lücke beim Schlüsselgewahrsam festgestellt, auf Verlängerung vertagt |

Nach dem Wechsel zu Rediacc auf Hetzner:

| Feld | Nachher |
|---|---|
| Anbieter | (1) Rediacc OÜ, Softwarelizenz; (2) Hetzner, IaaS |
| Tier | (1) Nicht kritisch (keine Datenebene); (2) Kritisch (Datenebene, aber kundenkontrolliert) |
| Verarbeitete Daten | (1) Keine; (2) Verschlüsselte Volumes, Kunde hält Schlüssel |
| Unterauftragsverarbeiter | (1) Keine für Self-Hosted; (2) Nur Hetzner-intern, im Hetzner-AVV aufgelistet |
| Vertragsstatus | (1) Softwarelizenz, kein AVV erforderlich; (2) Hetzner-AVV + SCCs bereits vorhanden |
| Schlüsselgewahrsam | Kunde (LUKS-Credential in Operator-Konfiguration, nicht auf dem Server) |
| Exit-Plan | "rdc repo backup pull von einem beliebigen rclone-kompatiblen Ziel. Volumes sind LUKS-verschlüsselt; Operator hält Credential." |
| Letzte Bewertung | (2) durch bestehende IaaS-Bewertung abgedeckt |

Zwei Registereinträge statt einem. Der kritische Eintrag gilt für den IaaS-Anbieter, bei dem der Einkäufer bereits einen AVV und einen getesteten Exit-Plan hatte, weil IaaS eine Beziehung ist, die die meisten Teams zu managen wissen. Der Rediacc-Eintrag ist nicht kritisch, weil es sich um eine Softwarelizenz handelt, nicht um einen Auftragsverarbeitungsvertrag.

Das ist der strukturelle Grund, warum ein CISO weniger SaaS-Abhängigkeiten in der Datenebene anstrebt, auch wenn die Beschaffungskosten auf einer Tabellenkalkulation ähnlich aussehen. Der Registereintrag hat nicht dieselbe Form.

## Beschaffungs-Checkliste

Für jeden Anbieter, der in einem Verkaufsgespräch 2026 "NIS2-ready" behauptet, sechs Fragen:

**1. Wo liegt der Verschlüsselungsschlüssel für unsere ruhenden Daten?** Wenn die Antwort "in unserem HSM" oder "im KMS unseres Kunden, das wir über IAM aufrufen können" lautet, befindet sich der Anbieter in Ihrer Schlüsselgewahrsam-Kette. Wenn es "in Ihrer lokalen Konfigurationsdatei, nie auf unserer Infrastruktur" lautet, nicht.

**2. Wer in Ihrem Unternehmen kann unsere Daten technisch lesen, abgesehen von den rechtlichen Bedingungen?** Nicht "wer ist berechtigt", sondern "wer könnte es, wenn er wollte und das Audit-Log ausgeschaltet wäre". Wenn die Antwort nicht null ist, das ist Ihre Population für eine Insider-Risikobewertung.

**3. Wird die Wiederherstellung gegen einen echten Produktionsklon oder gegen synthetische Testdaten getestet?** Article 21(2)(c) und (e) zusammen gelesen verlangen, dass Backup tatsächlich wiederhergestellt werden kann. Ein Anbieter, der nur gegen synthetische Daten validiert, validiert keine Wiederherstellung, er validiert die Integrität der Backup-Datei. (Mehr dazu im Begleitbeitrag zur [kontinuierlichen Wirksamkeitsbewertung](/de/blog/nis2-effectiveness-without-theatre).)

**4. Zeichnet Ihr Audit-Trail die Art des Akteurs, Mensch oder Agent, hinter jeder Aktion auf?** KI-Agentenaktivität ist die am schnellsten wachsende Audit-Log-Kategorie. Ein Audit-Log aus 2026, das Mensch und Agent nicht unterscheidet, wird 2027 wie eine Lücke aussehen.

**5. Listen Sie jeden Unterauftragsverarbeiter auf, der logischen Zugriff auf unsere Daten hat, einschließlich Metadaten.** "Logischer Zugriff" ist die richtige Formulierung. "Logischer Zugriff einschließlich Metadaten" ist die bessere, weil Metadaten-only-Zugriff das ist, was Abrechnungs-, Observability- und Kundensupport-Unterauftragsverarbeiter typischerweise haben, und das reicht aus, um sensible Strukturen preiszugeben, auch wenn die Nutzlast verschlüsselt ist.

**6. Was ist Ihr Exit-Plan, wenn Sie 2027 von einem Nicht-EU-Käufer übernommen werden?** Der DSGVO-Angemessenheitsrahmen, der Cloud Act und FISA 702 sind alle bewegliche Ziele. Ein heutiger Datenresidenz-Anspruch eines Anbieters ist keine Garantie für drei Jahre später. Die Frage des Einkäufers ist, was mit dem Datenpfad passiert, wenn sich die Eigentümerschaft des Anbieters ändert.

Ein Anbieter, der alle sechs Fragen sauber beantwortet, ist ungewöhnlich. Ein Anbieter, der vier von sechs beantwortet und die anderen zwei offen anerkennt, ist vertrauenswürdiger als einer, der alle sechs selbstsicher beantwortet. Das Glaubwürdigkeitssignal ist die Bereitschaft, zu benennen, was nicht gelöst ist.

## Was das für den nächsten Verlängerungszyklus bedeutet

Wer in den nächsten zwölf Monaten eine Backup- oder DR-Verlängerung vor sich hat und Article 21(2)(d) auf der Beschaffungs-Scorecard steht, drei konkrete Schritte:

1. Zeichnen Sie den Vier-Ebenen-Datenpfad Ihres aktuellen Anbieters auf einem Whiteboard. Wenn Sie den dritten Unterauftragsverarbeiter nicht benennen können, haben Sie ein Registervollständigkeitsproblem, das vor NIS2 bestand, und die Verlängerung ist der richtige Moment, es zu beheben.
2. Wenden Sie die obige Sechs-Fragen-Checkliste auf Ihren bisherigen Anbieter an. Schicken Sie die Antworten an Ihren DSB und Ihren Prüfer und fragen Sie, ob die Lücken akzeptiert werden. Wenn die Lücken Ebene 3 (Schlüsselgewahrsam) oder Ebene 4 (nicht erfasste Unterauftragsverarbeiter) umfassen, ist das der Ansatzpunkt.
3. Schauen Sie, wie ein alternatives Lieferantenregister mit einer Self-hosted-Kontrollebene aussehen würde. Vergleichen Sie die Registereinträge, nicht die Lizenzkosten. Die Lizenzkosten sind innerhalb eines Faktors von zwei ähnlich; die Registereinträge haben eine andere Form. (Der Begleitbeitrag zu den [strukturellen Kosten des NIS2-Stacks](/de/blog/nis2-the-real-bill) geht durch, was kollabiert und was bleibt.)

Wenn wir die Alternative auf Ihrer Shortlist sind, ist das Angebot konkret. Schicken Sie uns Ihren Lieferantenfragebogen. Wir füllen ihn für eine deployed Instanz aus, mit unseren tatsächlichen Antworten auf Ihre Fragen, einschließlich der Lücken. Wenn Sie die Architektur vor dem Papierkram besprechen möchten, buchen wir eine 30-minütige Architekturüberprüfung mit dem Gründer. Der Weg zu einem vertretbaren Registereintrag ist keine glänzende Broschüre. Es sind die Antworten, einschließlich der unbequemen.

Die Zuordnung pro Artikel finden Sie unter [NIS2 und DORA](/de/docs/legal-nis2-dora). Den breiteren Rahmen finden Sie unter [Compliance-Übersicht](/de/docs/legal-overview). Für Datenresidenz, siehe [Datensouveränität](/de/docs/legal-data-sovereignty). Warum Self-Hosting wichtig ist, erklärt [On-Premise](/de/docs/on-premise).
