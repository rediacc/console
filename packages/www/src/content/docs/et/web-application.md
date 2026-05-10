---
title: Veebirakendus
description: Veebirakenduse arhitektuuri ja juurutamise mõistmine Rediacc-iga
category: Reference
order: 1
language: et
---

# Rediacc platvormi kasutusjuhend

## Ülevaade

**Rediacc** on pilvplatvorm, mis pakub tehisintellektipõhiseid varundamisteenuseid.

See juhend selgitab veebiliidese põhikasutust aadressil [https://www.rediacc.com/](https://www.rediacc.com/).

### Juhendi eesmärk

- Aidata uutel kasutajatel platvormiga kiiresti kohaneda
- Selgitada põhifunktsioone (ressursihaldus, varundamine) samm-sammult

---

## 1. Konto loomine ja sisselogimine

### 1.1 Registreerimine

![Registreerimisprotsessi ülevaade](/assets/videos/user-guide/01-01-registration.webm)
*(Video: Täielik registreerimisvoog algusest lõpuni)*

Rediacc platvormi kasutamiseks tuleb esmalt luua konto.

![Rediacc sisselogimislehekülg – alati tööl olev taristu](/assets/images/user-guide/01_login.png)
*(Joonis 1: Peamine sisselogimisleht, mis näitab Rediacc platvormi põhifunktsioone)*

1. Navigeeri brauseris aadressile [https://www.rediacc.com/](https://www.rediacc.com/).
2. Klõpsa lehe paremas ülanurgas nuppu **{{t:auth.login.signIn}}**.
3. Vali **Get Started** tasuta juurdepääsuks või **Request Demo** demonstratsiooni jaoks.

> **Vihje**: Saad luua tasuta konto ilma krediitkaardita. Sisaldab piiramatu arvu meeskondi.

![Rediacc sisselogimise vorm – e-posti ja parooli väljad](/assets/images/user-guide/02_register.png)
*(Joonis 2: Olemasolevate kasutajate sisselogimisekraan)*

4. Kui sul pole kontot, klõpsa linki **{{t:auth.login.register}}**, et luua uus konto.

5. Täida avanevas vormis järgmised andmed:
   - **{{t:auth.registration.organizationName}}**: Sisesta oma organisatsiooni nimi
   - **{{t:auth.login.email}}**: Sisesta kehtiv e-posti aadress
   - **{{t:auth.login.password}}**: Loo vähemalt 8 tähemärki sisaldav parool
   - **{{t:auth.registration.passwordConfirm}}**: Sisesta sama parool uuesti

![Konto loomise modaal – registreeri, kinnita ja lõpeta sammud](/assets/images/user-guide/03_create_account.png)
*(Joonis 3: Uue kasutaja registreerimise samm-sammuline vorm – Registreeri > Kinnita > Lõpeta)*

6. Märgi ruut teenuse tingimuste ja privaatsuspoliitika aktsepteerimiseks.
7. Klõpsa nuppu **{{t:auth.registration.createAccount}}**.

> **Vihje**: Parool peab olema vähemalt 8 tähemärki pikk ja turvaline. Kõik väljad on kohustuslikud.

8. Sisesta e-postile saadetud 6-kohaline kinnituskood kastidesse järjestikku.
9. Klõpsa nuppu **{{t:auth.registration.verifyAccount}}**.

![Kinnituskoodi sisestamine – 6-kohaline aktiveerimiskood](/assets/images/user-guide/04_verification_code.png)
*(Joonis 4: Administraatorile saadetud aktiveerimiskoodi sisestamise aken)*

> **Vihje**: Kinnituskood kehtib piiratud aja. Kui koodi ei saabu, kontrolli rämpsposti kausta.

---

### 1.2 Sisselogimine

![Sisselogimisprotsessi ülevaade](/assets/videos/user-guide/01-02-login.webm)
*(Video: Täielik sisselogimisvoog)*

Pärast konto loomist saad platvormile sisse logida.

1. Täida väli **{{t:auth.login.email}}** (kohustuslik, kui ilmub punane hoiatus).
2. Täida väli **{{t:auth.login.password}}**.
3. Klõpsa nuppu **{{t:auth.login.signIn}}**.

![Sisselogimise vorm – kohustuslikud väljad koos veateadetega](/assets/images/user-guide/05_sign_in.png)
*(Joonis 5: Sisselogimise vorm – veateated on märgitud punase äärisega)*

> **Vihje**: Kui veateade ütleb "See väli on kohustuslik", täida tühjad väljad. Unustatud paroolide korral võta ühendust administraatoriga.

4. Pärast edukat sisselogimist suunatakse sind ekraanile **{{t:common.navigation.dashboard}}**.

![Rediacc juhtpaneel – masinate loend ja külgriba menüü](/assets/images/user-guide/06_dashboard.png)
*(Joonis 6: Põhiline juhtpaneel pärast edukat sisselogimist – Organisatsioon, Masinad ja Seaded menüüd vasakpoolses külgribal)*

> **Vihje**: Juhtpaneel värskendub automaatselt. Värskeima info saamiseks saad lehte F5-ga uuendada.

---

## 2. Liidese ülevaade

Pärast sisselogimist koosneb nähtav ekraan järgmistest põhiosadest:

- **{{t:common.navigation.organization}}**: Kasutajad, meeskonnad ja juurdepääsukontroll
- **{{t:common.navigation.machines}}**: Serveri ja hoidla haldus
- **{{t:common.navigation.settings}}**: Profiili ja süsteemi seaded
- **{{t:common.navigation.storage}}**: Salvestusala haldus
- **{{t:common.navigation.credentials}}**: Juurdepääsu mandaadid
- **{{t:common.navigation.queue}}**: Tööjärjekorra haldus
- **{{t:common.navigation.audit}}**: Süsteemi auditi logid

---

## 2.1 Organisatsioon – kasutajad

Kasutajahaldus võimaldab kontrollida platvormi juurdepääsu oma organisatsiooni inimestele.

### 2.1.1 Kasutajate lisamine

![Kasutajate lisamise ülevaade](/assets/videos/user-guide/02-01-01-user-create.webm)
*(Video: Uue kasutaja loomine)*

1. Klõpsa vasakul külgribal valikul **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**.
2. Vaata kõigi kasutajate loendit tabelikujul.
3. Iga kasutaja real kuvatakse e-post, staatus ({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), õiguste rühm ja viimase tegevuse aeg.

![Kasutajate haldusleht – aktiivsete kasutajate loend](/assets/images/user-guide/07_users.png)
*(Joonis 7: Organisatsiooni kasutajate jaotis – kõigi kasutajate teave on kuvatud)*

4. Klõpsa paremas ülanurgas ikooni **"+"**.
5. Klõpsa nuppu **{{t:organization.users.modals.createTitle}}** ja täida avanevas vormis:
   - **{{t:organization.users.form.emailLabel}}**: Sisesta kasutaja e-posti aadress
   - **{{t:organization.users.form.passwordLabel}}**: Sisesta ajutine parool

![Kasutaja loomise modaal – e-posti ja parooli väljad](/assets/images/user-guide/08_user_add.png)
*(Joonis 8: Uue kasutaja lisamise modaalaken – lihtne ja kiire kasutaja loomise vorm)*

6. Klõpsa nuppu **{{t:common.actions.create}}**.

> **Vihje**: Sisselogimisandmed tuleks loodud kasutajale turvaliselt edastada. Soovitame esimesel sisselogimisel parool vahetada.

![Kasutajate loend – täielik tabelivaade kolme kasutajaga](/assets/images/user-guide/09_user_list.png)
*(Joonis 9: Kõik aktiivsed ja passiivsed kasutajad kasutajate haldusleheküljel)*

> **Vihje**: Lehekülg näitab automaatselt 20 kirjet. Rohkemate kirjete vaatamiseks kasuta leheküljenumbrit.

### 2.1.2 Kasutajaõiguste määramine

![Kasutajaõiguste ülevaade](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(Video: Õiguste rühmade määramine kasutajatele)*

Saad hallata juurdepääsuõigusi, määrates kasutajatele konkreetsed õiguste rühmad.

1. Vali kasutaja vahekaardilt **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**.
2. Klõpsa toimingute veerus kilbi ikooni (**{{t:organization.access.tabs.permissions}}**).

![Õiguste haldus – kilbi, hammasratta ja kustutamise ikoonid](/assets/images/user-guide/10_users_permissions.png)
*(Joonis 10: Kasutajatoimingute ikoonide kuvamine – iga ikoon tähistab erinevat toimingut)*

3. Vali avanevas vormis **{{t:organization.users.modals.permissionGroupLabel}}**.
4. Rühma kasutajate ja õiguste arv kuvatakse kasutaja kõrval.
5. Klõpsa nuppu **{{t:organization.users.modals.assignTitle}}**, et muudatused salvestada.

![Õiguste määramise modaal – administraatorite rühm](/assets/images/user-guide/11_user_permissions_form.png)
*(Joonis 11: Valitud kasutajale õiguste rühma määramise modaal – rippmenüü saadaolevate rühmadega)*

> **Vihje**: Mõned õiguste rühmad on süsteemi poolt fikseeritud ja neid ei saa muuta.

### 2.1.3 Kasutaja aktiveerimine

![Kasutaja aktiveerimise ülevaade](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(Video: Passiivse kasutaja aktiveerimine)*

Saad keelatud kasutajaid uuesti aktiveerida.

1. Leia **Kasutajate** loendist passiivse staatusega kasutaja.
2. Klõpsa toimingute veerus punast ikooni.

![Kasutaja aktiveerimine – "Aktiveeri" tööriistavihjega vaade](/assets/images/user-guide/12_users_activation.png)
*(Joonis 12: Passiivse kasutaja aktiveerimine)*

3. Klõpsa kinnitusdialoogi nuppu **{{t:common.general.yes}}**.

![Aktiveerimise kinnituse modaal](/assets/images/user-guide/13_users_activation_confirm.png)
*(Joonis 13: Kasutaja aktiveerimise kinnitamise modaalaken)*

> **Vihje**: See toiming on pöörduv. Kasutaja saab samal viisil deaktiveerida.

### 2.1.4 Kasutaja jälg

![Kasutaja jälje ülevaade](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(Video: Kasutaja tegevusjälje vaatamine)*

Kasutajate tegevuse jälgimiseks saad kasutada jälje funktsiooni.

1. Vali kasutaja ja klõpsa toimingute veerus hammasratta ikooni.
2. Klõpsa valikul **{{t:common.actions.trace}}**, et avada kasutaja tegevuslugu.

![Kasutaja jälg – "Jälg" tööriistavihjega ja toiminguinupuga](/assets/images/user-guide/14_users_trace.png)
*(Joonis 14: Kasutaja tegevusjälje valik)*

3. Kasutaja varasemad tegevused on kuvatud avatud ekraanil.
4. Ülaosas kuvatakse statistika: kokku kirjeid, vaadatud kirjeid, viimane tegevus.
5. Klõpsa nuppu **{{t:common.actions.export}}** ja vali vorming: **{{t:common.exportCSV}}** või **{{t:common.exportJSON}}**.

![Auditi ajalugu – ekspordi valikud](/assets/images/user-guide/15_user_trace_export.png)
*(Joonis 15: Kasutaja täielik tegevuslugu – statistika, üksikasjad ja ekspordi valikud)*

> **Vihje**: Ekspordi auditi andmeid regulaarselt, et säilitada turvalisus- ja vastavusrekordeid. CSV-vormingut saab avada Excelis.

---

## 2.2 Organisatsioon – meeskonnad

Meeskonnad võimaldavad kasutajaid rühmitada ja anda ressurssidele hulgijuurdepääsu.

### 2.2.1 Meeskondade loomine

![Meeskondade loomise ülevaade](/assets/videos/user-guide/02-02-01-team-create.webm)
*(Video: Uue meeskonna loomine)*

1. Mine vahekaardile **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}**.
2. Klõpsa nuppu **"+"**.
3. Sisesta oma meeskonna nimi väljale **{{t:common.vaultEditor.fields.TEAM.name.label}}**.
4. Täida jaotises **{{t:common.vaultEditor.vaultConfiguration}}** väljad **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** ja **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}**.

![Uue meeskonna loomise vorm – meeskonna nimi ja SSH-võtmed](/assets/images/user-guide/16_teams_create.png)
*(Joonis 16: Uue meeskonna loomine "Private Team" all)*

5. Klõpsa meeskonna salvestamiseks nuppu **{{t:common.actions.create}}**.

> **Vihje**: SSH-võtmed on vajalikud Bridge SSH autentimiseks. Kui saad puuduva võtme hoiatuse, esita mõlemad võtmed.

### 2.2.2 Meeskonna muutmine

![Meeskonna muutmise ülevaade](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(Video: Meeskonna teabe muutmine)*

1. Klõpsa meeskondade loendis muuta soovitava meeskonna kõrval pliiatsiikonil.
2. Muuda vajadusel meeskonna nime väljal **{{t:common.vaultEditor.fields.TEAM.name.label}}**.
3. Uuenda SSH-võtmeid jaotises **{{t:common.vaultEditor.vaultConfiguration}}**.
4. Klõpsa muudatuste rakendamiseks nuppu **{{t:common.save}}**.

![Meeskonna muutmise vorm – sinine infoteade](/assets/images/user-guide/17_teams_edit_form.png)
*(Joonis 17: Olemasoleva meeskonna teabe muutmine)*

> **Vihje**: Meeskonna konfiguratsioon on kasutusel organisatsioonistruktuuri jaoks. Muudatused jõustuvad kõigi meeskonnaliikmete jaoks.

### 2.2.3 Meeskonnaliikmete haldus

![Meeskonnaliikmete halduse ülevaade](/assets/videos/user-guide/02-02-03-team-members.webm)
*(Video: Meeskonnaliikmete haldamine)*

1. Vali meeskond ja klõpsa kasutajaikoonil.
2. Vaata juba meeskonda määratud liikmeid vahekaardil **{{t:organization.teams.manageMembers.currentTab}}**.
3. Lülitu vahekaardile **{{t:organization.teams.manageMembers.addTab}}**.
4. Sisesta e-posti aadress või vali kasutaja rippmenüüst.
5. Klõpsa nuppu **"+"**, et liige meeskonda lisada.

![Meeskonnaliikmete halduse vorm – vahekaardid "Praegused liikmed" ja "Lisa liige"](/assets/images/user-guide/18_teams_members_form.png)
*(Joonis 18: Meeskonnaliikmete halduspaneel)*

> **Vihje**: Sama liiget saab määrata mitmesse meeskonda.

### 2.2.4 Meeskonna jälg

![Meeskonna jälje ülevaade](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(Video: Meeskonna auditi ajaloo vaatamine)*

1. Vali jälgitav meeskond.
2. Klõpsa kella/ajaloo ikooni.
3. Vaata modaalis **{{t:resources.audit.title}}** kokku kirjeid, vaadatud kirjeid ja viimase tegevuse arve.
4. Klõpsa nuppu **{{t:common.actions.export}}**, et eksportida {{t:common.exportCSV}} või {{t:common.exportJSON}} vormingus.

![Auditi ajaloo modaal – DataBassTeam meeskond](/assets/images/user-guide/19_teams_trace.png)
*(Joonis 19: Meeskonna auditi ajaloo vaatamine)*

> **Vihje**: Auditi ajalugu on oluline vastavuse ja turvakontrolli jaoks.

### 2.2.5 Meeskonna kustutamine

![Meeskonna kustutamise ülevaade](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(Video: Meeskonna kustutamine)*

1. Klõpsa kustutada soovitava meeskonna kõrval prügikasti (punane) ikooni.
2. Kinnita kinnitusdialoogi meeskonna nimi.
3. Klõpsa nuppu **{{t:common.general.yes}}**.

![Meeskonna kustutamise kinnituse dialoog](/assets/images/user-guide/20_teams_delete.png)
*(Joonis 20: Meeskonna kustutamise kinnitus)*

> **Hoiatus**: Meeskonna kustutamine on pöördumatu. Enne kustutamist kontrolli, kas meeskonnas on olulist andmeid.

---

## 2.3 Organisatsioon – juurdepääsukontroll

Juurdepääsukontroll võimaldab hallata kasutajaõigusi tsentraalselt, luues õiguste rühmi.

### 2.3.1 Õiguste rühmade loomine

![Õiguste rühma loomise ülevaade](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(Video: Õiguste rühma loomine)*

1. Mine vahekaardile **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}**.
2. Klõpsa nuppu **"+"**.
3. Sisesta väljale **{{t:organization.access.modals.groupPlaceholder}}** sisukas nimi.
4. Klõpsa rühma loomiseks nuppu **{{t:common.actions.confirm}}**.

![Õiguste rühma loomise vorm](/assets/images/user-guide/21_create_access.png)
*(Joonis 21: Uue õiguste rühma loomine)*

> **Vihje**: Õiguste rühmi kasutatakse sarnaste õigustega kasutajate organiseerimiseks. Hoia rühmade nimed kirjeldavad (nt "Admin", "Read Only", "Repository Manager").

### 2.3.2 Õiguste haldus

![Õiguste halduse ülevaade](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(Video: Rühma õiguste haldamine)*

1. Vali õiguste rühm ja klõpsa valikul **{{t:organization.access.modals.managePermissionsTitle}}**.
2. Vaata rühma juurdepääsuõigusi vahekaardil **{{t:organization.access.modals.currentPermissionsTab}}**.
3. Saad õiguse tühistada, klõpsates iga toimingu kõrval punast nuppu **{{t:common.delete}}**.
4. Klõpsa vahekaardile **{{t:organization.access.modals.addPermissionsTab}}**, et lisada rühmale uusi õigusi.

![Õiguste halduspaneel – määratud õiguste loend](/assets/images/user-guide/22_access_permission.png)
*(Joonis 22: Õiguste rühma õiguste haldamine)*

> **Vihje**: Anna õigused vähima õiguse printsiibi alusel. Vaata regulaarselt üle ja eemalda tarbetud õigused.

---

## 2.4 Masinad

Masinate jaotis võimaldab hallata servereid ja hoidla ressursse.

### 2.4.1 Masinate lisamine

![Masinate lisamise ülevaade](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(Video: Uue masina lisamine)*

1. Mine vasakust menüüst vahekaardile **{{t:common.navigation.machines}}**.
2. Klõpsa paremas ülanurgas nuppu **{{t:machines.createMachine}}**.

![Masinate leht – nupp "Lisa masin"](/assets/images/user-guide/23_machines_add.png)
*(Joonis 23: Masinate halduse avalehekülg)*

3. Täida avanevas vormis:
   - **{{t:machines.machineName}}**: Sisesta kordumatu nimi (nt "server-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: Sisesta masina IP-aadress (nt 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: Täpsusta salvestuskataloog (nt /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: Sisesta SSH kasutajanimi
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: Sisesta pordinumber (vaikimisi: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: Sisesta parool (valikuline)

![Masina lisamise vorm – kõik väljad](/assets/images/user-guide/24_machine_create.png)
*(Joonis 24: Uue masina lisamise vorm – masina nimi, võrguseaded, SSH mandaadid)*

4. Klõpsa ühenduse kontrollimiseks nuppu **{{t:common.vaultEditor.testConnection.button}}**.
5. Pärast edukat testi klõpsa nuppu **{{t:common.actions.create}}**.

> **Vihje**: Kui valik "Alusta seadistust automaatselt pärast masina loomist" on märgitud, teostab masin automaatselt täiendavad seadistamissammud.

![Masina loomine lõpetatud – ülesande jälgimise aken](/assets/images/user-guide/25_machine_create_complete.png)
*(Joonis 25: Ülesande jälgimise aken pärast masina edukat loomist)*

6. Jälgi etappe: **{{t:queue.trace.assigned}}** → **Processing** → **{{t:queue.statusCompleted}}**
7. Klõpsa toimingu sulgemiseks nuppu **{{t:common.actions.close}}**.

> **Vihje**: Viimase staatuse käsitsi kontrollimiseks klõpsa nuppu "{{t:common.actions.refresh}}".

### 2.4.2 Ühenduvuse test

![Ühenduvuse testi ülevaade](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(Video: Ühenduvuse testi käivitamine)*

Saad kontrollida olemasolevate masinate ühenduse olekut.

1. Klõpsa nuppu **{{t:machines.connectivityTest}}**.

![Ühenduvuse testi nupp](/assets/images/user-guide/26_connectivity_test_button.png)
*(Joonis 26: Ühenduvuse testi nupp masina toimingute tööriistaribal)*

2. Vaata testitavate masinate loendit.
3. Klõpsa nuppu **{{t:machines.runTest}}**.
4. Edukad tulemused on näidatud roheliselt, ebaõnnestumised punaselt.

![Ühenduvuse testi vorm – masinate loend](/assets/images/user-guide/27_connectivity_test_form.png)
*(Joonis 27: Ühenduvuse testi vorm – valitud masinate ping-funktsioon)*

> **Vihje**: Kui test ebaõnnestub, kontrolli masina IP-aadressi ja SSH-seadeid.

### 2.4.3 Masinate loendi värskendamine

![Masinate loendi värskendamise ülevaade](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(Video: Masinate loendi värskendamine)*

Masinate loendi uuendamiseks klõpsa nuppu **{{t:common.actions.refresh}}**.

![Värskenda nupp](/assets/images/user-guide/28_refresh.png)
*(Joonis 28: Värskenda nupp masina toimingute tööriistaribal)*

### 2.4.4 Masina üksikasjad

![Masina üksikasjade ülevaade](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(Video: Masina üksikasjade vaatamine)*

1. Vali masin, mille üksikasju soovid vaadata.
2. Klõpsa silmaikoonil (**{{t:common.viewDetails}}**).

![Kuva üksikasju nupp](/assets/images/user-guide/29_view_details_button.png)
*(Joonis 29: Silmiikoon masina toimingute veerus)*

3. Masina üksikasjade paneel avaneb paremal poolel:
   - **Hostname**: Masina nimi
   - **Uptime**: Töötamisaeg
   - **{{t:queue.trace.operatingSystem}}**: OS ja versioon
   - **{{t:queue.trace.kernelVersion}}**: Kerneli versioon
   - **CPU**: Protsessori teave
   - **System Time**: Süsteemikell

![Masina üksikasjade paneel – süsteemiteave](/assets/images/user-guide/30_machine_view_details.png)
*(Joonis 30: Masina üksikasjade paneel – hostname, tööaeg, OS, kernel, CPU teave)*

> **Vihje**: Vaata seda teavet regulaarselt, et kontrollida OS-ühilduvust ja ressursside saadavust.

### 2.4.5 Masina muutmine

![Masina muutmise ülevaade](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(Video: Masina seadete muutmine)*

1. Vali muuta soovitav masin.
2. Klõpsa pliiatsikoonil (**{{t:common.actions.edit}}**).

![Muuda nupp](/assets/images/user-guide/31_edit_button.png)
*(Joonis 31: Pliiatsikoon masina toimingute veerus)*

3. Tee vajalikud muudatused.
4. Klõpsa nuppu **{{t:common.vaultEditor.testConnection.button}}**.
5. Kui ühendus on edukas, klõpsa nuppu **{{t:common.save}}**.

![Masina muutmise vorm](/assets/images/user-guide/32_edit_form.png)
*(Joonis 32: Masina muutmise vorm – masina nimi, piirkond ja vault-konfiguratsioon)*

> **Vihje**: Käivita alati "Testi ühendust" pärast kriitiliste seadete muutmist.

### 2.4.6 Masina jälg

![Masina jälje ülevaade](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(Video: Masina auditi ajaloo vaatamine)*

1. Vali masin ja klõpsa kellaikoonil (**{{t:common.actions.trace}}**).

![Jälgi nupp](/assets/images/user-guide/33_trace_button.png)
*(Joonis 33: Kellaikoon masina toimingute veerus)*

2. Vaata toiminguid auditi ajaloo aknas:
   - **{{t:resources.audit.action}}**: Teostatud toimingu tüüp
   - **Details**: Muudetud väljad
   - **{{t:resources.audit.performedBy}}**: Toimingu sooritanud kasutaja
   - **Timestamp**: Kuupäev ja kellaaeg

![Masina auditi ajaloo aken](/assets/images/user-guide/34_trace_list.png)
*(Joonis 34: Auditi ajalugu – kõigi muudatuste loend)*

> **Vihje**: Klõpsa veerul Timestamp, et vaadata muudatusi kronoloogilises järjekorras.

### 2.4.7 Masina kustutamine

![Masina kustutamise ülevaade](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(Video: Masina kustutamine)*

1. Vali kustutada soovitav masin.
2. Klõpsa prügikastiikooni nupul (**{{t:common.delete}}**).

![Kustuta nupp](/assets/images/user-guide/35_delete_button.png)
*(Joonis 35: Prügikastiikoon masina toimingute veerus)*

3. Klõpsa kinnitusdialoogi nuppu **{{t:common.delete}}**.

![Masina kustutamise kinnituse aken](/assets/images/user-guide/36_delete_form.png)
*(Joonis 36: "Kas oled kindel, et soovid selle masina kustutada?" kinnitusaken)*

> **Hoiatus**: Masina kustutamisel eemaldatakse ka kõik sellel olevad hoidla definitsioonid. See toiming on pöördumatu.

### 2.4.8 Kaugoperatsioonid

![Kaugoperatsioonide ülevaade](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(Video: Kaugoperatsioonide käivitamine masinal)*

Saad teostada masinal erinevaid kaugoperatsioone.

1. Vali masin ja klõpsa nuppu **{{t:common.actions.remote}}**.
2. Vaata rippmenüü valikuid:
   - **{{t:machines.runAction}}**: Täida funktsioon masinal
   - **{{t:common.vaultEditor.testConnection.button}}**: Pinguta masinat

![Kaug-menüü – Käivita serveris ja Testi ühendust](/assets/images/user-guide/37_remote_button.png)
*(Joonis 37: Kaug-nupp – funktsioonide käivitamise menüü valitud masinal)*

> **Vihje**: Kasuta valikut "{{t:common.vaultEditor.testConnection.button}}", et kontrollida masina juurdepääsetavust enne funktsioonide käivitamist.

#### Seadistamine

1. Vali valik **{{t:machines.runAction}}**.
2. Leia loendist **{{t:functions.availableFunctions}}** funktsioon **Setup**.
3. Klõpsa funktsiooni nimel selle valimiseks.

![Masinate funktsioonide loend – setup-funktsioon](/assets/images/user-guide/38_server_setup.png)
*(Joonis 38: Setup-funktsioon – valmistab masina ette vajalike tööriistade ja konfiguratsioonidega)*

> **Vihje**: Uue masina seadistamisel on soovitatav esmalt käivitada "setup"-funktsioon.

#### Ühenduse kontroll (Hello)

1. Vali **{{t:machines.runAction}}** > **Hello** funktsioon.
2. Klõpsa nuppu **{{t:common.actions.addToQueue}}**.

![Hello funktsiooni valik](/assets/images/user-guide/39_remote_hello.png)
*(Joonis 39: Hello-funktsioon – lihtne testfunktsioon, tagastab hostname)*

3. Jälgi tulemusi ülesande jälgimise aknas.
4. Vaata masina väljundit jaotises **{{t:queue.trace.responseConsole}}**.

![Hello funktsioon lõpetatud](/assets/images/user-guide/40_remote_hello_complete.png)
*(Joonis 40: Hello-funktsioon edukalt lõpetatud – hostname vastus)*

> **Vihje**: Hello-funktsioon sobib ideaalselt masina ühenduse kontrollimiseks.

#### Täpsemad operatsioonid

1. Järgi teed **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}**.
2. Vaata saadaolevaid funktsioone: setup, hello, ping, ssh_test, uninstall
3. Vali vajalik funktsioon ja klõpsa nuppu **{{t:common.actions.addToQueue}}**.

![Täpsemad funktsioonid loend](/assets/images/user-guide/41_remote_advanced.png)
*(Joonis 41: Advanced valik – täpsemate funktsioonide loend)*

> **Vihje**: Enne täpsemaid funktsioone kasutamist veendu, et masina seadistamine on lõpule viidud.

#### Kiire ühenduvuse test

![Kaug-menüü – Testi ühendust](/assets/images/user-guide/42_connectivity_test.png)
*(Joonis 42: Ühenduse testimise valik kaug-menüüst)*

> **Vihje**: Kui masinal on SSH- või võrguprobleeme, saad selle testiga probleemid kiiresti tuvastada.

---

## 2.5 Hoidla loomine ja toimingud

Hoidlad on põhilised üksused, kus sinu varundamisandmeid säilitatakse.

### 2.5.1 Hoidlate loomine

![Hoidla loomise ülevaade](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(Video: Uue hoidla loomine)*

1. Vali masin vahekaardilt **{{t:common.navigation.machines}}**.
2. Klõpsa paremas ülanurgas nuppu **{{t:machines.createRepository}}**.

![Loo hoidla nupp](/assets/images/user-guide/43_create_repo_add.png)
*(Joonis 43: Masina hoidlate halduse ekraan – hoidla loomise nupp)*

3. Täida vorm:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: Sisesta hoidla nimi (nt postgresql)
   - **{{t:resources.repositories.size}}**: Sisesta hoidla suurus (nt 2GB)
   - **{{t:resources.repositories.repositoryGuid}}**: Vaata automaatselt genereeritud mandaati
   - **{{t:resources.templates.selectTemplate}}**: Vali mall (nt databases_postgresql)

![Hoidla loomise vorm](/assets/images/user-guide/44_repo_form.png)
*(Joonis 44: Hoidla loomise vorm – hoidla nimi, suurus ja malli valik)*

4. Klõpsa nuppu **{{t:common.actions.create}}**.

> **Vihje**: Mandaadi ID genereeritakse automaatselt, käsitsi muutmine ei ole soovitatav.

5. Jälgi etappe ülesande jälgimise aknas: **{{t:queue.trace.assigned}}** → **Processing** → **{{t:queue.statusCompleted}}**

![Hoidla loomine lõpetatud](/assets/images/user-guide/45_repo_complete.png)
*(Joonis 45: Hoidla loomine järjekorda lisatud – ülesande jälgimine)*

6. Klõpsa nuppu **{{t:common.actions.close}}**.

> **Vihje**: Ülesanne lõpeb tavaliselt 1-2 minuti jooksul.

![Hoidlate loend](/assets/images/user-guide/46_repo_list.png)
*(Joonis 46: Loodud hoidla ilmub loendisse)*

### 2.5.2 Hoidla hargnemine

![Hoidla hargnemise ülevaade](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(Video: Hoidla hargnemine)*

Saad luua uue hoidla olemasoleva kopeerimise teel.

1. Vali kopeeritav hoidla.
2. Klõpsa menüü **fx** (funktsioon).
3. Klõpsa valikul **fork**.

![fx menüü – fork valik](/assets/images/user-guide/47_fork_button.png)
*(Joonis 47: fx menüü paremal küljel – hoidla toimingud)*

4. Sisesta väljale **{{t:functions.functions.fork.params.tag.label}}** uus silt (nt 2025-12-06-20-37-08).
5. Klõpsa nuppu **{{t:common.actions.addToQueue}}**.

![Fork-i konfigureerimise vorm](/assets/images/user-guide/48_fork_form.png)
*(Joonis 48: Täpsusta fork-toimingus hoidlale uus silt)*

6. Oota teadet **{{t:queue.statusCompleted}}** ja klõpsa nuppu **{{t:common.actions.close}}**.

![Fork lõpetatud](/assets/images/user-guide/49_repo_completed.png)
*(Joonis 49: Fork-operatsioon edukalt lõpetatud)*

> **Vihje**: Siltide loomine vaikimisi kuupäeva-kellaaja vormingus on hea tava. Fork-operatsioon ei mõjuta algset hoidlat.

### 2.5.3 Hoidla käivitamine

![Hoidla käivitamise ülevaade](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(Video: Hoidla käivitamine)*

Hoidla aktiveerimiseks:

1. Vali hoidla ja järgi teed **fx** > **up**.

![Up-operatsioon](/assets/images/user-guide/50_repo_up.png)
*(Joonis 50: "up" valik fx menüüst – hoidla käivitamine)*

2. Oota teadet **{{t:queue.statusCompleted}}**.

![Up lõpetatud](/assets/images/user-guide/51_repo_up_complete.png)
*(Joonis 51: Hoidla käivitamine lõpetatud)*

> **Vihje**: "Up"-operatsioon käivitab hoidla määratletud Docker-teenused.

### 2.5.4 Hoidla peatamine

![Hoidla peatamise ülevaade](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(Video: Hoidla peatamine)*

Aktiivse hoidla peatamiseks:

1. Vali hoidla ja järgi teed **fx** > **down**.

![Down-operatsioon](/assets/images/user-guide/52_down_button.png)
*(Joonis 52: "down" valik fx menüüst – hoidla sulgemine)*

2. Oota teadet **{{t:queue.statusCompleted}}**.

![Down lõpetatud](/assets/images/user-guide/53_down_completed.png)
*(Joonis 53: Hoidla sulgemine lõpetatud)*

> **Vihje**: "Down"-operatsioon lülitab hoidla turvaliselt välja. Andmeid ei kaota, peatatakse ainult teenused.

### 2.5.5 Juurutamine

![Hoidla juurutamise ülevaade](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(Video: Hoidla juurutamine)*

Hoidla erinevas asukohas juurutamiseks:

1. Vali hoidla ja järgi teed **fx** > **deploy**.

![Deploy-operatsioon](/assets/images/user-guide/54_deploy_button.png)
*(Joonis 54: "deploy" valik fx menüüst)*

2. Sisesta juurutatav versioon väljale **{{t:functions.functions.fork.params.tag.label}}**.
3. Vali sihtmasinad väljal **{{t:functions.functions.backup_deploy.params.machines.label}}**.
4. Märgi valik **{{t:functions.checkboxOptions.overrideExistingFile}}** (kui kohaldatav).
5. Klõpsa nuppu **{{t:common.actions.addToQueue}}**.

![Deploy vorm](/assets/images/user-guide/55_deploy_form.png)
*(Joonis 55: Deploy-operatsiooni konfigureerimine – silt, sihtmasinad ja valikud)*

6. Oota teadet **{{t:queue.statusCompleted}}**.

![Deploy lõpetatud](/assets/images/user-guide/56_deploy_completed.png)
*(Joonis 56: Hoidla juurutamine lõpetatud)*

> **Vihje**: Pärast deploy-operatsiooni lõpetamist saad käivitada käsu "up", et hoidla sihtmasinatel käivitada.

### 2.5.6 Varundamine

![Hoidla varundamise ülevaade](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(Video: Hoidla varundamine)*

Hoidla varundamiseks:

1. Vali hoidla ja järgi teed **fx** > **backup**.

![Backup-operatsioon](/assets/images/user-guide/57_backup_button.png)
*(Joonis 57: "backup" valik fx menüüst)*

2. Täida vorm:
   - **{{t:functions.functions.fork.params.tag.label}}**: Sisesta kirjeldav nimi (nt backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}**: Vali varukoopia asukoht
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: Luba või keela valik
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: Vaata seadet üle

![Backup-vorm](/assets/images/user-guide/58_backup_form.png)
*(Joonis 58: Varundamise konfiguratsiooni vorm – siht, failinimi ja valikud)*

3. Klõpsa nuppu **{{t:common.actions.addToQueue}}**.

> **Vihje**: Kasuta varundamissildile kirjeldavat nime. Kaaluge kontrollpunkti lubamist suurte hoidlate puhul.

4. Oota teadet **{{t:queue.statusCompleted}}**.

![Varundamine lõpetatud](/assets/images/user-guide/59_backup_completed.png)
*(Joonis 59: Varundustöö edukalt lõpetatud)*

> **Vihje**: Enne lõpetatud oleku saavutamist oota kannatlikult; suured varukoopiad võivad võtta mitu minutit.

### 2.5.7 Malli rakendamine

![Malli rakendamise ülevaade](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(Video: Malli rakendamine hoidlale)*

Uue malli rakendamiseks hoidlale:

1. Vali hoidla ja järgi teed **fx** > **{{t:resources.templates.selectTemplate}}**.

![Mallide operatsioon](/assets/images/user-guide/60_templates_button.png)
*(Joonis 60: "Templates" valik fx menüüst)*

2. Filtreeri malle otsinguväljale tippides.
3. Klõpsa soovitud mallil selle valimiseks (valitud mall on esile tõstetud rasvase äärisega).
4. Klõpsa nuppu **{{t:common.actions.addToQueue}}**.

![Malli valiku vorm](/assets/images/user-guide/61_templates_form.png)
*(Joonis 61: Saadaolevate mallide otsimine ja valimine)*

> **Vihje**: Kasuta otsinguvälja mallide kiireks leidmiseks. Kasuta "{{t:common.viewDetails}}", et tutvuda malli funktsioonidega.

5. Oota teadet **{{t:queue.statusCompleted}}**.

![Mall rakendatud](/assets/images/user-guide/62_templates_completed.png)
*(Joonis 62: Malli rakendamine edukalt lõpetatud)*

### 2.5.8 Lahtiühendamine

![Hoidla lahtiühendamise ülevaade](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(Video: Hoidla lahtiühendamine)*

Hoidla lahtiühendamiseks:

1. Vali hoidla ja järgi teed **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}**.

![Unmount-operatsioon](/assets/images/user-guide/63_unmount_button.png)
*(Joonis 63: "Unmount" valik täpsemas menüüs)*

2. Oota teadet **{{t:queue.statusCompleted}}**.

![Unmount lõpetatud](/assets/images/user-guide/64_unmount_completed.png)
*(Joonis 64: Unmount-operatsioon lõpetatud)*

> **Vihje**: Enne lahtiühendamist veendu, et hoidlal ei ole aktiivseid toiminguid. Pärast lahtiühendamist muutub hoidla kättesaamatuks.

### 2.5.9 Laiendamine

![Hoidla laiendamise ülevaade](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(Video: Hoidla suuruse laiendamine)*

Hoidla suuruse suurendamiseks:

1. Vali hoidla ja järgi teed **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}**.

![Expand-operatsioon](/assets/images/user-guide/65_expand_button.png)
*(Joonis 65: "Expand" valik täpsemas menüüs)*

2. Sisesta soovitud suurus väljale **{{t:functions.functions.repository_expand.params.size.label}}**.
3. Vali paremal olevast rippmenüüst ühik (GB, TB).
4. Klõpsa nuppu **{{t:common.actions.addToQueue}}**.

![Expand-vorm](/assets/images/user-guide/66_expand_form.png)
*(Joonis 66: Uus suuruse parameeter hoidla suurendamiseks)*

> **Vihje**: Ära sisesta praegusest suurusest väiksemat väärtust. Hoidla laiendamise ajal teenus ei katkesta.

5. Oota teadet **{{t:queue.statusCompleted}}**.

![Expand lõpetatud](/assets/images/user-guide/67_expand_completed.png)
*(Joonis 67: Hoidla laiendamine lõpetatud)*

### 2.5.10 Ümbernimetamine

![Hoidla ümbernimetamise ülevaade](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(Video: Hoidla ümbernimetamine)*

Hoidla nime muutmiseks:

1. Vali hoidla ja järgi teed **fx** > **{{t:common.actions.rename}}**.

![Rename-operatsioon](/assets/images/user-guide/68_rename_button.png)
*(Joonis 68: "Rename" valik fx menüüst)*

2. Sisesta uus hoidla nimi.
3. Klõpsa nuppu **{{t:common.save}}**.

![Rename-vorm](/assets/images/user-guide/69_rename_form.png)
*(Joonis 69: Uue hoidla nime sisestamise dialoog)*

> **Vihje**: Hoidla nimed peaksid olema tähendusrikkad, peegeldades hoidla tüüpi ja eesmärki. Väldi erimärke.

### 2.5.11 Hoidla kustutamine

![Hoidla kustutamise ülevaade](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(Video: Hoidla kustutamine)*

Hoidla jäädavaks kustutamiseks:

1. Vali hoidla ja järgi teed **fx** > **{{t:resources.repositories.deleteRepository}}**.

![Kustuta hoidla operatsioon](/assets/images/user-guide/70_delete_repo_button.png)
*(Joonis 70: "Delete Repository" valik fx menüüst – punane)*

2. Klõpsa kinnitusdialoogi nuppu **{{t:common.delete}}**.

> **Hoiatus**: Hoidla kustutamine on pöördumatu. Enne kustutamist veendu, et hoidla andmed on varundatud.

### 2.5.12 Hoidla üksikasjad

![Hoidla üksikasjade ülevaade](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(Video: Hoidla üksikasjade vaatamine)*

Hoidla kohta üksikasjaliku teabe saamiseks:

1. Vali hoidla.
2. Klõpsa silmaikoonil (**{{t:common.viewDetails}}**).

![Kuva üksikasju nupp](/assets/images/user-guide/71_repo_view_button.png)
*(Joonis 71: Silmiikoon hoidla üksikasjade avamiseks)*

3. Vaata üksikasjade paneelil teavet:
   - **Hoidla nimi** ja tüüp
   - **Team**: Meeskond, kuhu kuulub
   - **Machine**: Masin, millel asub
   - **Vault Version**: Krüpteerimise versioon
   - **Repository GUID**: Kordumatu identifikaator
   - **Status**: Ühendatud/lahtiühendatud olek
   - **Image Size**: Kogusuurus
   - **Last Modified**: Viimase muutmise kuupäev

![Hoidla üksikasjade paneel](/assets/images/user-guide/72_repo_details_view.png)
*(Joonis 72: Valitud hoidla kohta igakülgne teave)*

> **Vihje**: Kogu selles paneelil kuvatav teave on viiteinformatsioon. Hoidla toiminguteks kasuta fx menüü valikuid.

---

## 2.6 Hoidlaga ühendamise toimingud

Hoidlatega saab ühendust luua erinevate meetodite abil.

### 2.6.1 Töölauarakenduse ühendus

![Töölauarakenduse ühenduse ülevaade](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(Video: Ühenduse loomine töölauarakenduse kaudu)*

1. Klõpsa hoidla real nuppu **{{t:resources.localActions.local}}**.

![Kohaliku ühenduse nupp](/assets/images/user-guide/73_repo_connection_local.png)
*(Joonis 73: "Local" nupp hoidla real – töölauarakenduse juurdepääs)*

2. Vali rippmenüüst juurdepääsu meetod:
   - **{{t:resources.localActions.openInDesktop}}**: Juurdepääs graafilise liidesega
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: Ava koodiredaktoris
   - **{{t:common.terminal.terminal}}**: Juurdepääs käsurealt
   - **{{t:resources.localActions.showCLICommands}}**: Käsurea tööriistad

![Ühenduse valikute menüü](/assets/images/user-guide/74_repo_connection.png)
*(Joonis 74: Hoidlaga ühendamise menüü – erinevad juurdepääsuteed)*

> **Vihje**: VS Code-iga töötades pakub valik "{{t:resources.localCommandBuilder.vscodeTab}}" kiiret integratsiooni.

3. Klõpsa nuppu **{{t:common.vscodeSelection.open}}**, kui brauser küsib luba.

![Töölauarakenduse avamise luba](/assets/images/user-guide/75_desktop_open_page.png)
*(Joonis 75: Brauser küsib luba töölauarakenduse avamiseks)*

> **Vihje**: Kui ei soovi töölauarakenduse avamisel iga kord luba anda, märgi valik "Always allow".

---

## 2.7 Seaded

Profiili ja süsteemi seadeid saad hallata jaotisest Seaded.

### 2.7.1 Parooli vahetus

![Parooli vahetuse ülevaade](/assets/videos/user-guide/02-07-03-password-change.webm)
*(Video: Parooli vahetamine)*

1. Mine vasakust menüüst vahekaardile **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}**.

![Profiili seadete lehekülg](/assets/images/user-guide/76_profiles_button.png)
*(Joonis 76: Seaded > Profiili lehekülg – isiklikud vault-seaded)*

2. Klõpsa nuppu **{{t:settings.personal.changePassword.submit}}**.

![Muuda parooli nupp](/assets/images/user-guide/77_profiles_change_button.png)
*(Joonis 77: Nupp "Change Password" isikliku seadete jaotises)*

3. Sisesta uus parool. Parooli nõuded:
   - Vähemalt 8 tähemärki pikk
   - Peab sisaldama suur- ja väiketähti
   - Peab sisaldama vähemalt ühe numbri
   - Peab sisaldama vähemalt ühe erimärgi

4. Sisesta sama parool uuesti väljale **{{t:settings.personal.changePassword.confirmPasswordLabel}}**.
5. Klõpsa nuppu **{{t:settings.personal.changePassword.submit}}**.

![Parooli vahetuse vorm](/assets/images/user-guide/78_profiles_change_form.png)
*(Joonis 78: Parooli vahetuse vorm – turvanõuded on nähtavad)*

> **Vihje**: Tugeva parooli loomisel kasuta juhuslikke kombinatsioone.

---

## 2.8 Salvestus

Salvestuse jaotis võimaldab hallata füüsilisi alasid, kuhu varunduseandmeid salvestatakse.

### 2.8.1 Salvestuse lisamine

![Salvestuse loomise ülevaade](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(Video: Salvestuskoha lisamine)*

1. Mine vasakust menüüst vahekaardile **{{t:common.navigation.storage}}**.
2. Klõpsa nuppu **{{t:resources.storage.createStorage}}**.

![Lisa salvestus nupp](/assets/images/user-guide/79_storage_add_button.png)
*(Joonis 79: Salvestuse halduse lehekülg – nupp "Lisa salvestus")*

3. Täida vorm:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: Sisesta kirjeldav nimi
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: Vali (nt s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: Lisa valikuline kirjeldus
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: Valikuline
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: rclone lipud (nt --transfers 4)

![Salvestuse loomise vorm](/assets/images/user-guide/80_storage_form.png)
*(Joonis 80: Salvestuse lisamise vorm – nimi, pakkuja, kirjeldus ja parameetrid)*

4. Klõpsa nuppu **{{t:common.actions.create}}**.

> **Vihje**: Lisaparameetrid aktsepteerivad rclone lippe salvestuse jõudluse optimeerimiseks.

---

## 2.9 Mandaadid

Mandaatide jaotis võimaldab turvaliselt hallata hoidlate juurdepääsuteavet.

### 2.9.1 Mandaadi muutmine

![Mandaadi muutmise ülevaade](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(Video: Mandaatide muutmine)*

1. Mine vasakust menüüst vahekaardile **{{t:common.navigation.credentials}}**.
2. Vali muuta soovitav kirje.
3. Klõpsa nuppu **{{t:common.actions.edit}}**.

![Mandaatide loend](/assets/images/user-guide/81_credentials.png)
*(Joonis 81: Mandaatide lehekülg – hoidlate nimed, meeskonnad ja haldusnupud)*

4. Muuda vajadusel **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**.
5. Salvesta nupuga **{{t:common.save}}**.

![Mandaadi muutmise vorm](/assets/images/user-guide/82_credentials_form.png)
*(Joonis 82: Hoidla nime muutmise vorm – vault-konfiguratsiooni väljad)*

> **Vihje**: Mandaadid salvestatakse krüpteeritult ja dekrüpteeritakse ainult juurutamise ajal.

### 2.9.2 Mandaadi jälg

![Mandaadi jälje ülevaade](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(Video: Mandaadi auditi ajaloo vaatamine)*

1. Vali jälgitav kirje.
2. Klõpsa nuppu **{{t:common.actions.trace}}**.

![Jälgi nupp](/assets/images/user-guide/83_credentials_trace_button.png)
*(Joonis 83: Nupp "Trace" mandaatide tabelis)*

3. Vaata auditi ajalugu.
4. Vali nupust **{{t:common.actions.export}}** vorming: **{{t:common.exportCSV}}** või **{{t:common.exportJSON}}**.

![Mandaadi auditi ajalugu](/assets/images/user-guide/84_credentials_list_export.png)
*(Joonis 84: Mandaatide loend – ekspordi valikud)*

> **Vihje**: Jälje funktsioon pakub mandaatide kasutuse jälgimist turvaauditi eesmärgil.

### 2.9.3 Mandaadi kustutamine

![Mandaadi kustutamise ülevaade](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(Video: Mandaadi kustutamine)*

1. Vali kustutada soovitav kirje.
2. Klõpsa punast nuppu **{{t:common.delete}}**.

![Kustuta nupp](/assets/images/user-guide/85_credentials_delete.png)
*(Joonis 85: Punane nupp "Delete" mandaatide leheküljel)*

3. Klõpsa kinnitusdialoogi nuppu **{{t:common.delete}}**.

![Kustutamise kinnitus](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(Joonis 86: Kustutamise kinnitamise dialoog – pöördumatu toimingu hoiatus)*

> **Hoiatus**: Enne kustutamist veendu, et mandaati ei kasutata teistel masinatel ega muudes toimingutes. Veendu, et kriitiliste mandaatide varukoopia on olemas enne kustutamist.

---

## 2.10 Järjekord

Järjekorra jaotis võimaldab jälgida süsteemis ootel ja lõpetatud toiminguid.

### 2.10.1 Järjekorra toimingud

![Järjekorra toimingute ülevaade](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(Video: Järjekorra toimingute haldamine)*

1. Klõpsa vasakust menüüst vahekaardile **{{t:common.navigation.queue}}**.

![Järjekorra lehekülg](/assets/images/user-guide/87_queue_button.png)
*(Joonis 87: Järjekorra lehekülg – filtreerimise valikud ja oleku vahekaardid)*

2. Järjekorra üksuste filtreerimiseks:
   - Kasuta filtreid **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}** ja **{{t:queue.trace.bridge}}**
   - Täpsusta **{{t:system.audit.filters.dateRange}}**
   - Märgi valik **{{t:queue.filters.onlyStale}}**

3. Vaata üksikasju oleku vahekaartidel:
   - **{{t:queue.statusActive}}**: Töödeldavad ülesanded
   - **{{t:queue.statusCompleted}}**: Edukalt lõpetatud ülesanded
   - **{{t:queue.statusCancelled}}**: Tühistatud ülesanded
   - **{{t:queue.statusFailed}}**: Ebaõnnestunud ülesanded

4. Vali nupust **{{t:common.actions.export}}** vorming: **{{t:common.exportCSV}}** või **{{t:common.exportJSON}}**.

![Järjekorra eksport](/assets/images/user-guide/88_queue_export.png)
*(Joonis 88: Järjekorra loend – ekspordi valikud)*

> **Vihje**: Valik "{{t:queue.filters.onlyStale}}" aitab leida ülesandeid, mida töödeldakse kaua. Ekspordi järjekorra ajalugu regulaarselt ülesannete täitmise trendide analüüsimiseks.

---

## 2.11 Audit

Auditi jaotis peab arvet kõigi süsteemis teostatud toimingute kohta.

### 2.11.1 Auditi kirjed

![Auditi kirjete ülevaade](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(Video: Süsteemi auditi kirjete vaatamine)*

1. Klõpsa vasakust menüüst vahekaardile **{{t:common.navigation.audit}}**.

![Auditi loend](/assets/images/user-guide/89_audit_list.png)
*(Joonis 89: Auditi lehekülg – kõigi süsteemitoimingute üksikasjalik arvestus)*

2. Filtreeri auditi kirjeid:
   - **Date Range**: Filtreeri konkreetse perioodi järgi
   - **Entity Type**: Filtreeri tüübi järgi (Request, Machine, Queue jne)
   - **Search**: Tee tekstiotsing

3. Vaata iga kirje teavet:
   - **Timestamp**: Toimingu kuupäev ja kellaaeg
   - **Action**: Toimingu tüüp (Create, Edit, Delete jne)
   - **Entity Type**: Mõjutatud objekti tüüp
   - **Entity Name**: Konkreetne objekti identifikaator
   - **User**: Toimingu sooritanud kasutaja
   - **Details**: Täiendav teave toimingu kohta

4. Vali nupust **{{t:common.actions.export}}** vorming: **{{t:common.exportCSV}}** või **{{t:common.exportJSON}}**.

![Auditi eksport](/assets/images/user-guide/90_audit_export.png)
*(Joonis 90: Auditi kirje eksport – CSV ja JSON valikud)*

> **Vihje**: Auditi kirje on kriitiline kõigi süsteemitegevuste jälgimiseks turvalisuse ja vastavuse eesmärgil. Ekspordi auditi kirje regulaarselt ja hoia seda turvalises kohas.

---

**© 2025 Rediacc Platform – All Rights Reserved.**
