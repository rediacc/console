---
title: Mida ostjad meile esimese NIS2 audititsükli jooksul rääkisid
description: >-
  Viie tööriista vastavuspakett, mille keskturu olulised üksused 2026. aastal
  vaikselt kokku panevad; mida ise majutatud juhtimistasand koondab; ja
  kuluridad, mis jäävad igal juhul teie kanda.
author: Rediacc
publishedDate: 2026-05-09T00:00:00.000Z
category: guide
tags:
  - nis2
  - ostjajuhend
  - vastavus
  - kulu
  - keskturg
featured: false
language: et
sourceHash: 29fbcbffd8a304bc
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
translatedFrom: en
---

**TL;DR.** Esimese tsükli NIS2 auditid on Saksamaa laine jaoks nüüd seljataga. Kõik ostjad, kellega oleme detsembrist saati rääkinud, kirjeldavad sama paketi varianti: viis tööriista, kolm lepingut, kaks kattuvat auditilogi ja üks lünk, mida ei suudeta sulgeda. See postitus on nende vestluste struktuurne versioon. Mida ise majutatud juhtimistasand koondab, mis jääb igal juhul teie eelarvesse ja miks 2026. aasta uuendusetsükli õige lähteküsimus ei ole "odavam kui Veeam", vaid "vähem registrikirjeid, vähem kattuvusi ja samad lüngad ausalt nimetatud."

- Frontier Economics hindas EL-i üleseks NIS2 vastavuse kuluks 31,2 miljardit eurot aastas. Keskturu tegelikkus on: "meil oli juba turvapakett; NIS2 tõi välja, mida puudu oli."
- Viie tööriista pakett: backup, DR, andmete maskeerimine ehk testandmed, penetratsioonitesti leping ja GRC. Igaüks katab osa tööst. Ükski ei kata tervikut.
- Rediacc koondab backup'i, DR-i, fork-as-test-data ja kiirtaaste ühte juhtimistasandisse ühe auditilogi alla. See ei koonda GRC-d, sertifitseerimisi, koolitusi, laiemat MFA-d, penetratsioonitestimist ega SIEM-i ja SOC-i.
- Aus tabel "jääb teie kanda" on selle postutuse struktuurne tulemus. Ostja, kes loeb seda ja järeldab, et Rediacc asendab Drata, valmistab oma audiitorile pettumuse.

2025. aasta detsembris saatis BSI Saksamaal 47 ametlikku teadet üksustele, keda peeti NIS2 reguleerimisalasse kuuluvaks, kuid kes ei olnud registreeritud. ANSSI Prantsusmaal alustas paralleelset harjutust. ACN Itaalias hakkas taga ajama ligikaudu 2000 üksust, keda peeti registreerimata. Keskturu oluliste ja tähtsate üksuste esimene laine läks oma esimesse NIS2 audititsüklisse.

Oleme sellest ajast saati olnud kõnelustel umbes kolmekümnest neist. Erinevad sektorid, erinevad suurused, enamasti Saksamaa ja Itaalia, mõni üksus Hollandist ja Eestist. Vestlused kordavad üksteist. Igal meeskonnal on backup-tarnija, DR-plaan, mida võib-olla on testitud, võib-olla mitte, lugu staging-keskkonnast, mis on pooleldi tõsi, ja hankeeelarvega, mis kinnitati enne, kui NIS2 oli kellegi slaidipakis.

See postitus on nende vestluste struktuurne versioon. Mida CFO-lt või ostjalt tegelikult 2026. aastal allkirja küsitakse, mida ise majutatud juhtimistasand arvega muudab ja milline näeb aus jääkkulu välja. See ei ole tahtlikult TCO kalkulaator. Ostjad, kellega me räägime, ei vaja veel üht arvutustabelit; nad vajavad struktuurikaarti, kuhu raha läheb ja millised kuluridad kattuvad.

Kui soovite tarneahela riskiargumenti "ise majutamine on oluline" väite taga, vaadake [kaaslaspostitust artikli 21(2)(d) kohta](/et/blog/nis2-supply-chain-self-hosted). Kui soovite SRE-tasandi argumenti, miks aastased penetratsioonitestid enam ei piisa, vaadake [kaaslaspostitust pideva tõhususe kohta](/et/blog/nis2-effectiveness-without-theatre). See postitus asub nende vahel, eelarvevestluse tasandil.

