---
title: "Kaug-MCP: agent, mis loeb ainult seda, mida tema inimene loeb"
description: "Kaug-MCP töötab kolmel piirkondlikul Workeril. Grant kannab ühe konfi võtit ja oma inimese poliitikavõtmeid, mitte kunagi peavõtit, ning ükski token ei ela grantist kauem."
author: Rediacc
publishedDate: 2026-11-25
category: announcement
tags:
  - mcp
  - ai-agents
  - security
  - policy
featured: false
language: et
sourceHash: "ce8dbe4241a2d7ab"
sourceCommit: "dda643f43f9dadc19e08a84858e87f115d428f85"
---

> **Lühidalt.** Kaug-MCP annab tehisintellekti agendile terminali asemel URL-i. Disainiküsimus polnud kunagi see, kuidas agent ühendada, vaid see, mida ta pärast ühendamist näha tohib. Vastus: täpselt seda, mida näeb grandi loonud inimene, ja mitte midagi enamat.
>
> - Grant ulatub **ühe konfini** ja elab **ühes piirkonnas**.
> - Tokenid kestavad kuni **1 tund** (juurdepääs) ja **30 päeva** (uuendus), ega kunagi kauem kui grant ise.
> - Grant kannab ühe konfi sisuvõtit ja kahte **poliitika lugemisvõtit**, mitte kunagi konfihoidla peavõtit.
> - Poliitikakirjete vorming muutus. Vanad lükatakse tagasi ja migratsiooniteed pole.

## URL, mitte sisselogimiskest

Kohalik MCP-server (`rdc mcp serve`) töötab agendi kõrval ja pärib selle masina juurdepääsu, kus ta jookseb. Kaugserver on teistsugune. Igas piirkonnas töötab üks MCP Worker aadressil `mcp.<region>.rediacc.cloud` ning iga agent ühendub ühe grandi URL-iga: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Tööriistakutsed jooksevad organisatsiooni täitjal (executor), mitte arendaja sülearvutis.

Interaktiivsed kliendid nagu claude.ai logivad sisse OAuth 2.1 ja PKCE abil. Peata agendid saadavad `rmcp_<grantId>.<secret>` kujulise bearer-tokeni. Mõlemad vormid tuvastavad granti, URL-is olev id ainult nimetab seda.

## Piir on grant ise

Grant on väike ja konkreetne objekt. Ta nimetab ühe konfi, aegumise ja ulatuse: kirjutuskaitse lipu, lubatud tööriistade nimekirja ning masinate ja hoidlate nimemustrid.

Sellest vormist tulenevad kolm reeglit:

- **Üks konf.** `tools/call`, mis nimetab teist konfi, lükatakse tagasi koodiga `REDIACC_GRANT_SCOPE`, enne kui midagi jookseb. Kellel on kolm konfi, see volitab kolm granti.
- **Üks piirkond.** Grandi id-d algavad piirkonnaga. Valele Workerile jõudnud päring saab HTTP 421 vastuse õige URL-iga ega edasta kunagi edasi.
- **Üks eluiga.** Juurdepääsutoken kestab lühema ajani 1 tunni ja grandil järelejäänud aja vahel. Uuendustoken kestab lühema ajani 30 päeva ja grandil järelejäänud aja vahel. Iga uuendus vaatab grandi uuesti üle, nii et tühistatud grant lakkab töötamast järgmisel vahetusel. Uuendustokeni kaks korda esitamine tühistab grandi.

Grandi URL kehtib vaikimisi 7 päeva, kõige rohkem 30.

## Hinnatud nagu tema inimest

Huvitav osa on võtmematerjal. Grant on jagatud saladus. Brauser loosib juhusliku väärtuse ja näitab seda ainult ühe korra. Kontoserver hoiab vaid sellest tuletatud sildi räsi ning täitja tuletab pesavõtme ainult nii kaua, kui tal on mõlemad pooled. Pesavõti avab konfi enda sisuvõtme, mitte kunagi organisatsiooni peavõtit.

Sama pesavõti avab ka kaks **poliitikavõtit**. Poliitika ehk konfikirje autoriseerimisreeglid elab nüüd omaette kirjes, mis on pitseeritud hoidlavõtmest ja kirje osutist tuletatud võtmega: hoidla, konf, tiim ja võtme põlvkond. Grant kannab oma tiimikonfi võtit ja organisatsioonitaseme konfi võtit. Need on kaks poliitikakirjet, mida tema inimene loeb, nii et täitja loeb samu kahte.

Tulemus: agenti hinnatakse nagu tema inimest. Lagi on organisatsiooni poliitika, mida tiimi poliitika kitsendab. Agent tegutseb ainult seal, kus nii inimese nõusolek kui see lagi seda lubavad. Ta ei saa poliitikat muuta, saladuste väärtusi lugeda ega oma granti laiendada. Võti, mille organisatsioon lukustab, ignoreeritakse tiimipoliitikas ning agent kohtab seda tulemust samamoodi nagu inimene.

Iga võtme sidumisel osutiga on kõrvalmõju, mida tasub mainida. Ühe poliitikavõtme omanik avab selle osuti kirjed selle võtmepõlvkonna all ja ühegi teise omad mitte. Teise hoidla, konfi või tiimi jaoks esitatud või teise versiooni all uuesti mängitud blob ei läbi terviklikkussilti.

## Mis muutub olemasolevate seadistuste jaoks

- **Poliitikakirjed on versioon 2.** Versiooni 1 kirje, mis oli pitseeritud hoidlavõtmega endaga, ei avane. See on tahtlik puhas katkestus.
- **Hostitud kirjutused alluvad samale poliitikale.** Hostitud täitja kaudu tehtud konfikirjutusi kontrollitakse enne salvestamist poliitika lae vastu.
- **Kohalikud agendid säilitavad sama lae.** `REDIACC_ALLOW_CONFIG_EDIT` lubab agendil endiselt nimetatud osutite konfi muuta, kuid ainult poliitika lubatud piirides.
- **Aegunud ja pööratud grandid ebaõnnestuvad selgelt.** `initialize` ja `tools/list` vastavad endiselt ning iga kutse tagastab `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` või `REDIACC_KEY_ROTATED` koos `reauthUrl`-iga.

Iga grant lubab 60 kutset minutis ja 5 korraga pooleli.

## Mida lekkinud URL annab

Lekkinud URL tegutseb selle kasutajana tema ühel konfil, kuni see aegub või tühistatakse. See ei ava ühtegi teist organisatsiooni konfi ega midagi väljaspool oma piirkonna hostitud täitjat. Tööriistade väljund jõuab siiski mudelipakkujani, kelle kasutaja ühendab. Rediacc seda pakkujat ei vali.

Seadistusjuhend on [MCP Server Setup](/et/docs/ai-agents-mcp) ja võtmete ülesehitus on [turvamudelis](/et/docs/security-model).
