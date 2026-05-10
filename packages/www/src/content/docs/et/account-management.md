---
title: Kontohaldus ülevaade
description: Organisatsioonid, meeskonnad, liikmed ja tellimused Rediaccis ühes kohas.
category: Guides
order: 12
language: et
---

### Organisatsioonid

Registreerimisel loob Rediacc teile automaatselt organisatsiooni. Teie org on kõigi ressursside peamine konteiner - masinate, repositooriumide, tellimuste ja meeskonnaliikmete jaoks.

![Registreerimisvoog](/img/account-registration-flow.svg)

Igal organisatsioonil on:
- Unikaalne nimi (vaikimisi teie e-posti aadress)
- Tellimisplaan (algab COMMUNITY-ga)
- Vaikemeeskond (kõik liikmed liituvad automaatselt)

### Liikmed ja rollid

Organisatsioonid toetavad kolme rolli:

![Rollide hierarhia](/img/account-role-hierarchy.svg)

| Roll | Võimalused |
|------|------------|
| **Omanik** | Täielik kontroll: arveldamine, omandiõiguse üleandmine, kõigi liikmete ja meeskondade haldamine |
| **Admin** | Liikmete kutsumine ja eemaldamine, meeskondade loomine ja haldamine, API-tokenite tühistamine |
| **Liige** | Organisatsiooni andmete vaatamine, API-tokenite loomine, määratud meeskondadele juurdepääs |

Liikmete kutsumine:
```bash
# Portaalis: Organization > Members > Invite
# Või API kaudu
```

Kui liige eemaldatakse, tühistatakse tema API-tokenid ja konfiguratsioonihoidla tokenid automaatselt.

### Meeskonnad

Meeskonnad võimaldavad ressursse organisatsioonis piirata. Iga org algab vaikemeeskonnaga.

![Meeskonna struktuur](/img/account-team-structure.svg)

Meeskonna rollid:
- **Meeskonna admin**: Saab meeskonnasiseselt liikmeid lisada ja eemaldada
- **Liige**: Saab ligi meeskonnale piiratud ressurssidele

Organisatsiooni omanikud ja adminid pääsevad automaatselt ligi kõigile meeskondadele ilma otsese liikmesuseta.

### Tellimused ja plaanid

Rediacc pakub nelja plaani:

| Plaan | Masinad | Repo-litsentsid/kuu | Delegeerimissert vaikimisi / max | Funktsioonid |
|-------|---------|---------------------|----------------------------------|--------------|
| COMMUNITY | 2 | 500 | 15p / 30p | Põhiline |
| PROFESSIONAL | 5 | 5 000 | 60p / 120p | Loagrupid, auditilogi, kohandatud bränding, prioriteettugi |
| BUSINESS | 20 | 20 000 | 90p / 180p | Ceph, täiustatud analüütika, järjekorra prioriteet, täiustatud järjekord |
| ENTERPRISE | 50 | 100 000 | 120p / 365p | Pühendatud kontohaldur |

![Tellimise voog](/img/account-subscription-flow.svg)

Kõik plaanid algavad 3-päevase puhverperioodiga. Masinakohti jälgitakse meeskonna kaupa ja need vabastatakse automaatselt pärast 1-tunnist tegevusetust. Vaadake üksikasju jaotisest [Tellimus ja litsentsid](/et/docs/subscription-licensing).

### Arveldamine

Ainult organisatsiooni **omanik** saab arveldamist hallata:
- Plaani uuendamiseks Stripe'i kassaseansi loomine
- Stripe'i arvelduportaalile juurdepääs makseviiside muutmiseks
- Iseteeninduse tagasimaksenõuded (14 päeva jooksul, 30-päevase jahtumisajaga)

### Andmeregioon

Teie konto on salvestatud andmeregiooni, mille valisite registreerimisel (EL, USA või Aasia-Vaikse ookeani piirkond). See valik on püsiv. Portaali regiooni märgis näitab, millises regioonis teie andmed asuvad. Vaadake üksikasju jaotisest [Andmeregioonid](/et/docs/data-regions).

### Edge-kanal

Kui teie konto on Edge-kanalil, näete portaali külgribal märgist "Edge". Edge-kontodel on 2-kordne Community piirang, kuid juurdepääs tasuliste plaanideni puudub. Vaadake Edge'i ja Stable'i erinevusi jaotisest [Väljalaskekanalid](/et/docs/release-channels).

### Delegeerimissertifikaadid

