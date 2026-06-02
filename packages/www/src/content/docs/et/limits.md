---
title: Piirangud ja kvoodid
description: >-
  Viide Rediacc hoidlate, teenuste, võrgu ja salvestuse suhtes
  kohaldatavatele piirangutele, maksimumidele ja kvootidele.
category: Reference
order: 99
language: et
sourceHash: "8f29c515be1b7fb4"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Piirangud ja kvoodid

See leht loetleb Rediacc juurutuste suhtes kohaldatavaid kõvasid ja pehmeid piiranguid. Loe seda enne mahu planeerimist, et teaksid, millised laed on olemas ja millised mitte.

---

## Teenused hoidla kohta

Iga hoidla toetab kuni **61 teenust** samaaegselt.

See on kõva piirang, mis on määratud igale hoidlale eraldatud võrguaadressi ruumiga. Iga teenus saab oma spetsiaalse privaatse IP-aadressi ja iga hoidla aadressiblokk mahutab täpselt 61 teenuse pesa.

Kui lähenete sellele piirangule, konsolideerige väiksemaid teenuseid (nt teisaldage kõrvalmoodulit või jälgimisagendid eraldi hoidlasse oma eralduspiiriga) või refaktoreerige, et vähendada ühe rakenduse sees iseseisvalt töötavate protsesside arvu.

---

## Hoidlad masina kohta

Rediacc ei jõusta kõva ülempiiri. Praktiline piirang sõltub teie masina ressurssidest:

| Ressurss | Mõju |
|----------|--------|
| Kettaruum | Iga hoidla on krüpteeritud kettapilt. Masin 1 TB kasutatava salvestusruumiga saab hoida palju hoidlaid, kuid kõikide piltide kogusuurm peab mahtuma andmehoidla basseini. |
| RAM | Iga töötav hoidla käivitab oma Dockeri deemoni ja konteinerid. Mälukasutus sõltub teie töökoormustest. |
| CPU | Paralleelsed hoidla toimingud (käivitamine, varundamine, hargnemine) lisavad ajutist CPU koormust. |

**Tüüpilised juurutused** käitavad 10 kuni 50 hoidlat masina kohta probleemideta. Masinad 32 GB+ RAM ja 500 GB+ salvestusruumiga käitavad regulaarselt 100+ hoidlat.

### Süsteemiülene võrgu-ID piirang

Igale hoidlale määratakse unikaalne **võrgu-ID**, mis on number, mida kasutatakse selle privaatse IP-aadressi vahemiku arvutamiseks. See bassein on jagatud kõikide masinate ja hoidlate vahel, mida haldab sama Rediacc konfiguratsioon.

| Piirang | Väärtus |
|-------|-------|
| Kokku saadaolevaid võrgu-ID-sid | ~261 944 |
| Ulatus | Konfiguratsiooni kohta (jagatud kõikide masinate vahel konfiguratsioonis) |

Kui hoidla kustutatakse, vabastatakse selle võrgu-ID ja see muutub taaskasutamiseks kättesaadavaks. Rediacc eraldab ID-sid järjestikku ja otsib vabasid lünki ainult siis, kui edasmine loendur läheneb lae tipule. Praktikas ei jõuta selle piiranguni kunagi. See eeldaks sadade tuhandete hoidlate loomist ja jälgimist ühe konfiguratsiooni eluea jooksul.

---

## Hargnemised

Hoidla aktiivsete hargnemiste arvule piirangut ei ole. Iga hargnemine on täielik kirjutamisel kopeeriv kloon koos oma krüpteeritud salvestuse, võrguaadresside ja Dockeri deemoniga. Hargnemised tarbivad kettaruumi proportsionaalselt pärast loomist neile kirjutatud andmetega (mitte täisvanema suurusega).

---

## Välisportid

### Alati aktiivsed pordid

Pordid avatakse ainult siis, kui konfigureerite avaliku IP aadressi `rdc config infra set --public-ipv4` abil. Kuni seda ei tehta, ei ole masinal ühtegi avatud porti. Pärast konfigureerimist:

| Port | Protokoll | Eesmärk |
|------|----------|---------|
| 80 | TCP | HTTP: Traefiki käsitsus; tagastab 404 konfigureerimata domeenide jaoks, ei edasta ühelegi teenusele |
| 443 | TCP | HTTPS: sama mis eespool; päringud ilma sobiva marsruudita lükatakse proksi kihil tagasi |
| 10000--10010 | TCP | Dünaamiline vahemik Rediacci hallatava TCP edastamise jaoks |

HTTP/HTTPS erinevad toortest TCP-portidest: isegi kui 80 ja 443 on avatud, valideerib pöördproksi iga päringu selgesõnalise marsruutimistabeli suhtes. Ilma konfigureeritud teenuse ja sobiva domeenita ei jõuta ühelegi rakenduse koodini ega paljastata andmeid.

### Valikuline TCP/UDP edastamine

