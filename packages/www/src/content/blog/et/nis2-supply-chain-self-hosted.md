---
title: "Article 21(2)(d) on hankija küsimus. Ise majutamine on vastus, mida te enam võlgu ei ole."
description: "Miks ICT kolmanda osapoole register kahaneb, kui andmeplaan ei lahku kunagi teie haldusest. Article 21(2)(d) praktiline lugemine CISO-dele ja hankeekspertidele, kes renegotsieerivad DPA-sid 2026. aastal."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - tarneahel
  - ise-majutamine
  - andmesuveräänsus
  - vastavus
featured: false
language: et
sourceHash: "98f0b752bc5dbd4d"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
translatedFrom: en
---

> **TL;DR.** NIS2 Article 21(2)(d) tõstab tarneahela riski juhatuse tasandi küsimuseks, mitte hankenüanssiks. Direktiiv ei nõua tegelikult ise majutamist. Küll aga küsib see, mis asub teie andmetees ja mis juhtub teiega, kui mõni hankijatest kogeb halba teisipäeva. Ise majutatud taristu kaotab enamiku SaaS-i andmeteede neljast kihist kolm. Kõiki nelja see ei kaota ja selle väitmine on see turundustrikk, mis viib CISO auditori ees ebameeldivasse olukorda.
>
> - Direktiivi tekst ja ENISA juhis, selges eesti keeles.
> - Nelja kihiga SaaS-i andmetee, mida enamik tiime unustab joonistada.
> - Mida Rediacc kahe tööriistaga mudel teie hankijaregistrist eemaldab ja mida sellesse jätab.
> - Kuus küsimust hanke kontroll-loend igale hankijale, kes väidab end olevat "NIS2-valmis".

2020. aasta juulis maksis Blackbaud lunaraha ja teavitas maailma sellest hiljem. Nad teatisid enam kui 13 000 kliendiorganisatsioonile tagantjärele, seisid silmitsi kollektiivhagidega seitsmest jurisdiktsioonist ning maksid lõpuks 49,5 miljonit dollarit osariikide peaprokurörde kokkulepete ja 3 miljonit dollarit SEC-i trahvi eksitavate avalikustamiste eest. Igal ühel neist 13 000 organisatsioonist oli Blackbaud'iga andmetöötluslepingu (DPA). Enamik neist oli üle vaadanud Blackbaud SOC 2 aruande. Paljudel oli Blackbaud hankijate riskiregistris koos taseme hinnanguga, uuendamise kuupäeva ja vastutava isikuga.

Miski ei suutnud kaskaadi peatada. Andmed asusid Blackbaud'i piiripoolel. Kui nende varukoopiate keskkond murditi sisse, sattus iga kliendiorganisatsioon üheaegselt rikkumise ohvriks.

NIS2 Article 21(2)(d) esitab raskema küsimuse kui "kas te auditeerisite oma hankijat?". See küsib, mis asub andmetees ja mis juhtub teiega, kui see hankija kogeb halba teisipäeva. Vastus on enamiku tiimide jaoks: "oleme nendega samas paadis ja ei mõistagi seda."

See postitus on mõeldud CISO-dele ja hankeekspertidele, kes renegotsieerivad DPA-sid 2026. aastal. See on Article 21(2)(d) andmetee lugemine, mitte sertifikaatide lugemine. Samuti on see aus selles osas, mida ise majutatud taristu ei lahenda, sest lünkade jaotis on see, mida auditor küsib ja turundusbrošüür vahele jätab.

## Mida 21(2)(d) tegelikult kohustab

Direktiivi tekst kõlab, veidi selguse nimel lühendatuna:

> "Lõikes 1 osutatud meetmed põhinevad kõiki ohte hõlmaval lähenemisviisil, mille eesmärk on kaitsta võrgu- ja infosüsteeme ning nende süsteemide füüsilist keskkonda intsidentide eest, ning hõlmavad vähemalt järgmist: [...] d) tarneahela turvalisust, sealhulgas sellised turvalisusesse puutuvad aspektid, mis on seotud iga üksuse ja tema otseste tarnijate või teenuseosutajate vaheliste suhetega"