## Makronumber ja mida see tähendab ja ei tähenda

Frontier Economicsi 2024. aasta uuring Euroopa Komisjonile hindas NIS2 vastavuse otseseks aastakuluks kogu EL-is 31,2 miljardit eurot. Arvu tsiteeritakse laialdaselt; seda loetakse ka laialdaselt valesti.

31,2 miljardit eurot jaguneb ligikaudu 160 000 olulise ja tähtsa üksuse vahel. Ühe organisatsiooni kohta jääb keskmine 150 000 kuni 250 000 euro vahemikku, kusjuures enamiku hajuvuse määravad sektor ja suurus. 250 töötajaga keskturu oluline üksus tootmises või tervishoius on selle vahemiku ülemises otsas. 60 töötajaga tähtis üksus vähem andmemahukast sektoris on alumises otsas.

ENISA enda rakendusmaksumuse juhend (rakendusmääruse (EL) 2024/2690 IV lisa) on Frontieri arvuga kooskõlas, kuid jaotab selle teisiti: ligikaudu 35-45 protsenti tööriistadele, 30-40 protsenti personalile ja koolitusele, 15-20 protsenti sertifitseerimisele ja auditile, 5-10 protsenti intsidentide lahendamise retaineritele ja hallatatavatele teenustele.

Mida see tähendab 2026. aasta eelarvet allkirjastavale CFO-le: tööriistade kiht on keskturu jaoks ligikaudu 50 000 kuni 120 000 eurot aastas, sõltuvalt sellest, mis on juba olemas. Seda tööriistade kihti me nüüd läbi vaatamegi.

Mida see ei tähenda: et NIS2-valmis paketi ostmine lahendab probleemi. Personali koolituse ja sertifitseerimise eelarved on enamiku meeskondade jaoks suuremad kui tööriistade eelarve ja ükski tööriistatarnija neid ei vähenda. Tarnija esitlus, mis väidab 50-protsendilist NIS2 kulude vähenemist, teeb peaaegu alati aritmeetikat ainult tööriistade kulurea vastu, mitte kogu programmi kulu vastu.

## Viie tööriistaga pakett, mida keskturu meeskonnad vaikselt kokku panid

Kolmekümne ostjavestluse põhjal näeb pakett 90 protsendil juhtudest ühesugune välja. Viis kategooriat, üks kuni kaks nimetatud tarnijat kategooria kohta. Kategooriate sildid on stabiilsed; tarnijate valik varieerub.

**1. Backup-tarnija.** Modaalne vastus on Veeam Data Platform Foundation või Premium. Väiksemate seas Cohesity DataProtect, Rubrik Security Cloud, Commvault, Acronis Cyber Protect. Aastane kulu keskturu jaoks 15 000 kuni 60 000 euro vahemikus. Tavaliselt kõige vanem kulurea kirje; on NIS2-st aastaid vanem.

**2. DR-sait või DR-as-a-service.** Kas teisene pilvepiirkond koos käivitamisjuhendiga, Veeam Cloud Connect'i või Rubrik Cloud Vault'i rent, või leping hallatava DR-tarnijaga. Aastane kulu 8000 kuni 35 000 eurot. Praktikas harva testitud; käivitamisjuhend on tavaliselt rohkem aspiratiivne kui toimiv.

**3. Testandmete tööriist või andmete maskeerimise tööriist.** Ettevõtteklass on Delphix (nüüd Perforce DevOps Data). Tonic.ai, Redgate Test Data Manager, aeg-ajalt kohandatud rsync-ja-mask skript. Aastane kulu litsentsitud valikute puhul 25 000 kuni 90 000 eurot. Enamikul meeskondadest meie kõnelustel seda kulurea kirjet ei ole; neil on midagi, mida nad loodavad, et on piisavalt hea staging-keskkond. Artikli 21(2)(e) auditvestlus on see, mis selle eelarvesse toob.

**4. Penetratsioonitesti leping.** Retainer turvatestimise ettevõttega või autonoomne platvorm nagu Pentera või Horizon3.ai. Aastane kulu 15 000 kuni 50 000 eurot autonoomsete tööriistade puhul, 20 000 kuni 80 000 eurot inimjuhitud tegevuste puhul. Enamikul meeskondadest on see olemas. Enamik meeskondi teeb seda kord või kaks aastas.

