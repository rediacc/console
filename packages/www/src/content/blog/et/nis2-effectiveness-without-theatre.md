---
title: "Teie aastane läbitungimistest on vastavuse teater. NIS2 Article 21(2)(f) tegi sellest probleemi."
description: "Pidev tõhususe hindamine, konstantajaga fork mis muudab selle odavaks, ja Article 23 aruandluse tähtaeg mida ei saa täita ilma kohtuekspertiisi taseme artefaktideta."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - sre
  - dr-testid
  - tõhusus
  - intsidentide-teatamine
featured: false
language: et
sourceHash: "21965e5d5e9f25d5"
sourceCommit: "b05326db48cfbe9d4bb41ade1b723df93f1bc604"
translatedFrom: en
---

> **Kokkuvõte.** Enamik turbeprogramme testib taastumist kord aastas, stagimiskeskkonna vastu, mis on tootmisest tehtud möödunud suve paiku. Nad tellivad läbitungimistesti keskkonna vastu, mis ei näe välja nagu tootmine, saavad puhta raporti ja esitavad selle. NIS2 Article 21(2)(f) tutvustas just fraasi, millele audiitorid hakkavad tugevalt toetuma: "tööpõhimõtted ja menetluskord küberturvalisuse riskijuhtimismeetmete tõhususe hindamiseks". Iga-aastane ei ole pidev. Aegunud staginskeskkond ei ole testitav süsteem.
>
> - Direktiivi lugemine: 21(2)(e) ja (f) koos nõuavad taastumis- ja turvalisuse testimist, mis tegelikult toimib, nõudmisel, praeguse tootmise vastu.
> - Delphix-klassi tööriistade, Veeam Instant Recovery või Rubrik Live Mount'iga õigesti tegemise kulu on see, mis paneb enamiku tiime vaikselt valima stagimise.
> - Kui tootmise fork võtab seitse sekundit, pöördub majanduslik loogika. Iganädalased harjutused muutuvad realistlikuks. Pidev tõhusus muutub dokumenteeritavaks.
> - Article 23 aruandlus (24-tunnine varajane hoiatus, 72-tunnine teavitus, ühe kuu raport) on täitmatu ilma kohtuekspertiisi taseme artefaktideta. Artefaktid on meil; SOC ja SIEM ja ENISA esitamise töövoog on endiselt teie kanda.

Astuge mis tahes keskmise suurusega SRE tiimi ja esitage üks küsimus: millal tegite viimati täieliku otsast lõpuni taastumise -- mitte varundusfaili kontrollimist, vaid taastatud süsteemi tegelikku ülesseadmist koos rakenduste, andmebaaside ja konfiguratsioonidega ning selle kontrollimist, et see toimib? Aus vastus enamikus tiimides on: "eelmise aasta tabeliharjutuses." Seejärel läheb kõik tagasi tavarutiini.

NIS2 Article 21(2)(f) tutvustab fraasi, millele audiitorid hakkavad tugevalt toetuma:

> "tööpõhimõtteid ja menetluskorda küberturvalisuse riskijuhtimismeetmete tõhususe hindamiseks"

See ei ütle "igaastane." See ütleb "tööpõhimõtted ja menetluskord." Kõrvuti Article 21(2)(e)-ga, mis kohustab:

> "võrgu- ja infosüsteemide hankimise, arendamise ja hooldamise turvalisust, sealhulgas nõrkuste käsitlemine ja avalikustamine"

on kohustus pidev, mitte perioodiline. 2024. aasta ENISA rakendamisjuhis (Implementing Regulation (EU) 2024/2690 IV lisa) <!-- nis2-quote-skip: ENISA Implementing Regulation 2024/2690, separate source --> kinnitab suunda fraasidega nagu "pidev hindamine" ja "dokumenteeritud tõendid testimise kohta, mis hõlmab praeguseid tootmiskeskkondi, mitte pärand- ega stagimismomentülesvõtteid."

Kui teie tõhususe lugu on "aastane läbitungimistest stagimise vastu," tuleb 2026. aasta ebamugav.

