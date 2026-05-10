---
title: Konfiguratsioonisalv
description: Null-teadmisega krüpteeritud konfiguratsioonisünkroonimine passkeyl-põhise krüpteerimisega
category: Guides
order: 8
language: et
sourceHash: "d20655e3e306b85b"
---

# Konfiguratsioonisalv

Konfiguratsioonisalv pakub sinu CLI konfiguratsiooni null-teadmisega krüpteeritud sünkroonimist seadmete vahel. Sinu konfiguratsioonid krüpteeritakse sinu passkey'st tuletatud võtmetega, server ei näe kunagi lihtteksti andmeid.

## Eeltingimused

- **Kahefaktoriline autentimine** on kontol lubatud
- **Passkey-pakkuja PRF-toega**: FIDO2 turvavõti (nt YubiKey), iCloud Keychain, Google Password Manager, 1Password või Dashlane
- **Brauser**: Chrome 133+, Edge 133+, Firefox 130+ või Safari 17+

## Seadistamine

1. Naviseeri külgribal **Konfiguratsioonisalv** ja klõpsa **Seadista konfiguratsioonisalv**
2. Nõuete kontrollnimekiri kontrollib brauserit, 2FA-d ja seansi olekut
3. Klõpsa **Alusta seadistamist**, pead puudutama oma turvavõtit kaks korda:
   - Esimene puudutus: registreerib passkey'i
   - Teine puudutus: tuletab krüpteerimisvõtmed PRF kaudu
4. Seadistamine lõpetatud, sinu passkey saladus salvestatakse sinu OS-i võtmehoidlasse

Pärast seadistamist toimivad igapäevased CLI toimingud (push/pull) ilma passkey'ta.

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

## Liikmete haldamine

Konfiguratsioonisalv on organisatsioonipõhine. Liikmeid hallatakse veebiportaali kaudu:

- **Liikmete vaatamine**: Konfiguratsioonisalv → Liikmed
- **Liikme lisamine**: Praegu ainult CLI kaudu (veebi UI planeeritud)
- **Liikme eemaldamine**: Klõpsa eemaldamise nuppu Liikmete lehel (nõuab 2FA + uuesti autentimist)

Turvamehhanismid takistavad viimase aktiivse liikme eemaldamist või enda eemaldamist.

## Turvalisus

- **Null-teadmine**: Server salvestab kolmekordselt krüpteeritud andmeid, mida ta ei suuda dekrüpteerida
- **Jagatud võti**: Dekrüpteerimiseks on vaja nii sinu passkey saladust (kliendi poolel) kui ka serveri saladust (serveri poolel)
- **Pöörlevad tokenid**: Iga API-kutse kasutab värsket tokenit; vanad tokenid hävivad ise
- **IP-sidumine**: Tokenid seotakse sinu IP-aadressiga esimesel kasutamisel
- **Kohene tühistamine**: Eemaldatud liikmed kaotavad juurdepääsu 30 sekundi jooksul

## Tõrkeotsing

| Viga | Põhjus | Lahendus |
|-------|-------|-----|
| PRF pole toetatud | Autentikaatoril puudub PRF-laiendus | Kasuta YubiKey, iCloud Keychain, 1Password või Dashlane |
| X25519 pole toetatud | Brauseri versioon on liiga vana | Uuenda Chrome 133+, Edge 133+, Firefox 130+ või Safari 17+ |
| Juba konfigureeritud | Salv on sinu organisatsiooni jaoks olemas | Külasta /account/config-storage haldamiseks |
| Konfiguratsioonisalv pole seadistatud | Serveril puudub blob-salvestus | Võta ühendust administraatoriga R2/RustFS seadistamiseks |
| Token aegunud | Tegevust pole olnud 24 tundi | Käivita mis tahes konfiguratsioonisalve käsk värskendamiseks |
| Viimast liiget ei saa eemaldada | Salv lukustaks end jäädavalt | Lisa esmalt teine liige |