**5. GRC-platvorm.** Drata, Vanta, OneTrust, AuditBoard, Hyperproof, DataGuard, Kertos. Väikseimate meeskondade puhul mõnikord omatehtud arvutustabel. Aastane kulu 12 000 kuni 60 000 eurot. Kasutatakse tarnijate registri, kontrollraamistiku atesteerimise, tõendite kogumise ja (üha enam) SOC 2 või ISO 27001 auditi toetuse jaoks.

Viis kulurea kirjet, kolm kuni viis nimetatud tarnijat, tavaliselt 75 000 kuni 295 000 eurot aastas enne personali ja koolitust. Hajuvus on suur, kuid struktuur on järjepidev.

Viis lepingut ei räägi sageli üksteisega. Auditilogid ei ole ühendatud. Väljumisplaanid kirjutatakse eraldi. Tarnijate ülevaatusi tehakse eraldi, mõnikord erinevate hankejuhtide poolt. See on struktuurne kuju, mille NIS2 ebamugavaks muudab.

## Kus kattuvused on

Iga paketi kategooria kattub vähemalt ühe teisega.

**Backup kattub DR-iga.** Kõik kaasaegsed backup-tarnijad väidavad end olevat DR-võimelised. Veeam Data Platform koos Cloud Connect'iga on DR-toode. Rubrik koos Cloud Vault'iga on DR-toode. Kaks kulurea kirjet maksavad sageli sama tarnija külgnevate võimaluste eest. Ostjatel, kes ei ole ajalooliselt kulurea kirjeid koondanud, olid selleks tegevuslikud põhjused (eraldi meeskonnad, eraldi SLA-d); NIS2 "taastamise ainsa tõeallika" ootuse all nõrgeneb see põhjendus.

**Backup kattub testandmetega.** Veeam Instant Recovery, Rubrik Live Mount, Cohesity SmartFiles pakuvad kõik testide jaoks mingi ühendatava backup'i vormi. Need ei asenda täielikult Delphix'i (maskeerimiskiht on eraldi, andmebaasiintegratsioon on pealiskaudsem), kuid paljude testandmete kasutusjuhtude puhul on backup-tööriist pool vastusest. Enamik meeskondi ei mõista seda.

**Penetratsioonitestid kattuvad autonoomse testimisega.** Retaineripõhist inimjuhitud penetratsioonitesti ja Pentera-stiilis pidevat testimist pakutakse mõnikord alternatiividena, mõnikord täiendite pairina. Praktikas maksab ostja, kellel on mõlemad, kaks korda külgnevate võimaluste eest. Ostjal, kellel ei ole kumbagi, on artikli 21(2)(f) lünk.

**GRC kattub kõigega.** Drata väidab integreerimist backup'i, DR-i, identiteedi, haavatavuse halduse, koolituse ja intsidentidele reageerimisega. Integratsioonid varieeruvad sügavuse poolest. GRC-platvorm, millel on pealiskaudne integratsioon backup-tööriistaga, toodab vastavustõendeid, mis ei ole samad mis backup-tööriista enda tõendid; audiitorid hakkavad küsima, kumb on kanooniline.

Kattuvused ei ole raiskamine. Need on järeldus paketist, mis pandi kokku kümne aasta jooksul, enne kui NIS2 tegi koondamisküsimuse struktuuriliseks.

## Kus lüngad on

Lüngad on kattuvustest huvitavamad, sest lüngad on see, mida NIS2 pinnale toob.

**Paikade valideerimine reaalsete tootmisandmete vastu.** Ükski viiest kategooriast ei tee seda hästi. Backup-tööriistad ühendavad backup'i; ühendatud keskkond on taastatud backup, mitte praegune tootmine. Testandmete tööriistad maskeerivad tootmisandmeid; maskeeritud keskkond on kujult realistlik, kuid kaotab konfiguratsioonideltad. Penetratsioonitesti lepingud testivad seda, millele neid suunatakse, mis on 90 protsendil juhtudest staging-keskkond. Lünk "meil on tööriistad" ja "suudame testida CVE paikamist praeguse tootmisega samaväärses keskkonnas alla tunni ajaga" vahel on reaalne ja struktuurne.