See postitus on mõeldud SRE juhtidele, ops-juhitatele ja turbeinseneridele, kes harjutusi tegelikult läbi viivad. See on ka postitus, mis nimetab kiilu, millele konkurent igas vastupakkumises toetub: hallatud aruandlus ja SIEM-i konnektori teenused Article 23 tähtaegade jaoks. Me ei lahenda seda. Me anname teile artefaktid. Aruandluse töövoog, SOC, ENISA esitamise mootor -- need on endiselt teie kanda.

## 21(2)(e) ja (f) koos lugemine

Article 21 loetleb kümme miinimummeedet. Kaks neist puudutavad seda, kuidas te ehitate ja kuidas te kontrollib.

e) **Hankimise, arendamise ja hooldamise turvalisus**: see on pakkumispoole meede. Kui võtate vastu CVE-plaastri, kui lähete laivi uue mikro-teenusega, kui teostate hooldusakna, tuleb muudatust valideerida tegeliku keskkonna vastu, kuhu see läheb. ENISA juhis on selgesõnaline, et stagimiskeskkonnad, mis erinevad tootmisest andmekuju, mahu, saladuste või konfiguratsiooni poolest, ei täida turvaluse-asjakohaste muudatuste testimise kohustust.

f) **Tõhususe hindamine**: see on kontrollimeede. Mis iganes kontrollid teil on, vajate tööpõhimõtteid ja menetluskorda, et kinnitada, et need tegelikult töötavad. Sõnastus "tõhusus" teeb päristööd. See on vahe "meil on varukoopia" (kontroll olemas) ja "me tõestasime, et saame sellest möödunud teisipäeval taastada ja taastatud süsteem läbis suitsutesti" (kontroll on tõhus) vahel.

Koos loetuna nõuavad kaks meedet, et turbe-asjakohased muudatused testitakse praeguste tootmisega samaväärsetes keskkondades ja et testimine toodab tõendeid muudatuse toimimise kohta. Iga-aastane on liiga harv. Aegunud staging on vale sihtmärk. Taastamine, mida pole valideeritud, ei ole tõhus.

Traditsiooniline vastus sellele kohustusele on see, mida enamik tiime juba teeb: kuulutada staging tootmisesarnaseks, viia harjutused läbi stagimise vastu aastasel sagedusperioodil, kirjutada käsiraamat, mis kirjeldab, mis juhtuks reaalse intsidendi korral, ja loota, et regulaator ei esita liiga palju küsimusi. See töötas siis, kui regulaator oli GDPR DPA ja intsident oli privaatsusevent. NIS2 paneb erinevalt regulaatori istmele (riiklik CSIRT, või BSI Saksamaal, ANSSI Prantsusmaal, ACN Itaalias), ja see regulaator esitab operatiivseid küsimusi.

## Aegunud stagimise lõks

Kolm asja teevad stagimise mitte-tootmiseks ajaks, kui enamik tiime selle vastu testib.

**Andmekuju**: tootmisandmetel on pikasabaga äärejuhud. Klient 8 000-märgilise märkuste väljaga, pärandkonto NULL-iga seal, kus igal teisel real on väärtus, ühendatud tabel, mis tagastas 12 miljonit rida ühele rentnikule, kes importis kogu oma CRM-i ajaloo. Stagimises on 1% tootmismahust ja pikasaba pole valimis.

**Mastaap**: päring, mis stagimises 10 000 rea vastu 50 ms-ga tagastab, tagastab tootmises 12 miljoni rea vastu 8 sekundiga. Läbitungimistesti stsenaarium, mis stagimises kurnatuse haavatavust ei leia, leiab selle tootmises kohe. Haavatavuse kuju sõltub andmemastaabist.

**Konfiguratsioonidrift**: tootmine on kogunud keskkonnamuutujaid, IAM rolle, võrgupoliitikaid, kolm korda roteeritud saladusi, eelmisel nädalal uuendatud SSL-sertifikaati, funktsiooniliputähe, mis pidanuks märtsis välja lülitatama, aga jäi sisse. Stagimises on puhas koopia eelmise suve konfiguratsioonist lisaks sellele, mis lisati viimase projekti jaoks. Deltad on täpselt seal, kus turbeaugud peituvad.

