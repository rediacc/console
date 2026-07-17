---
title: Konfiguratsioonisalv
description: Null-teadmisega krüpteeritud konfiguratsioonisünkroonimine passkey, peaparooli ja taastekoodiga avamisega
category: Guides
order: 8
language: et
sourceHash: "73c75b1f00630553"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Konfiguratsioonisalv

Konfiguratsioonisalv pakub sinu CLI konfiguratsiooni null-teadmisega krüpteeritud sünkroonimist seadmete vahel. Sinu konfiguratsioonid krüpteeritakse kliendipoolselt sisukrüpteerimisvõtmega (CEK), server ei näe kunagi lihtteksti andmeid.

## Avamismeetodid (võtmepesad)

Igal salvel on üks CEK, mis on iga avamismeetodi jaoks eraldi mähitud — sarnaselt LUKS-i võtmepesadele. Iga üksik pesa avab sama võtme ning pesasid saab lisada või eemaldada ilma andmeid uuesti krüpteerimata:

| Meetod | Mis see on | Märkused |
|--------|-----------|-------|
| **Passkey** | WebAuthn passkey PRF-laiendusega | Kõige tugevam valik; riistvarapõhine |
| **Peaparool** | Sinu valitud parool, venitatud PBKDF2-SHA256-ga (600 000 iteratsiooni) | Toimib ka ilma PRF-toega riistvarata; võimaldab ka pealdiseta CLI registreerimist |
| **Taastekood** | Genereeritud `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` kood | Näidatakse täpselt üks kord loomisel; hoia see turvalises kohas |

Iga meetod läbib sama protsessi: pesa annab saladuse, mis kombineeritakse serveripoolse saladusega CEK-i lahtimähkimiseks. Kummastki poolest üksi ei piisa, seega kehtib null-teadmise põhimõte kõigi kolme meetodi puhul — pesa saladus ei jõua kunagi serverisse.

Pesasid hallatakse portaalis Konfiguratsioonisalve lehel. Organisatsioonid, kes soovivad ainult riistvarapõhist avamist, saavad lubada **nõua passkey** poliitika, mis keeldub mitte-passkey pesadest ja tühistab need kogu salve jaoks.

Avamine on seadmepõhine: sa avad salve uuel seadmel üks kord ja pärast seda toimivad igapäevased CLI toimingud (push/pull) ilma passkey'i puudutamata või parooli sisestamata.

## Eeltingimused

- **Kahefaktoriline autentimine** on kontol lubatud
- **Passkey** meetodi jaoks: PRF-toega passkey-pakkuja, näiteks FIDO2 turvavõti (nt YubiKey), iCloud Keychain, Google Password Manager, 1Password või Dashlane
- **Brauser**: Chrome 133+, Edge 133+, Firefox 130+ või Safari 17+

PRF-nõue kehtib ainult passkey-pesa kohta. Peaparooli ja taastekoodi meetodid toimivad igas toetatud brauseris.

## Seadistamine

1. Naviseeri külgribal **Konfiguratsioonisalv** ja klõpsa **Seadista konfiguratsioonisalv**
2. Nõuete kontrollnimekiri kontrollib brauserit, 2FA-d ja seansi olekut
3. Klõpsa **Alusta seadistamist**. Passkey-pesa jaoks pead puudutama oma turvavõtit kaks korda:
   - Esimene puudutus: registreerib passkey'i
   - Teine puudutus: tuletab krüpteerimisvõtmed PRF kaudu
4. Seadistamine lõpetatud, sinu passkey saladus salvestatakse sinu OS-i võtmehoidlasse

Pärast seadistamist lisa Konfiguratsioonisalve lehelt peaparooli või taastekoodi pesa, et kadunud või PRF-i mittetoetav autentimisseade ei jätaks sind salvest välja.

## PRF-pakkuja ühilduvus

| Pakkuja | PRF tugi | Platvormid |
|----------|:-----------:|-----------|
| YubiKey / FIDO2 turvavõtmed | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Platvormideülene |
| Bitwarden laiendus | ❌ | Arenduses |
| Windows Hello | ❌ | Pole toetatud |