Kõik teised pordid (andmebaasid, vahemälud, sõnumamaaklerid, DNS, post) on **vaikimisi suletud** ja tuleb selgesõnaliselt avada. See hoiab masina ründepinna minimaalse.

Pordi paljastamiseks konkreetsest teenusest:

```yaml
labels:
  - "rediacc.tcp_ports=5432"   # expose PostgreSQL from this container
  - "rediacc.udp_ports=53"     # expose DNS from this container
```

Pordi avamiseks masina tasemel (kättesaadav kõikidele teenustele):

```bash
rdc config infra set -m server-1 --tcp-ports 25,587,993   # mail server
rdc config infra push -m server-1
```

> Ärge kunagi paljastage andmebaasi või vahemälu porte väliselt, välja arvatud juhul, kui teil on konkreetne vajadus. Kasutage veebiteenustele HTTPS automaatmarsruute ja hoidke salvestusteenused sisemised.

---

## Andmehoidla

Andmehoidla on fikseeritud suurusega bassein, mis luuakse masina esimesel seadistamisel. Selle suurus ei kasva automaatselt.

- **Minimaalne soovitatav suurus**: 50 GB
- **Maksimaalne suurus**: piiratud teie kettaga. Üks bassein võib hõlmata täielikku ketast.
- **Suuruse muutmine**: kasutage `rdc datastore resize` olemasoleva basseini laiendamiseks. Kokkutõmbamist ei toetata.
- **Failisüsteem**: Rediacc kasutab sisemiselt BTRFS-i kirjutamisel kopeerivate hetktõmmiste ja tõhusa hargnemise jaoks. Nõuab masinat, mis käitab **Linuxi tuumaga 6.1 või uuemaga** täieliku tootmisstabilisuse jaoks.

Igal hoidla pildil on fikseeritud maksimaalne suurus, mis on seatud loomise ajal (vaikimisi: 10 GB). Kasutage `rdc repo resize` üksiku hoidla laiendamiseks. Kõikide hoidla maksimaalade summa ei tohi ületada andmehoidla basseini suurust.

---

## HTTP-marsruudid

Iga teenus sildiga `rediacc.service_port` saab automaatselt ühe HTTPS-marsruudi. Marsruutidega teenuste arvule piirangut ei ole, alludes hoidla kohta 61-teenuse maksimumile.

Metamärgi TLS-sertifikaadid väljastatakse hoidla kohta esimesel juurutusel Let's Encrypt kaudu (Cloudflare DNS-01 väljakutse). Let's Encrypt piirab väljastamist **50 sertifikaadiga registreeritud domeeni kohta nädalas**. Kuna Rediacc kasutab ühte metamärgi sertifikaati hoidla kohta (mitte teenuse kohta), tabab 50+ uut hoidlat ühe nädala jooksul loov juurutus selle lae.

Hargnemised kasutavad uuesti vanema hoidla olemasolevat metamärgi sertifikaati ega tarbi sertifikaadi kvooti.

---

## Kontrollpunkt/taastamine (CRIU)

Live-migratsiooni CRIU kaudu on järgmised piirangud:

- **Valikuline**: ainult konteinereid sildiga `rediacc.checkpoint=true` kontrollpunktitakse. Andmebaasid ja olekuta teenused on vaikimisi välistatud ja käivituvad taastamisel värskelt.
- **Tuuma nõue**: Linux 6.1+ nii lähte- kui sihtmasinal.
- **Võrgurežiim**: CRIU nõuab hosti võrgurežiimi. Kohandatud võrgukonfiguratsioonidega konteinereid ei saa kontrollpunktida.
- **Mälu**: kontrollpunkti andmete suurus võrdub kontrollpunktitud protsessi residendimäluga. Suured mälus olevad andmekogumid (nt Node.js rakendus, mis vahemälustab 4 GB andmeid) toodavad 4 GB kontrollpunktifailid.
- **TCP-ühendused**: rakendused peavad taluma ühenduse katkemist taastamisel. Aktiivseid TCP-ühendusi **ei** säilitata. Taastatud protsess näeb sokette suletuna ja peab uuesti ühenduma. See kehtib nii sama masina kui ka masinate vaheliste taastamisteede kohta.
- **Sama masina live-hargnemine ei ole toetatud**: `rdc repo fork --parent X --tag Y --checkpoint` õnnestub kontrollpunkti jäädvustamisel, kuid sellele järgnev `rdc repo up` samal masinal nurjub `criu failed: type RESTORE errno 0` veaga, kui vanem on endiselt töötamas. Selle põhjustavad ülesvoolu CRIU vead [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) ja [checkpoint-restore/criu#514](https://github.com/checkpoint-restore/criu/issues/514), mis interakteeruvad `network_mode: host` valikuga. Sama masina protsessioleku kohapealseks säilitamiseks kasutage `rdc repo down --checkpoint` + `rdc repo up`. Live-migratsiooniks kasutage `rdc repo push --checkpoint` erinevale masinale.

---

## Varukoopiad

| Piirang | Väärtus |
|-------|-------|
| Varukoopia sihtkohti hoidla kohta | Piiramatu |
| Samaaegseid varukoopia töid | 1 hoidla kohta (tööd järjekorda, kui käivitatud samaaegselt) |
| Varukoopia sagedus | Minimaalset intervalli ei jõustata; piiratud teie salvestuse ribalaiusega. Kasutage `rdc config backup-strategy set --name <name> --bwlimit "6M"` üleslaadimiskiiruse piiramiseks (rclone `--bwlimit` süntaks: lihtne `6M`, suunaline `6M:off` või ajakava `08:00,3M;22:00,10M`) |
| Säilitamine | Kontrollib teie salvestusteenuse pakkuja (S3, Cloudflare R2 jne). Rediacc ei jõusta säilitamispoliitikat. |
| Masinate vaheline varukoopia | Toetatud; sihtmasinal peab olema piisavalt andmehoidla ruumi |

---

## CLI ja API

| Piirang | Väärtus |
|-------|-------|
| Samaaegseid `rdc` käske sama masina vastu | Piiramatu (iga käsk avab oma SSH-ühenduse) |
| Vaikimisi paralleelne hoidla käivitamise samaaegsus | 3 (reguleeritav `--concurrency` abil) |
| SSH-ühenduse aegumine | 30 sekundit esialgse ühenduse jaoks |
| `rdc` seansi kestus | Aegumine puudub; pikaajalised toimingud hoiavad ühenduse elus |

---

## Toetatud OS-versioonid

Kaugmasinad peavad käitama üht järgmistest, et vastata Rediacc tuuma-, failisüsteemi- ja võrgueralduse nõuetele. See loetelu on autoriteetne CI-testitud komplekt (Bridge Workers maatriks) ja peab olema sünkroonis [Nõuetega](/en/docs/requirements):

| OS | Minimaalne versioon | Vaikimisi tuum | Märkused |
|----|-----------------|----------------|-------|
| Ubuntu | 24.04 LTS *(soovitatav)* | 6.8 | AppArmor vaikimisi. |
| Debian | 13 (Trixie); 12 Bookworm töötab samuti | 6.12 (6.1 Debian 12-l) | |
| Fedora | 43 | 6.12 | SELinux jõustamine vaikimisi. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor vaikimisi. |
| Oracle Linux | 10 (UEK) | UEK 7+ | UEK säilitab btrfs; SELinux jõustamine vaikimisi. |

**Minimaalne nõutav tuum: 6.1.** Masinad, mis käitavad vanemaid tuumasid, lükatakse seadistamisel selge veateate kaudu tagasi.

> **Miks tuum 6.1?** Rediacc kasutab BTRFS-i krüpteeritud hoidlasalvestuse ja kirjutamisel kopeeriva hargnemise jaoks. Linux 6.1 tõi kriitilised BTRFS-i parandused, mis vähendavad oluliselt suurte andmehoidlate ühendamisaegu, parandavad hetktõmmise kustutamise jõudlust ja parandavad varasemates tuumades esinevaid andmetervikluse probleeme. Tuuma 6.1 on samuti vajalik tuumataseme võrgueralduse haakide jaoks, mis jõustavad hoidlatevahelise eralduse, kirjutavad läbipaistvalt ümber `bind()` kutseid ja blokeerivad hoidlatevahelisi ühendusi.

> **Miks mitte Rocky Linux 10 / RHEL 10 standardtuum?** RHEL 10 standardtuum tarnib ilma `btrfs` moodulita (`modprobe btrfs` nurjub veaga "Module btrfs not found"). Rediacc krüpteeritud salvestuse taustsüsteem ei saa ilma btrfs-ita töötada. **Oracle Linux 10 on ainus RHEL-ühilduv sihtmärk toetatud loetlus**, kuna see on vaikimisi Unbreakable Enterprise Kernel (UEK), mis säilitab btrfs. Vt [Nõuded -- Miks UEK?](/en/docs/requirements) täielikuks selgituseks.

### Tuumafunktsioonide maatriks

Loe maatriksit ühekordse pilguna sellele, mida iga CI-testitud OS pakub kastist välja. Kõik viis vastavad kõikidele nõuetele, seega on see operaatorile suunatud viide, mitte väravakriteerium.

| OS | btrfs moodul | cgroups v2 | Landlock (ABI >= 1) | eBPF cgroup haagid |
|----|--------------|------------|--------------------|-------------------|
| Ubuntu 24.04 | sees-puu | ühtne hierarhia | jah (5.13+) | jah |
| Debian 13 | sees-puu | ühtne hierarhia | jah | jah |
| Fedora 43 | sees-puu | ühtne hierarhia | jah | jah |
| openSUSE Leap 16.0 | sees-puu | ühtne hierarhia | jah | jah |
| Oracle Linux 10 (UEK) | sees-puu (UEK kaudu) | ühtne hierarhia | jah | jah |