Niisiis, kui plaaster stagimises läbib, on tiimi enesekindlus valesti paigutatud. Kui läbitungimistest raporteerib stagimise vastu puhta tulemuse, on raport eksitav. Kui taastamisharjutus taastab stagimise edukalt, pole tiim tootmistaastamist valideerinud.

Audiitorid 2026. aastal ei vaidlusta, kas staging on piisavalt hea. Nad küsivad tõendeid testimisest praeguse tootmise vastu. Tõendid peavad olema ajatempliga, peavad näitama, et testitav süsteem nägi testi ajal välja nagu tootmine, ja peavad näitama, et test andis tulemuse.

Enamik tiime ei suuda selliseid tõendeid täna esitada, kuna praeguse tootmise vastu harjutuste läbiviimise kulu on traditsiooniliste tööriistadega keelav.

## Õigesti tegemise kulu traditsiooniliste tööriistadega

Turul on vastuseid. Vastused on kallid.

**Veeam Instant Recovery**: seadistada VM otse varukoopiast, ühendada see, suunata võrguliides selle poole. Kasutatakse rakendusühtsete taastamiskatsetuste jaoks. Suuteline testima taastamist hiljutise varukoopia vastu; stagimiskeskkonnast saab taastatud varukoopia. Mahtudelt kerge, kuna kettalugemised tulevad varundushoidlast. Kulu: Veeam Data Platform Premium litsentseerimise maht skaleerub VM arvu järgi ja taastamistesti peab ikkagi planeerima ning käitama insener. Enamik tiime teeb seda kord kvartalis.

**Rubrik Live Mount**: sarnane kontseptsioon, momentülesvõtte kohene ühendamine testimiseks. Parem integratsioon pilvenatiivse töökoormusega. Sama operatiivne muster. Sama iga-testi insenerlikud üldkulud.

**Delphix (Perforce DevOps Data)**: andmevirtualiseerimise tööriist, mis loob arenduse ja testimise jaoks lähteandmebaaside peaaegu koheseid kloone. Lahendab "tahame dev-is tootmiskujulist andmeid" probleemi. Ainult andmebaasid. Ei klooni rakenduse teenuseid, konfiguratsioone, saladusi ega konteineri olekut. Aastane litsents läheb keskmise turu tiimidele kuuekohalisse arvusse.

**Tonic.ai, Redgate Test Data Manager**: andmete maskeerimise ja sünteetiliste andmete lähenemisviisid. Lahendavad privaatsuse ja realism-vahelise kompromissi arendus- ja testikeskkondades. Tootmisrealistlik andmekuju ja mahu osas. Mitte täisvirna kloonid. Mitte kavandatud turvetestimise stsenaariumite jaoks, kus rakenduse konfiguratsioon on oluline.

**Kohandatud ehitamine**: võtta kuumvarukoopia, taastada see paralleelkeskkonda, käivitada test, lammutada see. Kontseptuaalselt võimalik. Operatiivselt mitme päeva inseneritöö harjutuse kohta. Tiim teeb seda ühe korra, kuna oli sunnitud, ja siis mitte kunagi enam.

Struktuuriline probleem on see, et tootmiskloonaamine, täisvirna ja rakenduse olekuga, on ajalooliselt nõudnud kas (a) baidi-põhist andmeedastust (aeglane ja kallis mastaabis), (b) momentülesvõttel põhinevat VM kloonamist (töötab IaaS jaoks, katkeb konteineritega ja Kubernetesega), või (c) andmevirtualiseerimist (ainult andmebaasid). Kõik kolm lähenemist kannavad iga-testi kulu, mis skaleerub keskkonna suurusega.

Kui iga-testi kulu skaleerub suurusega, muutuvad harjutused haruldasteks sündmusteks. Haruldased sündmused ei täida pidevat tõhususe hindamist.

## Mis muutub, kui tootmise fork võtab seitse sekundit

Rediacc kasutab hoidla forkimiseks BTRFS reflinke. Mehhanism on failisüsteemi taseme koopia-kirjutamisel põhinev: fork jagab plokke vanemaga seni, kuni kumbki pool kirjutab uusi andmeid, millal ainult muutunud plokid lahknevad. Fork operatsioon ise on konstantaeg, sõltumata hoidla suurusest.