Kohapealsete ja õhulõhe juurutuste jaoks saate oma delegeerimissertifikaate hallata kliendiportaalis aadressil **/account/delegation-certs**. Leht on nähtav kõigile klientidele sõltumata plaani tasemest; ainult plaanispetsiifilised vaikimisi kehtivusajad erinevad.

#### Rollipiirangud

| Toiming | Org-omanik | Org-admin | Liige |
|---------|-----------|-----------|-------|
| Sertide loend / vaatamine / allalaadimine | ✓ | ✓ | ✓ |
| Uue serdi loomine | ✓ | ✓ | ✗ |
| Serdi tühistamine | ✓ | ✓ | ✗ |
| Automaatse uuendamise tokeni väljastamine | ✓ | ✓ | ✗ |
| Õhulõhe uuendamise päringu töötlemine | ✓ | ✓ | ✗ |

Liikmed näevad loendi ja saavad olemasolevaid serte alla laadida (kasulik masinate pargi vahel serdi levitamiseks), kuid ainult omanikud ja adminid saavad neid väljastada või tühistada.

#### Ühe aktiivse serdi nõue

Tellimusel võib korraga olla ainult **üks aktiivne delegeerimissert**. Iga kohapealne install rakendab kuu- ja masinakvoote oma lokaalse pearaamatu alusel; mitu aktiivset serti kordistaksid tegelikku kvooti ilma võimaluseta ühtlustada.

Kui proovite luua teist serti, kui üks on juba aktiivne, kuvab portaal dialoogi kahe valikuga:

- **Uuenda (soovitatav)** - pikendab olemasolevat ahelat. Kõik varem väljastatud repo-litsentsid jäävad uuendatud serdiga tööle. Kasutage seda, kui pöördete kehtivuse aeguva serdi sama kohapealse installi puhul.
- **Tühista ja loo uus** - hülgab olemasoleva ahela ja alustab nullist. Varem väljastatud repo-litsentsid muutuvad kontrollimiseks kõlbmatuks pärast VANA serdi validUntil möödumist. Kasutage ainult siis, kui olete migreerunud uuele kohapealsele installile erineva allkirjavõtmega, või taastumiseks ohustatud võtme puhul.

Kui vajate eraldi keskkondi (tootmine + lavastus + DR + mitme piirkonna), ostke üks tellimus installi kohta.

#### Automaatse uuendamise alglaadimine

Kohapealse automaatse uuendamise lubamiseks klõpsake delegeerimissertide lehel **Hangi automaatse uuendamise token**. See väljastab `delegation:renew`-ulatusega API-tokeni (igavene, aegumata) ja näitab väärtusi, mida tuleb kopeerida oma kohapealsesse `.env`-faili:

```
UPSTREAM_URL=https://www.rediacc.com
UPSTREAM_API_KEY=rdt_<token>
```

Token annab loa **ainult** delegeerimissertide uuendamiseks - muid ressursse ei saa lugeda ega muuta. See on ainus viis `delegation:renew`-tokeni väljastamiseks; tavaline `/portal/api-tokens` voog ei sisalda seda ulatust.

#### Õhulõhe uuendamine

Kui teie kohapealne install ei oma väljaminevat HTTPS-juurdepääsu, kasutage võrguühenduseta manifesti voogu:

1. Kohapealsel halduslehel klõpsake **Laadi alla uuenduspäring**. Kohapealne genereerib allkirjastatud manifesti, mis sisaldab teie lokaalse ahela pead.
2. Kandke manifest ülesvoolu (USB, krüpteeritud e-post, suvaline kanal).
3. Ülesvoolu portaalis klõpsake **Laadi üles uuenduspäring** ja valige manifest. Ülesvool kontrollib manifesti allkirja, väljastab uue serdi ja tagastab selle allalaaditava `.json`-ina.
4. Kandke uus sert tagasi kohapealsele installile ja laadige see üles kohapealse halduslehe kaudu.

Ülesvool lükkab tagasi üle 7 päeva vanused manifestid. Vaadake täielikku samm-sammult seadistust jaotisest [Kohapealne install](/et/docs/on-premise) ja krüptograafilist disaini jaotisest [Litsentsiahel ja delegeerimine](/et/docs/license-chain).

#### Kiiruspiirang

Serdi loomine on piiratud **10 katsega per libisev 24h** tellimuse kohta, kaasa arvatud ebaõnnestunud katsed (kollisiooni späm, vale sisend). Piiri ületamisel kuvab portaal väärtuse `Retry-After`, mis näitab, millal saate uuesti proovida.