Sellest tekstist on ostjale oluline kaks asja.

Esiteks lasub kohustus teil, mitte hankijal. Hankija sertifikaadid, hankija SOC 2, hankija ISO 27001 on sisendid teie riskihindamisse. Need ei asenda seda. Kui teie hankijal on täiuslik vastavusseisund, kuid ta saab rikkumise ohvriks ikkagi, küsib regulaator teie tarnijate riskijuhtimise kohta, mitte nende oma.

Teiseks on kohustus laiem kui leping. ENISA 2024. aasta rakendamisjuhis, komisjoni rakendusmääruse (EL) 2024/2690 IV lisa, sätestab oodatava tava: pidada ICT-tarnijate registrit, liigitada need kriitilisuse järgi, hinnata igaüht teie tegevusele ja nende poolt töödeldavatele andmetele ohuks oleva riski osas ning uuendada hinnangut määratletud sagedusega. IV lisa nimetab otsesõnu "tarnijate tarnijaid" reguleerimisalasse kuuluvatena, millest enamik tiime avastab, et nende hankijaregister ei ole tegelikult register, vaid lepingute loend kleebisega.

Kui vaatate seda hanke poolelt, on praktiline tõlgendus järgmine: iga hankija, kellel on loogiline juurdepääs teie tootmisandmetele, tuleb loetleda, hinnata, jälgida ja asendatavana pidada. "Asendatav" on see osa, mis lõhub enamiku olemasolevaid kokkuleppeid.

## Nelja kihiga SaaS-i andmetee, mida enamik tiime unustab joonistada

Istuge koos hankeekspertiga ja vaadake läbi, mis juhtub, kui varukoopiate hankija toode kirjutab ühe kirje. Aus andmetee näeb välja selline, ülevalt alla:

1. **Hankija rakendus.** Kood, mis võtab andmeid vastu, teeb marsruutimisotsuseid ja rakendab äriloogikat. Töötab hankija taristul. Seda hooldab, paigab ja jälgib hankija.
2. **Hankija pilv.** Hüpermastaabi piirkond või hankija oma andmekeskus, kus rakendus töötab. Mälumahud, võrk, IAM. Sageli hüpermastaap, kellega hankijal on alluttöötleja leping.
3. **Hankija võtmehaldus.** Krüptovõtmed, mis kaitsevad andmeid hankija pilves puhkeolekus. Enamikus SaaS-i kokkulepetes hoiab neid hankija. "Kliendi hallatavad võtmed" on mõnikord kõrgema taseme valik; nendes kokkulepetes asuvad võtmed ikkagi hüpermastaabi KMS-is, mida hankija IAM saab kutsuda.
4. **Hankija alluttöötlejad.** Kolmanda osapoole teenused, mida hankija kasutab (CDN, jälgitavus, arveldustarkvarad, klienditugi), mis võivad edastada või salvestada teie andmeid või nendest tuletatud metaandmeid.

Igaüks neist neljast kihist on kanne teie Article 21(2)(d) tarnijate registris. Igaühel on oma intsidentide ajalugu, oma rikkumise levimisulatus, oma lepinguläbirääkimiste pind. Kui uuendate lepingut SaaS-i hankijaga, uuendate kõiki nelja kaudselt, sest SaaS-i hankija leping on ainus, mida saate läbi rääkida.

Blackbaud'i intsident oli kihi 2 rikkumine (hankija pilv), mis levis läbi kihi 1 (hankija rakendus) ja oli nähtav igale kliendile kihi 3 tõttu (hankija võtmehaldus, antud juhul serveri poolsed võtmed ilma rentniku eristamiseta mõjutatud andmebaasis). Blackbaud'i alluttöötlejad ei olnud rikkumise vektor, kuid kliendid avastasid kolm neist, mida polnud loetletud.

## Blackbaud, Druva-stiilis võtmehaldus ja kaskaadi muster

Kolm üksikasja Blackbaud'i SEC-i esitistest on need, mis NIS2 lugemise jaoks olulised on.