Meie [PocketOS testi postituses](/et/blog/i-tested-rediacc-against-the-pocketos-incident), tegime 128 GB tootmishoidlast forki 7,2 sekundiga otsast lõpuni. Reflinkk ise oli 2,3 sekundit. Suurem osa ülejäänust on uue Dockeri deemoni seadistamine, LUKS-krüptitud mahu ühendamine ja teenuseviru ülesseadmine uues loopback-IP alamvõrgus.

Forgi kuju on sama oluline kui kiirus. Rediacc fork on täisvirna. Forkitud hoidla sisaldab:

- LUKS-krüptitud mahtu koos kõigi andmefailide ja andmebaasi olekuga.
- Dockeri deemoni konfiguratsiooni ja konteineri olekut.
- Rediaccfile elutsükli konkse (`up`, `down`, `info`).
- Hoidla loopback-IP alamvõrku (uus `/26` forkimiseks välja lõigatud).
- Hoidla võrgu ID-d, deemoni soklat ja ühendamise nimeruumi.

Mida see vaikimisi ei sisalda, on saladused, mida teie teenused vajavad väliste SaaS-ide rääkimiseks (Stripe, meiliedastajad, DKIM-võtmed, veebihaagi allkirjastamisvõtmed). Nende jaoks hoiab `rdc repo secret` mandaadid forgi pildist täielikult eemal, nii et välised SaaS-kutsed forkist on eksplitsiitsed, mitte päritud. Saladuste mudeli kohta vaata [Hoidlad](/et/docs/repositories).

See kuju -- täisvirna eksplitsiitset saladuste käsitlemisega -- on see, mis muudab forgi turvetestimise sihtmärgina sobivaks. Fork on tootmissüsteem, praeguste tootmisandmetega, praeguse tootmiskonfiguratsiooniga, praeguse konteineri olekuga, kümme sekundit tagasi. See on süsteem, mida audiitor tahab, et te testiksite.

Dokumenteeritud kasutusjuhtude jaoks vaata [Riskivabad uuendused](/et/docs/risk-free-upgrades) ja [Juhend: Forkimine](/et/docs/tutorial-forking).

## Pidev tõhususe rutiin, mida saate iganädalaselt käivitada

Siin on konkreetne rutiin, mis rahuldab Article 21(2)(e) ja (f) tootmishoidla jaoks, mida üks SRE saab käivitada iganädalaselt.

**1. samm**: Forki tootmine.

```bash
rdc repo fork --parent prod-app --tag effectiveness-2026w19 -m hostinger
```

Fork on nimetatud ISO nädalaga, nii et auditilogi on isekuvav. Hoidla on üleval forgi-spetsiifilise alamdomeeni all (`<service>-fork-effectiveness-2026w19.prod-app.<machine>.<basedomain>`) ja vanema metamärksertifikaat katab seda. Uut TLS kätlust ei toimu.

**2. samm**: Rakenda testitav plaaster forkis.

```bash
rdc repo up --name prod-app:effectiveness-2026w19 -m hostinger
rdc term connect -m hostinger -r prod-app:effectiveness-2026w19 -c "apt-get install -y openssl=3.5.5-1"
```

Term-seanss töötab privilegeerimata `rediacc` kasutajana (UID 7111), eraldi ühendamisnimeruumis, kusjuures `DOCKER_HOST` on ulatusega forgi deemoni soklale. Risthoidla juurdepääs on blokeeritud tuuma tasemel (fork ei pääse tootmise loopback-alamvõrku). Isolatsioonimudeli kohta vaata [Arhitektuur § Dockeri Isolatsioon](/et/docs/architecture).

**3. samm**: Käivita suitsutets forgi vastu.

```bash
curl -fsS https://app-fork-effectiveness-2026w19.prod-app.hostinger.example.com/health
# (teie projekti-spetsiifiline suitsutets läheb siia)
```

**4. samm**: Käivita taastamisharjutus. Kasuta tootmise viimast kuumvarukoopiat, tõmmatud forgi-joondatud sihtmärki.

