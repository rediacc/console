---
title: Turvamudel
description: Kes mida konfiguratsioonisalves näha saab, kuidas võtmete ulatus piiritletakse, milleni agendid ja kaug-MCP jõuavad ning mida saab taastada.
category: Guides
tags:
  - security
  - account
subcategory: account
order: 14
language: et
sourceHash: "dd01eccb85dd4e7c"
sourceCommit: "467795d4f62f378389037e0027cac2676125b437"
---

# Turvamudel

See leht selgitab, mida konfiguratsioonisalv kaitseb, milline võti mida avab ja milleni jõuab iga kutsuja tüüp. Seadistamise sammud leiad lehelt [Konfiguratsioonisalv](/et/docs/config-storage), seansid ja tokenid lehelt [Konto turvalisus ja API](/et/docs/account-security).

## Kes mida näha saab

![Võtmete hierarhia](/img/security-key-hierarchy.svg)

*Server hoiab SDK-kihi ja organisatsiooni paroolifraasi kihi võtmeid; CEK-i avavad ainult võtmepesade hoidjad.*

![Kes näeb seadistuse sisu](/img/security-who-can-see.svg)

*Mida iga ründaja tüüp lugeda saab.*

Salvestatud konfiguratsioon on krüpteeritud kolmes kihis. SDK kihti ja organisatsiooni paroolifraasi kihti haldab server. Keskmine kiht on sisu krüpteerimisvõti (CEK), mille saavad lahti võtta vaid võtmepesa hoidjad: seadmes hoitav pesasaladus ühendatakse serveri hoitava saladusega ning kumbki pool üksi seda ei ava.