## Pealdiseta CLI registreerimine

Brauserita masin (server, CI-käitaja, käitaja teenus) saab liituda olemasoleva salvega peaparooli meetodi abil:

```bash
rdc config remote enable --password
```

Nõuded:

- **Peaparooli pesa** on portaali kaudu juba loodud (brauser hoiab võtit loomise ajal, seega see samm ise ei saa olla pealdiseta)
- **API-token `config:enroll` õigusega** kutse autentimiseks

Registreerimine on lugemistoiming: CLI toob pesa avalikud KDF-parameetrid ja mähitud võtme, tuletab parooli saladuse lokaalselt ning mähib CEK-i seadmes lahti. See annab seadmele õiguse konfiguratsiooni dekrüpteerida ja sünkroonida; see ei muuda salve.

## Võtme pööramine

Salve CEK-i pööramine mähib selle uude põlvkonda:

- **Taastekoodid muutuvad pööramisel alati kehtetuks** — genereeri ja salvesta pärast seda uus
- **Peaparooli pesa** säilib ainult siis, kui parool sisestatakse pööramisviisardis uuesti
- Vana põlvkonda jäänud pesa märgitakse aegunuks, mitte ei ebaõnnestu arusaamatu dekrüpteerimisveaga

## Liikmete haldamine

Konfiguratsioonisalv on organisatsioonipõhine. Liikmeid hallatakse veebiportaali kaudu:

- **Liikmete vaatamine**: Konfiguratsioonisalv → Liikmed
- **Liikme lisamine**: Praegu ainult CLI kaudu (veebi UI planeeritud)
- **Liikme eemaldamine**: Klõpsa eemaldamise nuppu Liikmete lehel (nõuab 2FA + uuesti autentimist)

Turvamehhanismid takistavad viimase aktiivse liikme eemaldamist või enda eemaldamist.

## Turvalisus

- **Null-teadmine**: Server salvestab kolmekordselt krüpteeritud andmeid, mida ta ei suuda dekrüpteerida
- **Jagatud võti**: Dekrüpteerimiseks on vaja nii sinu pesa saladust (kliendi poolel) kui ka serveri saladust (serveri poolel)
- **Pöörlevad tokenid**: Iga API-kutse kasutab värsket tokenit; vanad tokenid hävivad ise
- **IP-sidumine**: Tokenid seotakse sinu IP-aadressiga esimesel kasutamisel
- **Kohene tühistamine**: Eemaldatud liikmed kaotavad juurdepääsu 30 sekundi jooksul

## Tõrkeotsing

| Viga | Põhjus | Lahendus |
|-------|-------|-----|
| PRF pole toetatud | Autentikaatoril puudub PRF-laiendus | Kasuta YubiKey, iCloud Keychain, 1Password või Dashlane, või lisa peaparooli pesa |
| X25519 pole toetatud | Brauseri versioon on liiga vana | Uuenda Chrome 133+, Edge 133+, Firefox 130+ või Safari 17+ |
| Juba konfigureeritud | Salv on sinu organisatsiooni jaoks olemas | Külasta /account/config-storage haldamiseks |
| Konfiguratsioonisalv pole seadistatud | Serveril puudub blob-salvestus | Võta ühendust administraatoriga R2/RustFS seadistamiseks |
| Token aegunud | Tegevust pole olnud 24 tundi | Käivita mis tahes konfiguratsioonisalve käsk värskendamiseks |
| Viimast liiget ei saa eemaldada | Salv lukustaks end jäädavalt | Lisa esmalt teine liige |
| Aegunud pesa | Pesa pärineb enne viimast võtme pööramist | Lisa pesa uuesti (taastekoodid tuleb pärast iga pööramist uuesti genereerida) |

## Seotud

- [Veebikonsool](/et/docs/web-console), salve avamine brauseris käskude käivitamiseks
- [Proxy ja käitaja](/et/docs/proxy-and-executor), kuidas avatud võti käitajale antakse