```bash
rdc repo backup pull --from offsite-b2 --name prod-app:restore-2026w19 -m hostinger
rdc repo up --name prod-app:restore-2026w19 -m hostinger
# kontrolli, et taastatud fork vastab samale suitsutestile
curl -fsS https://app-fork-restore-2026w19.prod-app.hostinger.example.com/health
```

See on taastamistest, mida 21(2)(c) ja (f) küsivad: mitte "varundusfaili terviklus kontrollitud", vaid "taastatud süsteem vastab suitsutestile."

**5. samm**: Auditilogi tulemus, seejärel lamuta.

```bash
rdc audit log --since "1 hour ago" > /tmp/effectiveness-2026w19.json
rdc repo destroy --name prod-app:effectiveness-2026w19 -m hostinger --force
rdc repo destroy --name prod-app:restore-2026w19 -m hostinger --force
```

Auditilogi jäädvustab iga sammu (forgi loomine, repo up, term-seansid, varunduse tõmbamine, repo hävitamine). See on räsiaheldatud. `rdc audit verify` operaatori tööjaamal kinnitab, et ahelat pole pärast sündmuste kirjutamist muudetud. Auditi mudeli kohta vaata [Konto turvalisus § CLI turvahoiak AI agentide jaoks](/et/docs/account-security).

Rutiini kogu seinakellajaeg 128 GB hoidla puhul on alla 15 minuti. Suurem osa on suitsutets ja varundustõmbamise võrgu edasi-tagasi aeg. Fork operatsioonid ise on sekundid igaüks.

Üks SRE, kes teeb seda kord nädalas, toodab 52 ajatempliga, auditilogi kirjega tõhususe kirjet aastas. See on tõendite kuju, mida audiitor küsib.

Laialdasema taastumiloo jaoks, sealhulgas maskinaüleste ja mandritevaheliste harjutuste kohta, vaata [Ristivarundusstrateegia](/et/docs/cross-backup) ja [Varundus ja taastamine](/et/docs/backup-restore). Osalise korruptsioonisündmuse ajal ajas-tagasi semantika kohta vaata [Ajas-tagasi taastamine](/et/docs/time-travel-recovery).

## Article 23: aruandluse tähtaeg, mida ei saa täita ilma artefaktideta

NIS2 Article 23 on intsidentide aruandluskell. Kolm tähtaega:

- **24 tundi** olulisest intsidendist teadlikusaamisest: varajane hoiatus riiklikule CSIRT-le või pädevale asutusele. Näitab, et intsident toimub, ja annab esialgset teavet piiriülese mõju kohta.
- **72 tundi** teadlikusaamisest: täielik intsidentide teavitus. Sisaldab tõsiduse hindamist, esialgseid kompromissi indikaatoreid, ohu tüüpi ja teadaolevat mõju.
- **Üks kuu** teavitusest: lõpparuanne. Üksikasjalik kirjeldus, algpõhjus, rakendatud leevendusmeetmed, käimasolev risk.

See on tihe kell. See on ka kell, mis käib siis, kui intsident on veel käimas. Kõige valusam versioon Article 23-st on see, kus tiim taastab teenuseid, säilitab kohtuekspertiisi tõendeid, kooskõlastab õiguskaitseasutustega, brifib juhtmeeskonda ja kirjutab varajast hoiatust -- kõik esimese 24 tunni jooksul.

Standardsed varundamistööriistad sunnivad kompromissile: taasta süsteem teenuse tagaamiseks, või säilita süsteem uurimiseks. Kui taastad varukoopiast, on kompromissi elavad tõendid kadunud. Kui külmutad kompromiteeritud süsteemi uurimiseks, ei teeni sa kliente. Mõlemad on halvad Article 23 tähtajas.

Fork mehhanism lahendab kompromissi. Kompromiteeritud olekut saab forkida (vanemhoidlast saab kohtuekspertiisi momentülesvõte) ja paralleelne fork saab käivitada viimase puhta varukoopia alusel liikluse teenindamiseks. Kohtuekspertiisi fork on ainult lugemiseks analüüsi jaoks. Teenindav fork vastab klientidele. Mõlemad eksisteerivad samaaegselt samal masinal, jagades plokke reflinki kaudu, mistõttu see on operatiivselt taskukohane.