**Pideva tõhususe hindamine.** Aastane tsüklilisus on see, mida enamik meeskondi teeb. Artikkel 21(2)(f) nõuab midagi sagedasemat. Ükski viiest kategooriast ei tooda vaikimisi iganädalaseid või kahenädalaseid tõendeid. Ostja kas korraldab kohandatud harjutusi (harva, kulukas) või aktsepteerib aastakadensi ja loodab, et audiitor aktsepteerib seda (üha enam ei aktsepteeri).

**Tarneahela registri koondamine.** Iga viiest tarnijast on oma registrikirje. Igaühel on oma DPA, SCC, alamtöötlejate nimekiri ja väljumisplaan. Registris on viis esimese tasandi kirjet enne personali koolituse tööriistade, identiteedi tööriistade, jälgimise tööriistade ja IaaS-i lisamist. Tarneahela vestlus on NIS2 mõttes registri haldamise vestlus sama palju kui turvavestlus. (Vaadake struktuuriargumendi jaoks [tarneahela postitust](/et/blog/nis2-supply-chain-self-hosted).)

**Artikli 23 aruandlusprotsess.** 24-tunnist varajast hoiatust, 72-tunnist teavitust ja ühekuist aruannet ei tooda automaatselt ükski viiest kategooriast. Need nõuavad SIEM-i, SOC-i (majasisest või allhanget) ja isikut, kes teab, kuidas esitada dokumente riiklikule CSIRT-ile. Väiksematel meeskondadel seda sageli ei ole. Esimene intsident on valus õppekogemus.

## Mida Rediacc koondab

Rediacc on üks juhtimistasand ühtse auditilogi, asendades nelja viiest kategooriast põhivõimaluse ise majutatud taristu jaoks.

**Backup** töötab kahes režiimis. Kuum on crash-consistent BTRFS hetktõmmis. Seisakut pole. Külm teeb peata-hetktõmmis-käivita tsükli. Mõlemad ajastavad systemd taimeritega. Mõlemad saadavad paljudesse sihtkohtadesse rclone'i kaudu. Mahud on LUKS-krüpteeritud. Operaator hoiab võtit. Rediacc OÜ ei näe kunagi lihtteksti. Vaata [Backup & Restore](/et/docs/backup-restore) ja [Cross Backup Strategy](/et/docs/cross-backup).

**DR**: sama primitiiv mis backup'il, lisaks `rdc repo migrate` masinate vahel andmete liigutamiseks, lisaks fork-primitiiv taastatud seisundi kiireks käivitamiseks paralleelmasinas. DR-sait võib olla teine Hetzner masin, OVH masin, kohapealne riiuliserver, kuhu iganes SSH ulatub. Andmete teel ei ole DR-tarnija pilve.

**Testandmed ja täisvõimsusel kloonimine** töötab BTRFS reflingil. Fork on konstantaja, olenemata repositooriumi suurusest. Täisvõimsusel tähendab andmeid, konfiguratsioone, konteinereid ja teenuseid. Forke 128 GB repositooriumit 7,2 sekundiga meie [PocketOS testis](/et/blog/i-tested-rediacc-against-the-pocketos-incident). Fork on praegune tootmine, mitte kärpitud lavastuskoopia. Vaata [Risk-Free Upgrades](/et/docs/risk-free-upgrades).

**Kiirtaaste**: `rdc repo backup pull` mis tahes rclone-sihtmärgist värskesse forki, mis käivitatakse fork-spetsiifilise alamdomeeni all, mida katab emRepositooriumi metamärgisertifikaat. Ei mingit DNS-i segadust, ei sertifikaadi tantsu.

**Ühtne auditilog.** 70+ sündmusetüüpi juhtimistasandil. Need katavad sisselogimised, API tokenid, konfiguratsiooni kirjutamised, repositooriumi elutsükli, varunduse, sünkroonimise, terminaliseansid ja masina toimingud. Ahel on räsiga lingitud operaatori tööjaamal. `rdc audit verify` kontrollib seda otsast lõpuni.

250 töötajaga keskturu olulise üksuse jaoks on koondamine neljalt nimetatud tarnijalt (backup, DR, testandmed, kiirtaaste) ühele. Üks litsents, üks auditilog, üks komplekt uuendamisotsuseid, üks registrikirje.