Esiteks hoidis Blackbaud klientide andmete krüptovõtmeid, sealhulgas varukoopiate keskkonna omi, mis oli rikkumise sihtmärk. Kliendi hallatavaid võtmeid ei pakutud. Pärast intsidenti toimunud SEC-i kohtuprotsessil iseloomustati seda kontrollipuudusena, mitte rikkumisena, sest Blackbaud'i lepingud lubasid seda. NIS2 vaatenurk samale kokkuleppele Article 21(2)(d) alusel on karmim, sest klient ei suuda tähenduslikult hinnata kontrolli riski, millesse tal puudub nähtavus.

Teiseks mõjutas rikkumine varukoopiate andmeid, mis olid vanemad kui otsebaas. Kliendiorganisatsioonid, kelle otseandmed olid Blackbaud'i põhisüsteemidest kustutatud, omasid ikkagi andmeid, mis olid varukoopiate keskkonna kaudu avalikustatud. See on kaskaadi muster: hankija kompromiss ulatub ajaloolistesse andmetesse, mille klient arvas juba olevat reguleerimisalast väljas.

Kolmandaks said rikkumisteatise enam kui 13 000 kliendiorganisatsiooni. Paljud neist olid väikesed mittetulundusühingud ja koolid, millel polnud toimingute suutlikkust reageerida, ei DR-käsiraamatut ega teist varukoopiate hankijat, kellele üle lülituda. Hankija intsident sai sel moel nende intsidendiks.

Druva-stiilis kaasaegse SaaS-i varukoopia puhul on arhitektuur mõnes kohas parem (rentniku kohane võtmete eraldamine on tavalisem, BYOK on kõrgematel tasemetel saadaval), kuid nelja kihiga andmetee on sama. Hankija rakendus, hankija pilv (tavaliselt AWS), võtmehaldus (mõnikord hankija, mõnikord BYOK kliendi KMS-is, mõnikord hübriid), alluttöötlejad. Rikkumine mis tahes kihis jõuab kõigi klientideni üheaegselt, sest kõigi klientide andmed asuvad piiri samal poolel.

See on struktuurne argument. See ei ole Druva ründamine. Druva töötab korrektsemalt kui Blackbaud tegi. Argument seisneb selles, et mis tahes SaaS-i kujundusega varukoopiate toote struktuur muudab kihi 2 ja kihi 3 rikkumised 21(2)(d) alusel kohustuseks, mida klient ei suuda tähenduslikult täita.

## Ise majutamine kaotab kolm neljast kihist

Rediacc on üles ehitatud teisiti. Täielik arhitektuur on dokumenteeritud [arhitektuuri lehel](/et/docs/architecture), kuid tarneahelaga seotud kuju on kaks binaari, mis suhtlevad üle SSH:

- `rdc` töötab operaatori tööjaamal. See loeb lamedat JSON-konfiguratsioonifaili (kaustas `~/.config/rediacc/`), ühendub operaatori enda masinatega üle SSH ja saadab käske.
- `renet` töötab operaatori enda serveris root-õigustega ja haldab LUKS2-krüptitud kettakujutisi, isoleeritud Dockeri daemoneid ja pöördpuhverserverit.

Operaator ei logi kunagi Rediacc OÜ taristusse varukoopia, taastamise või hargnemise käivitamiseks. Andmetees ei ole Rediacc OÜ pilve. Hoidla LUKS2 mandaat säilitatakse operaatori kohalikus konfiguratsioonifailis (moodus `0600`), mitte kunagi serveris, mitte kunagi saadetuna Rediaccile. Andmetee näeb välja selline:

1. **Operaatori tööjaam.** Käivitab `rdc`. Hoiab LUKS2 mandaati.
2. **Operaatori enda server.** Käivitab `renet`. Hoiab LUKS2-krüptitud hoidlaid.
3. **Operaatori enda varukoopiasisend.** Mis tahes rclone-ühilduv salvestusruum (S3, B2, OneDrive, kohapealne MinIO). Saab krüptitud mahte.