| Ründajal on | Näeb konfiguratsiooni sisu | Põhjus |
|---|---|---|
| Ainult andmebaasi koopia | Ei | Konfiguratsiooni blobid asuvad objektisalves, mitte andmebaasis |
| Andmebaas ja objektisalv | Ei | Organisatsiooni paroolifraasi kiht vajab Workeri saladust ja CEK kiht pesasaladust |
| Serveri täielik kompromiteerimine | Mitte ilma pesasaladuseta | Serverikihid kukuvad, kuid CEK jääb passkey PRF-väljundi või 160-bitise taastekomplekti taha ning ühtegi neist ei saa ära arvata |
| Eemaldatud liikme seade | Seda, mis on juba alla tõmmatud | Hilisemad versioonid jäävad pärast CEK pööramist suletuks |
| Lekkinud agendi URL | Üks konfiguratsioon, selle kasutajana | Vaata [Agendid ja kaug-MCP](#agents-and-remote-mcp) |

Server näeb siiski metaandmeid (konfiguratsioonide id-d, tiimid, versioonid, ajatemplid, blobi suurused) ning võib päringuid tagasi lükata, viivitada või kustutada. Operaator, kes serveerib pahatahtlikku portaalikoodi, saab võtmeid brauseris lugeda. Iga blob on seotud oma salve, konfiguratsiooni, tiimi ja versiooniga, nii et server ei saa ühtegi neist märkamatult vahetada ega muuta, ning CLI lükkab tagasi versiooni, mis on vanem kui juba nähtud versioon.

## Võtmete ulatus

![Võtmete ulatus](/img/security-key-scope.svg)

*Üks hoidla ja üks CEK organisatsiooni kohta; tiimid on juurdepääsukontroll, mitte eraldi võtmed.*

- Üks konfiguratsioonisalv organisatsiooni kohta ja üks CEK salve kohta. Tiimid on serveripoolne juurdepääsukontroll, mitte krüptograafiline isolatsioon: taastekomplekt või võtmepesa avab kogu organisatsiooni CEK.
- Võtmepesad on salve, kasutaja ja meetodi kohta unikaalsed, seega on taastekomplekt üks kasutaja ja organisatsiooni kohta. Kahe organisatsiooni kasutajal on kaks komplekti ning tiimikomplekti ei ole.
- Masinasaladus on üks masina ja organisatsiooni kohta ning registreerib pealdiseta masina.
- Igal konfiguratsioonil on CEK all oma sisuvõti. Agendi volitus kannab ühe konfiguratsiooni sisuvõtit, seega ei avane sellega ükski teine organisatsiooni konfiguratsioon.
- Iga konfiguratsiooni autoriseerimispoliitika on eraldi kirje võtme all, mis tuletatakse CEK-st ja kirje viidast. Ühe poliitikavõtme hoidja avab ainult selle viida kirjed.

## Agendid ja kaug-MCP

![Kaug-MCP voog](/img/security-remote-mcp-flow.svg)

*Kliendi päring läheb MCP Workeri kaudu organisatsiooni täitjale; aegunud luba saadab kliendi uuesti autoriseerima.*

Agendi volitus on kaug-MCP URL-i taga olev võtmehoidja tüüp. See kannab ühe konfiguratsiooni sisuvõtit ning volituse enda tiimikonfiguratsiooni ja organisatsioonitaseme konfiguratsiooni poliitikavõtmeid, mitte kunagi CEK-d, seega loeb agent täpselt seda, mida loeb tema inimene.

- **Eluiga.** URL kehtib vaikimisi 7 päeva ja kõige rohkem 30 päeva, seejärel aegub või tühistatakse. Aegunud volitus lükatakse tagasi ja klient autoriseerib uuesti.
- **Ulatus.** Volitus ulatub ühe konfiguratsioonini ja kuulub ühte regiooni (eu, us või asia). Teisele regioonile esitatud URL lükatakse tagasi õige regiooni nimetamisega ning seda ei suunata kunagi edasi. On-premise paigaldused on ühe regiooniga.
- **Poliitika.** Agent tegutseb ainult seal, kus seda lubavad nii inimese selge nõusolek kui ka poliitika lagi. Lagi on organisatsiooni poliitika, mida tiimi poliitika kitsendab. Agent ei saa poliitikat muuta, saladuste väärtusi lugeda ega oma volitust laiendada.
- **Mõjuraadius.** Lekkinud URL tegutseb selle kasutajana oma ühel konfiguratsioonil, kuni see aegub või tühistatakse. See ei ava midagi väljaspool oma regiooni majutatud käitajat.

Tööriistade väljund jõuab mudelipakkujani, kelle kasutaja ühendab ja keda Rediacc ei vali.

### On-premise

Teel pole Cloudflare'i. Pilve Workeri saladused muutuvad kliendi hostis keskkonnamuutujateks või konfiguratsiooniks, seega asendab hostile juurdepääs ülaltoodud tabeli Workeri saladuse piiri ning tööriistakutsed jooksevad kliendi enda deemonikäitajas.

## Poliitika

![Poliitika lagi](/img/security-policy-ceiling.svg)

*Agent tegutseb ainult seal, kus inimese nõusolek ning organisatsiooni ja tiimi poliitika ühisosa seda lubavad.*

Poliitika on eraldi kirje, mis on konfiguratsioonikirje kaupa pitseeritud autenditud andmetega, mis seovad salve, konfiguratsiooni, tiimi, versiooni ja võtmegeneratsiooni. Server ei saa seda lugeda ning taasesitatud või vahetatud kirje ei läbi oma terviklikkusmärgist. Versiooni 1 poliitikakirjed lükatakse tagasi.

Organisatsiooni poliitikat kirjutab ainult organisatsiooni omanik või admin ning tiimi poliitikat ainult tiimi admin (või omanik või admin). Kirjutamiseks on vaja 2FA-d ja kõrgendatud seanssi ning seotud passkey'd, kui salv nõuab passkey'sid. Poliitikat loevad kõik liikmed ja kõik neid teenindavad käitajad. Võti, mille organisatsioon lukustab, jäetakse tiimi poliitikas arvestamata.

## Mida saab taastada

![Lukustuse avamise ja taastamise teed](/img/security-unlock-recovery.svg)

*Iga avamisviis lõpeb CEK-iga ning taastekomplekt on kohustuslik.*

| Olukord | Taastamine |
|---|---|
| Passkey kadunud | Ava taastekomplektiga, seejärel registreeri uus passkey |
| Komplekt kadunud | Loo see töötava passkey'ga uuesti; vana väljatrükk lakkab töötamast |
| Mõlemad kadunud | Omanik või admin lisab liikme uuesti liikme üleandmise kaudu |
| Viimane võtmehoidja kaotab mõlemad | Taastamatu, mistõttu soovitatakse teist võtmehoidjat |
| Liige eemaldatud | Tema pesad ja tokenid kaovad kohe; CEK pööramine sulgeb hilisemad versioonid võtme eest, mille ta säilitas |
| CEK pööramine | Mähib CEK uue generatsiooni alla ümber ja muudab kõik taastekomplektid kehtetuks |

Server keeldub pesa kustutamisest, liikme eemaldamisest ja liikme lahkumisest, mis jätaks alla kahe võtmehoidja ja ilma taastepesata. Iga liige saab registreerimisel kohustusliku taastekomplekti ning selle säilitamine on liikme vastutus.