Viies kategooria, GRC, ei ole koondatud. Tuleme selle juurde tagasi.

## Mis jääb igal juhul teie eelarvesse

See on jaotis, mis määrab, kas ülejäänud postitus on aus. Kahe veeru tabel:

| Rediacc eemaldab | Jääb teie kanda, kulurea kaupa |
|---|---|
| Backup-tarnija litsents | GRC-platvorm (Drata, Vanta, OneTrust, AuditBoard, DataGuard) tarnijate registri, kontrollraamistiku atesteerimise, tõendite kogumise ja SOC 2 või ISO 27001 auditi toe jaoks |
| DR-saidi leping või DR-as-a-service rent | Sertifitseerimisauditi kulud (ISO 27001, SOC 2, BSI C5, kui neid vajate; Rediacc ise ei ole veel sertifitseeritud, nii et kannate selle kulu vahepeal ise) |
| Testandmete või maskeerimise tööriista litsents | Personali koolitus ja turvateadlikkuse eelarve (NIS2 artikkel 21(2)(g)) |
| Kiirtaaste litsents backup-tarnijal | Laiem ettevõtte MFA-lahendus; Rediacc'il on portaalil TOTP, mitte ettevõtte MFA-platvorm |
| | Penetratsioonitesti leping või autonoomne testimisplatvorm; Rediacc annab sihtkeskkonna, mitte testimisvõimekuse |
| | SIEM ja SOC artikli 23 tuvastamiseks ja aruandluseks; Rediacc annab kohtuekspertiisi tasemel artefaktid, mitte operatiivse aruandluskihi |
| | IaaS-tarnija (Hetzner, OVH, teie colo, teie bare metal); Rediacc töötab taristu peal, mitte selle asemel |
| | Programmi juhiv personal. Rediacc on tööriistade kiht, mitte turvameeskond |

Tabeli parem pool on pikem kui vasak pool. See on aus kuju, mida NIS2 maksab. Backup-ja-DR-ja-testandmete kattuvuse eemaldamine säästab reaalset raha ja reaalseid registrikirjeid; see ei muuda turvaprogrammi SaaS-tellimuseks.

Ostja, kes loeb seda ja järeldab "saan asendada Drata Rediacciga", valmistab oma audiitorile pettumuse. Õige lugemine on: andmetasandi tarnijate koondamine, mida Rediacc võimaldab, on see, mida GRC-tööriistad ei suuda teha, ja register-ja-tõendite töö, mida GRC-tööriistad teevad, on see, mida Rediacc ei tee. Need kaks on teineteist täiendavad.

Veel kolm linki, kui soovid süvitsi. Avalik kaardistus on aadressil [NIS2 and DORA](/et/docs/legal-nis2-dora). Laiem raamistik on aadressil [Compliance Overview](/et/docs/legal-overview). Rediacc'i kaubanduslik pool on aadressil [Subscription & Licensing](/et/docs/subscription-licensing).

## Viitestsenaarium, struktuurne mitte numbriline

Võtame 250 töötajaga Saksa tootmisettevõtte. II lisa "tähtis üksus" klassifikatsioon. Tootmisandmed 4 kuni 6 serveris, enamasti ise majutatud kahe ühe kuni kahe SaaS-tööriistaga (CRM, palgaarvestus). Aastane käive 80 miljonit eurot. Olemasolev turvameeskond 3 inimesest.

**Enne**, nende andmetasandi pakett:

- Veeam Data Platform Foundation, 24 000 eurot aastas
- Veeam Cloud Connect DR jaoks, 12 000 eurot aastas
- Omatehtud rsync-pluss-pg_dump skeem testandmete jaoks, tasuta litsentsilt, kuid maksab SRE-le poole päeva iga kahe nädala tagant
- Aastane penetratsioonitestimine, 22 000 eurot
- Drata GRC jaoks, 18 000 eurot aastas

Viis lepingut. Kaks neist (Veeam, Veeam Cloud Connect) on sama tarnijaga, kuid erinevate SKU-dega. Andmetasandi kulurea kirjed kokku 36 000 eurot aastas enne penetratsioonitestimist või GRC-d. Meeskond toodab aastase taastamistesti, ei mingeid pidevaid tõhususe tõendeid, ja tarnijate registri, millel on andmetasandil ainuüksi viis kirjet.