Kihti 4 pole. Rediacc OÜ ei ole alluttöötleja ühelegi operaatorile, kes pole katsetuslikku [Pilveadapterisse](/et/docs/architecture) registreerunud. Ise majutavate operaatorite jaoks on suhe Rediacc OÜ-ga tarkvaralitsents, mitte andmetöötlusleping.

See on andmetee argument ja see on õige argument, millega tarnijate registri vestluses alustada. SaaS-i konkurent saab pakkuda kliendi hallatavaid võtmeid (ja enamik kaasaegseid pakubki). SaaS-i konkurent ei saa pakkuda "me ei ole alluttöötleja."

Teine löök, pärast seda kui andmetee argument on kohale jõudnud, on võtmehaldus. Rediacciga on LUKS2 mandaat operaatori konfiguratsioonifailis, punkt. Võtmejärelvalvet pole, taasteteenus puudub, mida Rediacc OÜ saaks käivitada, kui operaator mandaadi kaotab. See on ka soovituslik arhitektuur [nullteadmiste konfiguratsioonihoidlale](/et/docs/config-storage), kus krüptovõti tuletatakse kliendi poolel passivõtme PRF-laiendist ning server säilitab läbipaistmatuid plokke. Server ei saa lugeda SSH-võtmeid, LUKS2 mandaate, IP-aadresse ega ühtegi selget konfiguratsiooniteksti. Juurdepääsu loa rotatsioon ei anna serverile tagasiulatuvat lugemisõigust.

Article 21(2)(h) (krüpteerimine) seisukohast on see oluline. Article 21(2)(d) (tarneahel) seisukohast on see olulisem, sest see eemaldab viimase loogilise juurdepääsutee Rediacc OÜ-lt operaatori andmetele.

## Mida ise majutamine ei kaota

Ise majutamine nihutab tarnijate nimekirja, ei kustuta seda. Kolm asja, mida auditor ikka küsib:

**1. Teil on ikkagi hankijad, lihtsalt erinevad.** Riistvara hankija (Hetzner, Hostinger, OVH, teie kolokatsiooniruumid, teie enda bare metal). Hypervisor (KVM, VMware). Operatsioonisüsteem (Debian, Ubuntu, RHEL). Konteinerite register (Docker Hub, GHCR, teie privaatne register). Aluspildid, mida teie teenused tõmbavad. Igaüks neist on Article 21(2)(d) kanne. Ise majutamine nihutab hankijate nimekirja, ei kustuta seda.

**2. Rediaccil ei ole veel ISO 27001, SOC 2 ega BSI C5.** Need on teekaardil, mitte käes. Hanketiimi jaoks, mis kasutab sertifikaate väravamehhanismina, on see reaalne hõõrdekoht. Kaitsetav vastuargument on see, mida see postitus on esitanud: andmetee argument tähendab, et enamik sellest, mida need sertifikaadid tõendavad (hankija pilve turvakontrollid, hankija töötajate juurdepääsu haldamine, hankija alluttöötlejate haldamine), ei ole reguleerimisalas, sest Rediacc OÜ ei ole andmetees. Seda argumenti tuleb esitada hoolikalt ja kaitstavalt, mitte sertifikaatide asendajana siis, kui ostja vajab just sertifikaate.

**3. GRC kiht on ikkagi teie oma.** Rediacc annab operaatorile üle 70-sündmuselise räsiketiga auditilogi (`rdc audit verify` valideerib ahela algusest lõpuni). See ei anna teile tarnijate registrit, kontrollraamistikku ega tõendite kogumise töövoogu. Need tulevad ikka Drata, Vanta, OneTrust või mõne Euroopa tulijate käest. Kaasleva [tegeliku arve postituse](/et/blog/nis2-the-real-bill) kaudu saate täpsemat teavet selle täiendavuse kulustruktuuri kohta.

## DPA, mida te enam läbi rääkima ei pea