Konkreetselt intsidendi korral:

```bash
# Snäppi kompromiteeritud olek kohtuekspertiisiks. Fork on momentülesvõte.
rdc repo fork --parent prod-app --tag forensic-2026-05-09T14-23Z -m hostinger

# Käivita teenindav fork viimasest puhtast varukoopiast. Erinev tag.
rdc repo backup pull --from offsite-b2 --name prod-app:serving-2026-05-09T14-30Z -m hostinger
rdc repo up --name prod-app:serving-2026-05-09T14-30Z -m hostinger
# Lõika liiklus uuele teenindavale forkile DNS-i või marsruudi serveri kaudu.
```

Kohtuekspertiisi fork vastab regulaatori küsimusele 60. tunnil: "näidake meile teie süsteemide täpset olekut kompromissi hetkel." Teenindav fork vastab kliendi küsimusele. Üle 70 sündmusega auditilogi vastab küsimusele "kes tegi mida ja millal" räsiaheldatud, kontrollitaval viisil.

See on see, mida Rediacc operaatorile annab. Mida me ei anna:

- **SIEM-i**. Me ei edasta Splunki, Datadog'i, Sentineli ega teie koduehitatud virna. Auditilogi on lokaalne JSONL operaatori tööjaamal; selle torustamine SIEM-i on operaatori integratsioonitöö.
- **SOC-i**. Me ei käita 24x7 tuvastamisvõimekust. Me ei tooda hoiatusi. Me ei tee triaaži.
- **Hallatud aruandlust**. Me ei esita ENISA aruannet. Me ei koosta varast hoiatust. Me ei koordineeri riikliku CSIRT-ga teie nimel.

See on kiil, mida konkurent meie vastu kasutab. Veeam Data Platform koos Coveware integratsioonidega, Rubrik nende hallatud teenuste tiivaga ja mõned spetsialiseeritud IR-hoidiku ettevõtted (Mandiant, Kroll, S-RM Euroopas) müüvad täpselt operatiivset kihti, mida Rediacc ei müü. Vastupidine väitmine on turundusliigutus, mis viib meid hätta. Kaitstav positsioon on: Rediacc annab teile kohtuekspertiisi taseme artefaktid, mida need teenused ise ei suuda toota; need teenused annavad teile operatiivse aruandluskihi, mida Rediacc ei suuda pakkuda. Need täiendavad üksteist. NIS2 programm vajab mõlemat.

## Mida Rediacc teie eest ei käita

Kaks asja, mida SRE peaks teadma ette, enne kui otsustab, et ülejäänud postitus on huvitav.

**Rediacc ei käita läbitungimisteste**. Fork-sihtmärgina on keskkond, mitte testimisvõimekus. Päris adversatiivsed läbitungimistestid on endiselt teie punane tiim või teie lepinguline testettevõte (Pentera, Horizon3.ai autonoomsete jaoks; spetsialiseerunud konsultatsioonifirmad inimjuhtidega). Rediacc eemaldab nende vabanduse, et testkeskkond oli ebareaalne. See ei eemalda testi kulu.

**Rediacc ei kirjuta teie käsiraamatuid**. Ülaltoodud CLI käsud on liikuvad osad. Otsused selle kohta, millal forkida, millal üle lülituda, kuidas klientidega suhelda, millal kaasata õiguskaitseasutused, on käsiraamatu otsused. Neid tuleb endiselt teie tiimil koostada, harjutada ja uuendada. NIS2 Article 21(2)(b) (intsidentide käsitlemine) on protsessikohustus, mitte tööriistakohustus, ja me rahuldame osa sellest, mitte kõike.

Hangete poolse ulatuse kohta (sertifikaadid, GRC, tarnija registri kokkukukkumine) vaata [tarneahela postitust](/et/blog/nis2-supply-chain-self-hosted). Kulude poolse ulatuse kohta (mis jääb eelarvesse pärast ise majutatud juhtimistasandit) vaata [reaalse arve postitust](/et/blog/nis2-the-real-bill).