**Pärast**, Rediacciga Hetzneril ise majutatud töökoormuste jaoks:

- Rediacc Business tier, 8400 eurot aastas (katab nende repositooriumi suuruse)
- Hetzner IaaS esmase ja teisese jaoks, 9600 eurot aastas kokku (juba eelarves; uut kulurea kirjet ei lisandu)
- Penetratsioonitesti leping jääb (22 000 eurot)
- Drata jääb (18 000 eurot)
- Omatehtud testandmete skeem lükatakse kasutusest välja; SRE pool päeva iga kahe nädala tagant läheb igal nädalal tõhususe rutiini käitamisele

Andmetasandi koondamine: 5 kulurea kirjet väheneb 1-le (Rediacc) pluss olemasolev IaaS-rida. Tarnijate registri andmetasandi jaotis langeb 5 kirjelt 2-le. Pideva tõhususe lugu on nüüd iganädalased harjutused räsi-aheldatud auditilogi tõenditega; taastamistesti lugu on nüüd toetatud `rdc machine backup status` väljundiga ja iganädalase taastamise harjutusega.

Numbrid on illustratiivsed, mitte lubadused. Teie pakett on erinev. Kuju, neli kuni viis kulurea kirjet koondumas ühte pluss olemasolev IaaS, on see, milline näeb välja reaalne ostjavestlus.

## Märkus selle kohta, mis see ei ole

See postitus ei ole Veami mahakirjutamine ega TCO kalkulaator. Veeam juhib Euroopas suurimat VM-backup'i turuosa mõjuvatel põhjustel: nende toode on küps, nende partnerivõrgustik on lai, nende NIS2 turundus on tugev, ja ostja, kes valib Veeami 2026. aastal, ei tee viga. Viitestsenaariumi arvud on illustratiivsed, pärit tegelikest ostjavestlustest, mitte võrdlusalustest. Käivitage struktuurianalüüs oma lepingute vastu.

Mis see on: ostjapoolne raamistik CFO jaoks, kes uuendab backup'i, DR-i või vastavuslepingut järgmise kaheteistkümne kuu jooksul ja soovib teada, mida ise majutatud juhtimistasand kulurea kirjetega muudab.

## Mida teha järgmisena

Kui suundute uuendusetsüklisse ja eelarve on avatud, kolm konkreetset sammu:

1. **Võtke välja eelmise aasta kolm suurimat turva- ja taristu kulurea kirjet.** Saatke need oma DPO-le, CISO-le ja audiitorile. Küsige, millised neist olid juba enne NIS2 kattuvad, enne kui see nähtavaks sai. Enamik meeskondi leiab vähemalt ühe kattuvuse, mille eest on makstud.
2. **Kaardistage oma praegune andmetasandi pakett ülaloleva viie kategooria nimekirja vastu.** Märkige, milliste kategooriate jaoks on teil üks tarnija, milliste jaoks kaks ja milliste jaoks pole ühtegi. "Pole" lahtrid on lüngad, mida NIS2 pinnale toob.
3. **Käivitage tarnijate registri harjutus [tarneahela postitusest](/et/blog/nis2-supply-chain-self-hosted)** iga andmetasandi tarnija jaoks. Lugege registrikirjeid. Arv on tavaliselt suurem, kui meeskond ootas.

Kui oleme lühikeses nimekirjas, on pakkumine konkreetne. Saatke oma kolm suurimat kulurea kirjet eelmise aasta turva- ja taristueelarvest. Ütleme teile, milliseid saab koondada ja milliseid mitte, kirjalikult, ühe nädala jooksul. Vastus sisaldab lünki, sest lünkade nimetamine on see, mis muudab ülejäänud vastuse usaldusväärseks.

Veel kolm dokumenti, kui soovid sügavamale minna. [Nullkuluga backup](/et/docs/zero-cost-backup) selgitab, miks töötame ladustamisküljel turuosalistest kergemini. [Cross Backup Strategy](/et/docs/cross-backup) katab mandritevahelist DR-i. [Subscription & Licensing](/et/docs/subscription-licensing) on kaubanduslik pool.