Konkreetsemaks muutmiseks on siin "enne vs pärast" registririda tegelikust hankevestlusest, anonümiseerituna. Ostja on 280 töötajaga Saksa tootmisettevõte, mis on liigitatud II lisas "oluliseks üksuseks". Nende algne hankijaregistri kanne varukoopiate jaoks nägi välja selline:

| Väli | Enne |
|---|---|
| Hankija | Acme Backup SaaS |
| Tase | Kriitiline |
| Töödeldud andmed | Tootmisandmebaas, klientide isikuandmed, finantskirjed |
| Alluttöötlejad | AWS (eu-central-1), Datadog, Stripe, Zendesk |
| Lepingu staatus | DPA allkirjastatud 2023, SCC-d lisatud, meetmete ajakava viimati üle vaadatud jaan 2025 |
| Võtmehaldus | Hankija hallatav (BYOK valik pole praegusel tasemel) |
| Väljumisplaan | "Hankija nõustub andmete eksportimisega CSV-formaadis 30 päeva jooksul pärast lepingu lõpetamist" |
| Viimane hindamine | 2025-Q1, võtmehalduse lünk märgitud, edasi lükatud uuendamiseni |

Pärast Rediaccile üleminekut Hetzneris:

| Väli | Pärast |
|---|---|
| Hankijad | (1) Rediacc OÜ, tarkvaralitsents; (2) Hetzner, IaaS |
| Tase | (1) Mittekriitiline (andmetasandit pole); (2) Kriitiline (andmetasand, kuid kliendi hallatav) |
| Töödeldud andmed | (1) Puuduvad; (2) Krüptitud mahud, klient hoiab võtmeid |
| Alluttöötlejad | (1) Ise majutavatele puuduvad; (2) Ainult Hetzner-sisesed, loetletud nende DPA-s |
| Lepingu staatus | (1) Tarkvaralitsents, DPA pole vajalik; (2) Hetzner DPA + SCC-d juba paigas |
| Võtmehaldus | Klient (LUKS2 mandaat operaatori konfiguratsioonis, mitte serveris) |
| Väljumisplaan | "rdc repo backup pull mis tahes rclone-ühilduvast sihtmärgist. Mahud on LUKS2-krüptitud; operaator hoiab mandaati." |
| Viimane hindamine | (2) kaetud olemasoleva IaaS-i ülevaatusega |

Kaks registrikirjet ühe asemel. Kriitilise taseme kanne on IaaS-i pakkuja jaoks, kellel oli ostjal juba DPA paigas ja testitud väljumisplaan, sest IaaS on suhe, mida enamik tiime oskab hallata. Rediacc'i kanne on mittekriitiline, sest see on tarkvaralitsents, mitte andmetöötleja.

See on struktuurne põhjus, miks CISO soovib andmetasandil vähem SaaS-i sõltuvusi, isegi kui hankekulu näeb tabelis sarnane välja. Registrikanne ei ole sama kujuga.

## Hanke kontroll-loend

Igale hankijale, kes väidab end olevat "NIS2-valmis" 2026. aasta müügitsüklis, kuus küsimust:

**1. Kus asub meie puhkeolekus andmete krüptovõti?** Kui vastus on "meie HSM-is" või "meie kliendi KMS-is, mida saame IAM-i kaudu kutsuda," on hankija teie võtmehalduse ahelas. Kui see on "teie kohalikus konfiguratsioonifailis, mitte kunagi meie taristus," ei ole ta.

**2. Kes teie ettevõttes saab meie andmeid tehniliselt lugeda, õigusnorme ignoreerides?** Mitte "kellel on luba," vaid "kes saaks, kui ta tahaks ja auditilogi oleks välja lülitatud." Kui vastus ei ole null, on see teie siseringi riskihindamise populatsioon.

**3. Kas taastamine on testitud tegeliku tootmiskloonil või sünteetiliste testandmetega?** Article 21(2)(c) ja (e) koos loetuna nõuavad, et varukoopia tegelikult taastub. Hankija, kes valideerib ainult sünteetiliste andmete suhtes, ei valideeri taastamist, vaid varukoopiate failide terviklust. (Lisateabe saamiseks vt kaaslev postitus [pideva tõhususe hindamise kohta](/et/blog/nis2-effectiveness-without-theatre).)