Nende õige lugemine: Rediacc on tööriistakiht, mitte turbepagramma. See eemaldab vabandused ja toodab tõendeid. See ei käita programmi teie eest.

## Mida audiitor 2026. aastal näha tahab

Kolm artefakti. Tooda need ja Article 21(2)(e) ja (f) vestlus läheb lühikeseks.

**Artefakt 1: forgi-harjutuse sagedus**. Ajatempliga logi tõhususe harjutustest, mis on läbi viidud iganädalaselt või iga kahe nädala tagant jooksva kaheteistkümne kuu jooksul. Iga kirje näitab vanemhoidlat, forgi tagi, testitavat plaastrit või muudatust, suitsutesti tulemust ja lammutuse ajatempli. `rdc audit log --since` toodetud auditilogi jäädvustab kõike seda.

**Artefakt 2: nende harjutuste auditilogi, räsiaheldatud**. Räsiahel auditilogi on see, mis muudab "käitasime 47 harjutust eelmisel aastal" väitest tõendiks. `rdc audit verify` valideerib ahela otsast lõpuni. Valideerimisetulemus on üks käsu väljund, mida audiitor saab uuesti käivitada.

**Artefakt 3: varunduse kontrollimise rada**. Iga ajakavastatud varundusstrateegiale toodab systemd üksus oleku lisafaili `/var/run/rediacc/cold-backup-<guid>.status.json` hoidla ja käituse kohta ning lõpliku kokkuvõtte logirea. `rdc machine backup status` esitab mõlemaid. Koos 4. sammust iganädalase taastamisharjutusega annab see audiitorile "varundus-ja-taastamine-testitud" raja, mitte ainult "varundus-võetud" raja. Diagnostilise pinna kohta vaata [Jälgimine](/et/docs/monitoring).

Artefaktid koos vastavad küsimusele "kas teie kontrollid on tõhusad" ajatemplite ja räsiaheldatud tõenditega, mitte kinnitustega.

## Mida see tähendab järgmiseks kvartaliks planeerimiskoosolekuks

Kui teie tiim suundub Q3 planeerimisse ja Article 21(2)(f) on turbe mahajäämuses, kolm konkreetset sammu:

1. Auditeerige oma praegust tõhususe lugu. Tõmmake viimase kaheteistkümne kuu läbitungimistestide aruanded, taastamisharjutused ja plaastrite valideerimispiletid. Loendage, mitu neist sihtis praegust tootmist. Aus arv on tavaliselt alla viie.
2. Valige üks tootmishoidla ja käivitage ülaltoodud iganädalane rutiin selle vastu kuu aega. Rutiin on kujundatud ühe SRE poolt käitatavaks ilma ajakavastamislisakuluta. Pärast nelja nädalat on teil neli ajatempliga tõhususe kirjet; see on rohkem kui enamik tiime toodab aastas.
3. Viige läbi vestlus selle kohta, kes katab SIEM-i, SOC-i ja Article 23 aruandluse töövoo. Kui vastus on "me pole nii kaugele jõudnud," on õige koht alustamiseks mitte Rediacc, vaid 24x7 tuvastamisvõimekus. Me täiendame seda vestlust; me ei ole selle algus.

Kui soovite näha forgi ajastust oma suurimal hoidlal, on pakkumine lihtne. Käitage seda kõnega meiega. Kui fork võtab kauem kui kümme sekundit, ei võlgne te meile midagi. Kui see võtab seitse, veedame ülejäänud kõne rutiini läbi vaatamises teie virna peal.

Struktuuriline kululugu (mis kukub kokku ülejäänud turbepinult ja mis jääb eelarve ritta) on kaaspostituses [reaalse arve](/et/blog/nis2-the-real-bill) kohta. Tarnija registri ja hangete nurga jaoks vaata [Article 21(2)(d) ja ise majutamine](/et/blog/nis2-supply-chain-self-hosted).

Võimekuste avaliku kaardistamise jaoks NIS2 artiklitele vaata [NIS2 ja DORA](/et/docs/legal-nis2-dora).
