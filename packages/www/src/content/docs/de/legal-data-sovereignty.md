---
title: "Datenhoheit"
description: "Wie die Self-Hosted-Architektur von Rediacc die Anforderungen an Datenresidenz und Datenhoheit über globale Jurisdiktionen hinweg erfüllt."
category: "Legal"
order: 7
language: de
sourceHash: "72bbd6b951067a1d"
---

Viele Länder verlangen, dass personenbezogene Daten ihrer Bürger innerhalb der Landesgrenzen gespeichert und verarbeitet werden. Die Self-Hosted-Architektur von Rediacc erfüllt diese Anforderungen von Natur aus: Daten verbleiben auf Ihrer Maschine, in Ihrem Rechenzentrum, in Ihrer Jurisdiktion. Keine Daten verlassen die Maschine während des Klonings, und kein Drittanbieter-SaaS verarbeitet Ihre Daten.

## Warum Self-Hosting Datenhoheit löst

Grenzüberschreitender Datentransfer ist das schwierigste Compliance-Problem im Cloud Computing. Jede Jurisdiktion hat unterschiedliche Regeln, Angemessenheitsentscheidungen und Übertragungsmechanismen. Self-Hosting eliminiert die gesamte Kategorie:

- **Kein grenzüberschreitender Transfer**: CoW-Kloning (`cp --reflink=always`) dupliziert Daten auf derselben Maschine
- **Kein Drittanbieter-Verarbeiter**: Rediacc läuft auf Ihrer Infrastruktur, nicht auf Rediacc's Servern
- **Keine Angemessenheitsbewertung nötig**: Daten verlassen nie die Jurisdiktion, daher gelten Transferregeln nicht
- **Keine Standardvertragsklauseln**: Es gibt keinen internationalen Datenfluss zu regulieren

## Jurisdiktionsabdeckung

### Europäische Union

Die [DSGVO](https://gdpr-info.eu/) beschränkt die Übertragung personenbezogener Daten außerhalb der EU/des EWR, es sei denn, das Zielland bietet angemessenen Schutz. Das Schrems-II-Urteil machte den EU-US Privacy Shield ungültig, und die [Strafe von 1,2 Mrd. EUR gegen Meta](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) zeigte die Kosten fehlerhafter grenzüberschreitender Transfers.

Self-Hosted Rediacc in der EU hält alle Daten innerhalb der EU. Kein Übertragungsmechanismus erforderlich. Siehe [DSGVO-Konformität](/de/docs/legal-gdpr) für Artikelzuordnung.

### China

Das [Gesetz zum Schutz personenbezogener Daten (PIPL)](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) verlangt die Speicherung personenbezogener Daten chinesischer Bürger in China. Grenzüberschreitende Transfers erfordern Sicherheitsbewertungen durch die Cyberspace Administration of China (CAC). Self-Hosted Rediacc auf chinesischer Infrastruktur vermeidet CAC-Sicherheitsbewertungen vollständig.

### Brasilien

Das [LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) verlangt angemessene Sicherheitsmaßnahmen und beschränkt internationale Transfers. Self-Hosting in Brasilien eliminiert Transferbedenken und erfüllt die technischen Maßnahmenanforderungen des Art. 46 durch LUKS2-Verschlüsselung und Netzwerkisolation.

### Indien

Das [DPDP Act (2023)](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023) beschränkt Transfers auf Länder, die nicht auf einer staatlich genehmigten Liste stehen. Self-Hosting auf indischer Infrastruktur bedeutet keinen Transfer, unabhängig davon, welche Länder auf die schwarze Liste gesetzt werden. Indiens Regierungs- und Verteidigungssektoren bevorzugen stark On-Premises-Lösungen.

### Türkei

Das [KVKK (Gesetz Nr. 6698)](https://kvkk.gov.tr/en/) beschränkt internationale Transfers mit komplexen Angemessenheitsanforderungen. Die Türkei steht nicht auf der EU-Angemessenheitsliste, sodass grenzüberschreitende Transfers eine ausdrückliche Genehmigung erfordern. Self-Hosting in der Türkei eliminiert dies vollständig.

### Südkorea

Das [PIPA](https://www.pipc.go.kr/eng/index.do) ist eines der weltweit strengsten und schreibt ausdrücklich die Verschlüsselung personenbezogener Daten bei Speicherung und Übertragung vor. LUKS2 AES-256 erfüllt diese Anforderung direkt. Strafen von bis zu 3% des Umsatzes.

### Japan

Das [APPI](https://www.ppc.go.jp/en/legal/) beschränkt grenzüberschreitende Transfers, es sei denn, das Empfängerland bietet angemessenen Schutz. Self-Hosting in Japan vermeidet Transferbeschränkungen und entspricht der kulturellen Marktpräferenz für On-Premises-Lösungen.

### Australien

Das [Privacy Act 1988](https://www.legislation.gov.au/C2004A03712/latest/text) macht die offenlegende Einheit für den Umgang des ausländischen Empfängers mit Daten verantwortlich (APP 8). Self-Hosting eliminiert diese Haftung vollständig. LUKS2-Verschlüsselung und Netzwerkisolation bieten konkrete "angemessene Schritte" unter APP 11.

### Vereinigte Arabische Emirate

Das [Bundesdekret Nr. 45/2021](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws) verlangt angemessene Sicherheitsmaßnahmen und beschränkt grenzüberschreitende Transfers. Die Regierungs- und Finanzsektoren der VAE bevorzugen stark On-Premises-Bereitstellungen.

### Saudi-Arabien

Das [PDPL](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) verlangt, dass personenbezogene Daten saudischer Einwohner innerhalb Saudi-Arabiens gespeichert und verarbeitet werden. Self-Hosting erfüllt diese strenge Lokalisierungsanforderung direkt.

### Singapur

Das [PDPA](https://sso.agc.gov.sg/Act/PDPA2012) verlangt angemessene Sicherheit und beschränkt grenzüberschreitende Transfers. Self-Hosting in Singapur, einem wichtigen APAC-Datenhub, erfüllt regionale Compliance für ASEAN-Operationen.

### Russland

Das [Bundesgesetz 242-FZ](https://pd.rkn.gov.ru/) verlangt die Speicherung personenbezogener Daten russischer Bürger auf Servern in Russland. Verstöße können zu Website-Sperren führen. Self-Hosting auf russischem Boden bietet Compliance durch Architektur.

## Das Muster

Über alle Jurisdiktionen hinweg ist die Compliance-Gleichung identisch:

| Eigenschaft | Cloud/SaaS | Self-Hosted Rediacc |
|-------------|-----------|-------------------|
| Datenspeicherort | Rechenzentren des Anbieters (können Grenzen überschreiten) | Ihre Maschine, Ihre Jurisdiktion |
| Übertragungsmechanismus nötig | Ja (SCCs, Angemessenheit, Einwilligung) | Nein (kein Transfer findet statt) |
| Drittanbieter-Verarbeiter-Haftung | Ja | Nein |
| Verschlüsselungskontrolle | Vom Anbieter verwaltete Schlüssel | Ihre LUKS-Anmeldedaten, lokal gespeichert |
| Kloning-/Staging-Daten | Können Grenzen überschreiten oder Ihrer Kontrolle entgleiten | CoW auf derselben Maschine, derselben Jurisdiktion |