**4. Kas teie auditijälg registreerib toimija liigi, inimene või agent, iga toimingu taga?** AI agentide tegevus on auditilogide kõige kiiremini kasvav kategooria. 2026. aasta auditilogi, mis ei erista inimest agendist, näeb 2027. aastaks lüngana välja.

**5. Loetlege iga alluttöötleja, kellel on loogiline juurdepääs meie andmetele, sealhulgas metaandmed.** "Loogiline juurdepääs" on õige fraas. "Loogiline juurdepääs sealhulgas metaandmed" on parem, sest ainult metaandmetele juurdepääs on see, mis arveldusel, jälgitavusel ja klienditeeninduse alluttöötlejatel tavaliselt on, ning see piisab tundliku struktuuri lekkimiseks isegi siis, kui kasulik koormus on krüptitud.

**6. Mis on teie väljumisplaan, kui teid omandab mitte-EL ostja 2027. aastal?** GDPR-i piisavuse raamistik, Cloud Act ja FISA 702 on kõik liikuvad sihtmärgid. Hankija andmete asukohakohustus täna ei ole garantii kolme aasta pärast. Ostja küsimus on see, mis juhtub andmeteega, kui hankija omandisuhe muutub.

Hankija, kes vastab kuuele küsimusele kuuest selgelt, on haruldane. Hankija, kes vastab neljale kuuest ja tunnistab kaht teist avalikult, on usaldusväärsem kui see, kes vastab kõigile kuuele enesekindlalt. Usaldusväärsuse signaal on valmisolek nimetada, mis pole lahendatud.

## Mida see tähendab järgmiseks uuendamise tsükliks

Kui teil on järgmise kaheteistkümne kuu jooksul ees varukoopiate või DR uuendamine ja Article 21(2)(d) on hanke tulemiskaardil, kolm konkreetset sammu:

1. Joonistage tahvlile oma praeguse hankija nelja kihiga andmetee. Kui te ei suuda nimetada kolmandat alluttöötlejat, on teil registri täielikkuse probleem, mis eelneb NIS2-le, ja uuendamine on õige hetk see parandada.
2. Käivitage ülaltoodud kuue küsimuse kontroll-loend oma praeguse hankija suhtes. Saatke vastused oma DPO-le ja auditorile ning küsige, kas lüngad on aktsepteeritud. Kui lüngad hõlmavad kihti 3 (võtmehaldus) või kihti 4 (alluttöötlejad, keda te ei loetlenud), on see kang.
3. Vaadake, milline näeks välja alternatiivne hankijate register ise majutatud juhtimistasandiga. Võrrelge registrikirjeid, mitte litsentsikulusid. Litsentsikulud on kahe kordse teguri piires sarnased; registrikirjed on erineva kujuga. (Kaaslev postitus [NIS2 paketi struktuurkulude kohta](/et/blog/nis2-the-real-bill) käib läbi selle, mis kaob ja mis jääb.)

Kui oleme teie lühinimistu alternatiiv, on pakkumine konkreetne. Saatke meile oma hankijaküsimustik. Me täidame selle juurutatud instantsi suhtes, meie tegelike vastustega teie küsimustele, sealhulgas lünkadega. Kui soovite arhitektuuri läbi vaadata enne paberimajanduse saatmist, broneerime 30-minutilise arhitektuuriülevaatuse asutajaga. Kaitsetava registrikirjeni viiv tee ei ole läikiv brošüür. See on vastused, sealhulgas ebamugavad.

Soovid artiklipõhist Rediacc kaarti? Vaata [NIS2 ja DORA](/et/docs/legal-nis2-dora). Vajad laiemat raamistikku? Loe [Vastavuse ülevaade](/et/docs/legal-overview). Andmete asukoha kohta vaata [Andmesuveräänsus](/et/docs/legal-data-sovereignty). Miks ise majutamine on oluline, vaata [Kohapealne](/et/docs/on-premise).
