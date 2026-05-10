---
title: Applicazione Web
description: Comprensione dell'architettura dell'applicazione web e del deployment con Rediacc. È progettata per la massima semplicità operativa.
category: Reference
order: 1
language: it
---

# Guida utente della piattaforma Rediacc

## Panoramica

**Rediacc** è una piattaforma cloud che offre servizi di backup basati sull'intelligenza artificiale.

Questa guida illustra l'utilizzo di base dell'interfaccia web disponibile su [https://www.rediacc.com/](https://www.rediacc.com/).

### Scopo di questa guida

- Aiutare i nuovi utenti ad adattarsi rapidamente alla piattaforma
- Spiegare le funzioni di base (gestione delle risorse, backup) passo dopo passo

---

## 1. Creazione dell'account e accesso

### 1.1 Registrazione

![Procedura guidata di registrazione](/assets/videos/user-guide/01-01-registration.webm)
*(Video: Flusso completo della registrazione dall'inizio alla fine)*

Per iniziare a utilizzare la piattaforma Rediacc è necessario creare un account.

![Pagina di accesso Rediacc - infrastruttura sempre attiva](/assets/images/user-guide/01_login.png)
*(Figura 1: Pagina di accesso principale, con le funzionalità principali della piattaforma Rediacc)*

1. Naviga su [https://www.rediacc.com/](https://www.rediacc.com/) nel tuo browser.
2. Fai clic sul pulsante **{{t:auth.login.signIn}}** nell'angolo in alto a destra della pagina.
3. Scegli **Get Started** per accesso gratuito oppure **Request Demo** per una dimostrazione.

> **Suggerimento**: È possibile creare un account gratuito senza richiedere alcuna carta di credito. Include team illimitati.

![Modulo di accesso Rediacc - campi email e password](/assets/images/user-guide/02_register.png)
*(Figura 2: Schermata di accesso per gli utenti esistenti)*

4. Se non hai un account, fai clic sul link **{{t:auth.login.register}}** per crearne uno nuovo.

5. Compila le seguenti informazioni nel modulo che si apre:
   - **{{t:auth.registration.organizationName}}**: Inserisci il nome della tua organizzazione
   - **{{t:auth.login.email}}**: Inserisci un indirizzo email valido
   - **{{t:auth.login.password}}**: Crea una password di almeno 8 caratteri
   - **{{t:auth.registration.passwordConfirm}}**: Reinserisci la stessa password

![Finestra di dialogo Crea account - passaggi registra, verifica e completa](/assets/images/user-guide/03_create_account.png)
*(Figura 3: Modulo di registrazione nuovo utente passo dopo passo - Registra > Verifica > Completa)*

6. Spunta la casella per accettare le condizioni di servizio e l'informativa sulla privacy.
7. Fai clic sul pulsante **{{t:auth.registration.createAccount}}**.

> **Suggerimento**: La password deve essere lunga almeno 8 caratteri e deve essere sicura. Tutti i campi sono obbligatori.

8. Inserisci in sequenza nelle caselle il codice di verifica a 6 cifre inviato al tuo indirizzo email.
9. Fai clic sul pulsante **{{t:auth.registration.verifyAccount}}**.

![Inserimento del codice di verifica - codice di attivazione a 6 cifre](/assets/images/user-guide/04_verification_code.png)
*(Figura 4: Finestra per l'inserimento del codice di attivazione inviato all'amministratore)*

> **Suggerimento**: Il codice di verifica ha una validità limitata nel tempo. Se non ricevi il codice, controlla la cartella spam.

---

### 1.2 Accesso

![Procedura guidata di accesso](/assets/videos/user-guide/01-02-login.webm)
*(Video: Flusso completo di accesso)*

Dopo la creazione dell'account puoi accedere alla piattaforma.

1. Compila il campo **{{t:auth.login.email}}** (obbligatorio se appare un avviso rosso).
2. Compila il campo **{{t:auth.login.password}}**.
3. Fai clic sul pulsante **{{t:auth.login.signIn}}**.

![Modulo di accesso - campi obbligatori con avviso di errore](/assets/images/user-guide/05_sign_in.png)
*(Figura 5: Modulo di accesso - i messaggi di errore sono evidenziati con un bordo rosso)*

> **Suggerimento**: Se il messaggio di errore recita "Questo campo è obbligatorio", compila i campi vuoti. Per le password dimenticate contatta l'amministratore.

4. Dopo un accesso riuscito, verrai reindirizzato alla schermata **{{t:common.navigation.dashboard}}**.

![Dashboard Rediacc - elenco macchine e menu laterale](/assets/images/user-guide/06_dashboard.png)
*(Figura 6: Dashboard principale dopo un accesso riuscito - menu Organizzazione, Macchine e Impostazioni nella barra laterale sinistra)*

> **Suggerimento**: Il dashboard si aggiorna automaticamente. Puoi aggiornare la pagina con F5 per ottenere informazioni fresche.

---

## 2. Panoramica dell'interfaccia

Dopo l'accesso, la schermata che vedi è composta dalle seguenti sezioni principali:

- **{{t:common.navigation.organization}}**: Utenti, team e controllo degli accessi
- **{{t:common.navigation.machines}}**: Gestione di server e repository
- **{{t:common.navigation.settings}}**: Impostazioni del profilo e di sistema
- **{{t:common.navigation.storage}}**: Gestione delle aree di archiviazione
- **{{t:common.navigation.credentials}}**: Credenziali di accesso
- **{{t:common.navigation.queue}}**: Gestione della coda dei lavori
- **{{t:common.navigation.audit}}**: Log di audit del sistema

---

## 2.1 Organizzazione - Utenti

La gestione degli utenti consente di controllare l'accesso alla piattaforma per le persone della tua organizzazione.

### 2.1.1 Aggiunta di utenti

![Procedura guidata di aggiunta utenti](/assets/videos/user-guide/02-01-01-user-create.webm)
*(Video: Creazione di un nuovo utente)*

1. Fai clic sull'opzione **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** nella barra laterale sinistra.
2. Visualizza l'elenco di tutti gli utenti in formato tabella.
3. Ogni riga utente mostra email, stato ({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), gruppo di permessi e ora dell'ultima attività.

![Pagina di gestione utenti - elenco utenti attivi](/assets/images/user-guide/07_users.png)
*(Figura 7: Sezione Utenti sotto Organizzazione - le informazioni di tutti gli utenti sono visualizzate)*

4. Fai clic sull'icona **"+"** nell'angolo in alto a destra.
5. Fai clic sul pulsante **{{t:organization.users.modals.createTitle}}** e compila il modulo che si apre:
   - **{{t:organization.users.form.emailLabel}}**: Inserisci l'indirizzo email dell'utente
   - **{{t:organization.users.form.passwordLabel}}**: Inserisci una password temporanea

![Finestra di dialogo di creazione utente - campi email e password](/assets/images/user-guide/08_user_add.png)
*(Figura 8: Finestra modale per l'aggiunta di un nuovo utente - modulo di creazione utente semplice e rapido)*

6. Fai clic sul pulsante **{{t:common.actions.create}}**.

> **Suggerimento**: Le credenziali di accesso devono essere comunicate in modo sicuro all'utente creato. Si consiglia di cambiare la password al primo accesso.

![Elenco utenti - vista tabella completa con tre utenti](/assets/images/user-guide/09_user_list.png)
*(Figura 9: Tutti gli utenti attivi e inattivi nella pagina di gestione utenti)*

> **Suggerimento**: La pagina mostra automaticamente 20 record. Usa la paginazione per vedere più record.

### 2.1.2 Assegnazione dei permessi agli utenti

![Procedura guidata dei permessi utente](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(Video: Assegnazione di gruppi di permessi agli utenti)*

Puoi gestire i diritti di accesso assegnando specifici gruppi di permessi agli utenti.

1. Seleziona un utente dalla scheda **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**.
2. Fai clic sull'icona a scudo nella colonna delle azioni (**{{t:organization.access.tabs.permissions}}**).

![Gestione permessi - icone scudo, ingranaggio ed elimina](/assets/images/user-guide/10_users_permissions.png)
*(Figura 10: Visualizzazione delle icone delle azioni utente - ciascuna icona rappresenta un'azione diversa)*

3. Seleziona un **{{t:organization.users.modals.permissionGroupLabel}}** dal modulo che si apre.
4. Il numero di utenti e permessi nel gruppo è mostrato accanto all'utente.
5. Fai clic sul pulsante **{{t:organization.users.modals.assignTitle}}** per salvare le modifiche.

![Finestra di assegnazione permessi - gruppo Administrators](/assets/images/user-guide/11_user_permissions_form.png)
*(Figura 11: Finestra modale per l'assegnazione del gruppo di permessi all'utente selezionato - menu a tendina con i gruppi disponibili)*

> **Suggerimento**: Alcuni gruppi di permessi sono fissi di sistema e non possono essere modificati.

### 2.1.3 Attivazione degli utenti

![Procedura guidata di attivazione utente](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(Video: Attivazione di un utente inattivo)*

È possibile riattivare gli utenti disabilitati.

1. Trova l'utente con stato inattivo nell'elenco **Utenti**.
2. Fai clic sull'icona rossa nella colonna delle azioni.

![Attivazione utente - visualizzazione del tooltip "Attiva"](/assets/images/user-guide/12_users_activation.png)
*(Figura 12: Attivazione di un utente inattivo)*

3. Fai clic sul pulsante **{{t:common.general.yes}}** nella finestra di conferma.

![Finestra modale di conferma attivazione](/assets/images/user-guide/13_users_activation_confirm.png)
*(Figura 13: Finestra modale per la conferma dell'attivazione utente)*

> **Suggerimento**: Questa azione è reversibile. Puoi disattivare l'utente nello stesso modo.

### 2.1.4 Traccia utente

![Procedura guidata di traccia utente](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(Video: Visualizzazione della traccia delle attività dell'utente)*

Puoi utilizzare la funzione di traccia per monitorare le attività degli utenti.

1. Seleziona un utente e fai clic sull'icona a ingranaggio nella colonna delle azioni.
2. Fai clic sull'opzione **{{t:common.actions.trace}}** per aprire la cronologia delle attività dell'utente.

![Traccia utente - tooltip "Trace" con pulsante di azione](/assets/images/user-guide/14_users_trace.png)
*(Figura 14: Opzione di traccia delle attività dell'utente)*

3. Le attività passate dell'utente sono elencate nella schermata che si apre.
4. Le statistiche sono visualizzate in alto: Record totali, Record visualizzati, Ultima attività.
5. Fai clic sul pulsante **{{t:common.actions.export}}** e seleziona il formato: **{{t:common.exportCSV}}** o **{{t:common.exportJSON}}**.

![Cronologia audit - Opzioni di esportazione](/assets/images/user-guide/15_user_trace_export.png)
*(Figura 15: Cronologia completa delle attività dell'utente - statistiche, dettagli e opzioni di esportazione)*

> **Suggerimento**: Esporta regolarmente i dati di audit per mantenere i registri di sicurezza e conformità. Il formato CSV può essere aperto in Excel.

---

## 2.2 Organizzazione - Team

I team ti consentono di raggruppare gli utenti e fornire accesso collettivo alle risorse.

### 2.2.1 Creazione di team

![Procedura guidata di creazione team](/assets/videos/user-guide/02-02-01-team-create.webm)
*(Video: Creazione di un nuovo team)*

1. Vai alla scheda **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}**.
2. Fai clic sul pulsante **"+"**.
3. Inserisci il nome del team nel campo **{{t:common.vaultEditor.fields.TEAM.name.label}}**.
4. Compila i campi **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** e **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** nella sezione **{{t:common.vaultEditor.vaultConfiguration}}**.

![Modulo di creazione nuovo team - nome del team e chiavi SSH](/assets/images/user-guide/16_teams_create.png)
*(Figura 16: Creazione di un nuovo team all'interno di "Private Team")*

5. Fai clic sul pulsante **{{t:common.actions.create}}** per salvare il team.

> **Suggerimento**: Le chiavi SSH sono obbligatorie per l'autenticazione SSH tramite Bridge. Se ricevi un avviso di chiave mancante, fornisci entrambe le chiavi.

### 2.2.2 Modifica del team

![Procedura guidata di modifica team](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(Video: Modifica delle informazioni del team)*

1. Fai clic sull'icona a matita accanto al team che vuoi modificare nell'elenco dei team.
2. Se necessario, modifica il nome del team nel campo **{{t:common.vaultEditor.fields.TEAM.name.label}}**.
3. Aggiorna le chiavi SSH nella sezione **{{t:common.vaultEditor.vaultConfiguration}}**.
4. Fai clic sul pulsante **{{t:common.save}}** per applicare le modifiche.

![Modulo di modifica team - messaggio informativo blu](/assets/images/user-guide/17_teams_edit_form.png)
*(Figura 17: Modifica delle informazioni di un team esistente)*

> **Suggerimento**: La configurazione del team viene utilizzata per la struttura organizzativa. Le modifiche hanno effetto per tutti i membri del team.

### 2.2.3 Gestione dei membri del team

![Procedura guidata di gestione dei membri del team](/assets/videos/user-guide/02-02-03-team-members.webm)
*(Video: Gestione dei membri del team)*

1. Seleziona un team e fai clic sull'icona utente.
2. Visualizza i membri già assegnati al team nella scheda **{{t:organization.teams.manageMembers.currentTab}}**.
3. Passa alla scheda **{{t:organization.teams.manageMembers.addTab}}**.
4. Inserisci un indirizzo email o seleziona un utente dal menu a tendina.
5. Fai clic sul pulsante **"+"** per aggiungere il membro al team.

![Modulo di gestione membri del team - schede "Membri attuali" e "Aggiungi membro"](/assets/images/user-guide/18_teams_members_form.png)
*(Figura 18: Pannello di gestione dei membri del team)*

> **Suggerimento**: Puoi assegnare lo stesso membro a più team.

### 2.2.4 Traccia del team

![Procedura guidata di traccia del team](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(Video: Visualizzazione della cronologia audit del team)*

1. Seleziona il team che vuoi tracciare.
2. Fai clic sull'icona orologio/cronologia.
3. Esamina i conteggi di Record totali, Record visualizzati e Ultima attività nella finestra modale **{{t:resources.audit.title}}**.
4. Fai clic sul pulsante **{{t:common.actions.export}}** per esportare in formato {{t:common.exportCSV}} o {{t:common.exportJSON}}.

![Finestra modale di cronologia audit - team DataBassTeam](/assets/images/user-guide/19_teams_trace.png)
*(Figura 19: Visualizzazione della cronologia audit del team)*

> **Suggerimento**: La cronologia audit è importante per la conformità e il controllo della sicurezza.

### 2.2.5 Eliminazione del team

![Procedura guidata di eliminazione team](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(Video: Eliminazione di un team)*

1. Fai clic sull'icona cestino (rossa) accanto al team che vuoi eliminare.
2. Verifica che il nome del team sia corretto nella finestra di dialogo di conferma.
3. Fai clic sul pulsante **{{t:common.general.yes}}**.

![Finestra di dialogo di conferma eliminazione team](/assets/images/user-guide/20_teams_delete.png)
*(Figura 20: Conferma dell'eliminazione del team)*

> **Avvertenza**: L'eliminazione del team è irreversibile. Controlla se il team contiene dati importanti prima di eliminarlo.

---

## 2.3 Organizzazione - Controllo degli accessi

Il controllo degli accessi consente di gestire centralmente i permessi degli utenti creando gruppi di permessi.

### 2.3.1 Creazione di gruppi di permessi

![Procedura guidata di creazione gruppo di permessi](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(Video: Creazione di un gruppo di permessi)*

1. Vai alla scheda **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}**.
2. Fai clic sul pulsante **"+"**.
3. Inserisci un nome significativo nel campo **{{t:organization.access.modals.groupPlaceholder}}**.
4. Fai clic sul pulsante **{{t:common.actions.confirm}}** per creare il gruppo.

![Modulo di creazione gruppo di permessi](/assets/images/user-guide/21_create_access.png)
*(Figura 21: Creazione di un nuovo gruppo di permessi)*

> **Suggerimento**: I gruppi di permessi servono per organizzare gli utenti con permessi simili. Mantieni i nomi dei gruppi descrittivi (es. "Admin", "Solo lettura", "Repository Manager").

### 2.3.2 Gestione dei permessi

![Procedura guidata di gestione permessi](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(Video: Gestione dei permessi per un gruppo)*

1. Seleziona un gruppo di permessi e fai clic sull'opzione **{{t:organization.access.modals.managePermissionsTitle}}**.
2. Visualizza i diritti di accesso del gruppo nella scheda **{{t:organization.access.modals.currentPermissionsTab}}**.
3. Puoi revocare un permesso facendo clic sul pulsante rosso **{{t:common.delete}}** accanto a ciascuna azione.
4. Fai clic sulla scheda **{{t:organization.access.modals.addPermissionsTab}}** per aggiungere nuovi permessi al gruppo.

![Pannello di gestione permessi - elenco permessi assegnati](/assets/images/user-guide/22_access_permission.png)
*(Figura 22: Gestione dei permessi per il gruppo di permessi)*

> **Suggerimento**: Concedi i permessi in base al principio del minimo privilegio. Esamina e rimuovi regolarmente i permessi non necessari.

---

## 2.4 Macchine

La sezione Macchine consente di gestire i tuoi server e le risorse dei repository.

### 2.4.1 Aggiunta di macchine

![Procedura guidata di aggiunta macchine](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(Video: Aggiunta di una nuova macchina)*

1. Vai alla scheda **{{t:common.navigation.machines}}** dal menu di sinistra.
2. Fai clic sul pulsante **{{t:machines.createMachine}}** nell'angolo in alto a destra.

![Pagina Macchine - pulsante "Aggiungi macchina"](/assets/images/user-guide/23_machines_add.png)
*(Figura 23: Pagina principale di gestione macchine)*

3. Compila il modulo che si apre:
   - **{{t:machines.machineName}}**: Inserisci un nome univoco (es. "server-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: Inserisci l'indirizzo IP della macchina (es. 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: Specifica la directory di archiviazione (es. /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: Inserisci il nome utente SSH
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: Inserisci il numero di porta (predefinito: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: Inserisci la password (opzionale)

![Modulo di aggiunta macchina - tutti i campi](/assets/images/user-guide/24_machine_create.png)
*(Figura 24: Modulo di aggiunta nuova macchina - nome macchina, impostazioni di rete, credenziali SSH)*

4. Fai clic sul pulsante **{{t:common.vaultEditor.testConnection.button}}** per verificare la connessione.
5. Dopo che il test è riuscito, fai clic sul pulsante **{{t:common.actions.create}}**.

> **Suggerimento**: Se l'opzione "Avvia automaticamente la configurazione dopo la creazione della macchina" è selezionata, la macchina eseguirà automaticamente ulteriori passaggi di configurazione.

![Creazione macchina completata - finestra di monitoraggio attività](/assets/images/user-guide/25_machine_create_complete.png)
*(Figura 25: Finestra di monitoraggio attività dopo la creazione riuscita della macchina)*

6. Osserva le fasi: **{{t:queue.trace.assigned}}** → **Elaborazione in corso** → **{{t:queue.statusCompleted}}**
7. Fai clic sul pulsante **{{t:common.actions.close}}** per chiudere l'operazione.

> **Suggerimento**: Fai clic sul pulsante "{{t:common.actions.refresh}}" per controllare manualmente lo stato più recente.

### 2.4.2 Test di connettività

![Procedura guidata di test di connettività](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(Video: Esecuzione di un test di connettività)*

Puoi verificare lo stato della connessione delle macchine esistenti.

1. Fai clic sul pulsante **{{t:machines.connectivityTest}}**.

![Pulsante Test di connettività](/assets/images/user-guide/26_connectivity_test_button.png)
*(Figura 26: Pulsante Test di connettività nella barra degli strumenti delle azioni macchina)*

2. Visualizza l'elenco delle macchine da testare.
3. Fai clic sul pulsante **{{t:machines.runTest}}**.
4. I risultati positivi sono mostrati in verde, quelli negativi in rosso.

![Modulo di test di connettività - elenco macchine](/assets/images/user-guide/27_connectivity_test_form.png)
*(Figura 27: Modulo di test di connettività - funzione ping per le macchine selezionate)*

> **Suggerimento**: Se il test fallisce, controlla l'indirizzo IP della macchina e le impostazioni SSH.

### 2.4.3 Aggiornamento dell'elenco macchine

![Procedura guidata di aggiornamento elenco macchine](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(Video: Aggiornamento dell'elenco macchine)*

Fai clic sul pulsante **{{t:common.actions.refresh}}** per aggiornare l'elenco delle macchine.

![Pulsante Aggiorna](/assets/images/user-guide/28_refresh.png)
*(Figura 28: Pulsante Aggiorna nella barra degli strumenti delle azioni macchina)*

### 2.4.4 Dettagli della macchina

![Procedura guidata dei dettagli della macchina](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(Video: Visualizzazione dei dettagli della macchina)*

1. Seleziona la macchina di cui vuoi visualizzare i dettagli.
2. Fai clic sul pulsante icona occhio (**{{t:common.viewDetails}}**).

![Pulsante Visualizza dettagli](/assets/images/user-guide/29_view_details_button.png)
*(Figura 29: Icona occhio nella colonna delle azioni macchina)*

3. Il pannello dei dettagli della macchina si apre sul lato destro:
   - **Hostname**: Nome della macchina
   - **Uptime**: Tempo di esecuzione
   - **{{t:queue.trace.operatingSystem}}**: Sistema operativo e versione
   - **{{t:queue.trace.kernelVersion}}**: Versione del kernel
   - **CPU**: Informazioni sul processore
   - **System Time**: Orologio di sistema

![Pannello dei dettagli macchina - informazioni di sistema](/assets/images/user-guide/30_machine_view_details.png)
*(Figura 30: Pannello dei dettagli macchina - informazioni su hostname, uptime, OS, kernel, CPU)*

> **Suggerimento**: Esamina regolarmente queste informazioni per verificare la compatibilità del sistema operativo e la disponibilità delle risorse.

### 2.4.5 Modifica della macchina

![Procedura guidata di modifica macchina](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(Video: Modifica delle impostazioni della macchina)*

1. Seleziona la macchina che vuoi modificare.
2. Fai clic sul pulsante icona a matita (**{{t:common.actions.edit}}**).

![Pulsante Modifica](/assets/images/user-guide/31_edit_button.png)
*(Figura 31: Icona a matita nella colonna delle azioni macchina)*

3. Apporta le modifiche necessarie.
4. Fai clic sul pulsante **{{t:common.vaultEditor.testConnection.button}}**.
5. Quando la connessione ha esito positivo, fai clic sul pulsante **{{t:common.save}}**.

![Modulo di modifica macchina](/assets/images/user-guide/32_edit_form.png)
*(Figura 32: Modulo di modifica macchina - nome macchina, regione e configurazione vault)*

> **Suggerimento**: Esegui sempre "Testa connessione" dopo aver modificato impostazioni critiche.

### 2.4.6 Traccia della macchina

![Procedura guidata di traccia della macchina](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(Video: Visualizzazione della cronologia audit della macchina)*

1. Seleziona la macchina e fai clic sul pulsante icona orologio (**{{t:common.actions.trace}}**).

![Pulsante Traccia](/assets/images/user-guide/33_trace_button.png)
*(Figura 33: Icona orologio nella colonna delle azioni macchina)*

2. Esamina le operazioni nella finestra della cronologia audit:
   - **{{t:resources.audit.action}}**: Tipo di operazione eseguita
   - **Dettagli**: Campi modificati
   - **{{t:resources.audit.performedBy}}**: Utente che ha eseguito l'azione
   - **Timestamp**: Data e ora

![Finestra della cronologia audit della macchina](/assets/images/user-guide/34_trace_list.png)
*(Figura 34: Cronologia audit - elenco di tutte le modifiche)*

> **Suggerimento**: Fai clic sulla colonna Timestamp per visualizzare le modifiche in ordine cronologico.

### 2.4.7 Eliminazione della macchina

![Procedura guidata di eliminazione macchina](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(Video: Eliminazione di una macchina)*

1. Seleziona la macchina che vuoi eliminare.
2. Fai clic sul pulsante icona cestino (**{{t:common.delete}}**).

![Pulsante Elimina](/assets/images/user-guide/35_delete_button.png)
*(Figura 35: Icona cestino nella colonna delle azioni macchina)*

3. Fai clic sul pulsante **{{t:common.delete}}** nella finestra di conferma.

![Finestra di conferma eliminazione macchina](/assets/images/user-guide/36_delete_form.png)
*(Figura 36: Finestra di conferma "Sei sicuro di voler eliminare questa macchina?")*

> **Avvertenza**: Quando una macchina viene eliminata, vengono rimossi anche tutti i repository su di essa. Questa azione è irreversibile.

### 2.4.8 Operazioni remote

![Procedura guidata di operazioni remote](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(Video: Esecuzione di operazioni remote su una macchina)*

Puoi eseguire varie operazioni remote sulle macchine.

1. Seleziona la macchina e fai clic sul pulsante **{{t:common.actions.remote}}**.
2. Visualizza le opzioni nel menu a tendina:
   - **{{t:machines.runAction}}**: Esegui funzione sulla macchina
   - **{{t:common.vaultEditor.testConnection.button}}**: Esegui ping sulla macchina

![Menu Remote - Esegui sul server e Testa connessione](/assets/images/user-guide/37_remote_button.png)
*(Figura 37: Pulsante Remote - menu di esecuzione funzione sulla macchina selezionata)*

> **Suggerimento**: Usa l'opzione "{{t:common.vaultEditor.testConnection.button}}" per verificare che la macchina sia accessibile prima di eseguire le funzioni.

#### Configurazione

1. Seleziona l'opzione **{{t:machines.runAction}}**.
2. Trova la funzione **Setup** nell'elenco **{{t:functions.availableFunctions}}**.
3. Fai clic sul nome della funzione per selezionarla.

![Elenco funzioni macchina - funzione setup](/assets/images/user-guide/38_server_setup.png)
*(Figura 38: Funzione Setup - prepara la macchina con gli strumenti e le configurazioni necessari)*

> **Suggerimento**: Si consiglia di eseguire prima la funzione "setup" quando si configura una nuova macchina.

#### Verifica della connessione (Hello)

1. Seleziona **{{t:machines.runAction}}** > funzione **Hello**.
2. Fai clic sul pulsante **{{t:common.actions.addToQueue}}**.

![Selezione della funzione Hello](/assets/images/user-guide/39_remote_hello.png)
*(Figura 39: Funzione Hello - semplice funzione di test, restituisce il nome host)*

3. Osserva i risultati nella finestra di monitoraggio attività.
4. Visualizza l'output della macchina nella sezione **{{t:queue.trace.responseConsole}}**.

![Funzione Hello completata](/assets/images/user-guide/40_remote_hello_complete.png)
*(Figura 40: Funzione Hello completata con successo - risposta con il nome host)*

> **Suggerimento**: La funzione hello è ideale per verificare la connettività della macchina.

#### Operazioni avanzate

1. Segui il percorso **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}**.
2. Visualizza le funzioni disponibili: setup, hello, ping, ssh_test, uninstall
3. Seleziona la funzione richiesta e fai clic sul pulsante **{{t:common.actions.addToQueue}}**.

![Elenco funzioni avanzate](/assets/images/user-guide/41_remote_advanced.png)
*(Figura 41: Opzione Avanzate - elenco delle funzioni avanzate)*

> **Suggerimento**: Prima di utilizzare le funzioni avanzate, assicurati che la configurazione della macchina sia completa.

#### Test di connettività rapido

![Menu Remote - Testa connessione](/assets/images/user-guide/42_connectivity_test.png)
*(Figura 42: Opzione Testa connessione dal menu Remote)*

> **Suggerimento**: Se la macchina presenta problemi SSH o di rete, puoi identificare rapidamente i problemi con questo test.

---

## 2.5 Creazione e operazioni sui repository

I repository sono le unità fondamentali in cui vengono archiviati i dati di backup.

### 2.5.1 Creazione di repository

![Procedura guidata di creazione repository](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(Video: Creazione di un nuovo repository)*

1. Seleziona una macchina dalla scheda **{{t:common.navigation.machines}}**.
2. Fai clic sul pulsante **{{t:machines.createRepository}}** nell'angolo in alto a destra.

![Pulsante Crea repository](/assets/images/user-guide/43_create_repo_add.png)
*(Figura 43: Schermata di gestione repository della macchina - pulsante Crea repository)*

3. Compila il modulo:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: Inserisci il nome del repository (es. postgresql)
   - **{{t:resources.repositories.size}}**: Inserisci la dimensione del repository (es. 2GB)
   - **{{t:resources.repositories.repositoryGuid}}**: Visualizza la credenziale generata automaticamente
   - **{{t:resources.templates.selectTemplate}}**: Scegli un template (es. databases_postgresql)

![Modulo di creazione repository](/assets/images/user-guide/44_repo_form.png)
*(Figura 44: Modulo di creazione repository - nome, dimensione e selezione template)*

4. Fai clic sul pulsante **{{t:common.actions.create}}**.

> **Suggerimento**: L'ID credenziale viene generato automaticamente; la modifica manuale non è consigliata.

5. Osserva le fasi nella finestra di monitoraggio attività: **{{t:queue.trace.assigned}}** → **Elaborazione in corso** → **{{t:queue.statusCompleted}}**

![Creazione repository completata](/assets/images/user-guide/45_repo_complete.png)
*(Figura 45: Repository in coda per la creazione - monitoraggio attività)*

6. Fai clic sul pulsante **{{t:common.actions.close}}**.

> **Suggerimento**: L'attività si completa di solito entro 1-2 minuti.

![Elenco repository](/assets/images/user-guide/46_repo_list.png)
*(Figura 46: Il repository creato appare nell'elenco)*

### 2.5.2 Fork del repository

![Procedura guidata di fork del repository](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(Video: Fork di un repository)*

Puoi creare un nuovo repository copiando uno esistente.

1. Seleziona il repository che vuoi copiare.
2. Fai clic sul menu **fx** (funzione).
3. Fai clic sull'opzione **fork**.

![Menu fx - opzione fork](/assets/images/user-guide/47_fork_button.png)
*(Figura 47: Menu fx sul lato destro - operazioni sul repository)*

4. Inserisci un nuovo tag nel campo **{{t:functions.functions.fork.params.tag.label}}** (es. 2025-12-06-20-37-08).
5. Fai clic sul pulsante **{{t:common.actions.addToQueue}}**.

![Modulo di configurazione fork](/assets/images/user-guide/48_fork_form.png)
*(Figura 48: Specifica il nuovo tag per il repository nell'operazione di fork)*

6. Attendi il messaggio **{{t:queue.statusCompleted}}** e fai clic sul pulsante **{{t:common.actions.close}}**.

![Fork completato](/assets/images/user-guide/49_repo_completed.png)
*(Figura 49: Operazione di fork completata con successo)*

> **Suggerimento**: Creare tag nel formato data-ora predefinito è una buona pratica. L'operazione di fork non influisce sul repository originale.

### 2.5.3 Avvio del repository (Up)

![Procedura guidata di avvio del repository](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(Video: Avvio di un repository)*

Per attivare il repository:

1. Seleziona il repository e segui il percorso **fx** > **up**.

![Operazione Up](/assets/images/user-guide/50_repo_up.png)
*(Figura 50: Opzione "up" dal menu fx - avvio del repository)*

2. Attendi il messaggio **{{t:queue.statusCompleted}}**.

![Up completato](/assets/images/user-guide/51_repo_up_complete.png)
*(Figura 51: Avvio del repository completato)*

> **Suggerimento**: L'operazione "Up" avvia i servizi Docker definiti dal repository.

### 2.5.4 Arresto del repository (Down)

![Procedura guidata di arresto del repository](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(Video: Arresto di un repository)*

Per fermare un repository attivo:

1. Seleziona il repository e segui il percorso **fx** > **down**.

![Operazione Down](/assets/images/user-guide/52_down_button.png)
*(Figura 52: Opzione "down" dal menu fx - spegnimento del repository)*

2. Attendi il messaggio **{{t:queue.statusCompleted}}**.

![Down completato](/assets/images/user-guide/53_down_completed.png)
*(Figura 53: Spegnimento del repository completato)*

> **Suggerimento**: L'operazione "Down" spegne in modo sicuro il repository. Non viene perso alcun dato; vengono fermati solo i servizi.

### 2.5.5 Deploy

![Procedura guidata di deploy del repository](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(Video: Deploy di un repository)*

Per eseguire il deploy del repository in una posizione diversa:

1. Seleziona il repository e segui il percorso **fx** > **deploy**.

![Operazione Deploy](/assets/images/user-guide/54_deploy_button.png)
*(Figura 54: Opzione "deploy" dal menu fx)*

2. Inserisci la versione da distribuire nel campo **{{t:functions.functions.fork.params.tag.label}}**.
3. Seleziona le macchine di destinazione nel campo **{{t:functions.functions.backup_deploy.params.machines.label}}**.
4. Spunta l'opzione **{{t:functions.checkboxOptions.overrideExistingFile}}** (se applicabile).
5. Fai clic sul pulsante **{{t:common.actions.addToQueue}}**.

![Modulo deploy](/assets/images/user-guide/55_deploy_form.png)
*(Figura 55: Configurazione dell'operazione di deploy - tag, macchine di destinazione e opzioni)*

6. Attendi il messaggio **{{t:queue.statusCompleted}}**.

![Deploy completato](/assets/images/user-guide/56_deploy_completed.png)
*(Figura 56: Deploy del repository completato)*

> **Suggerimento**: Dopo il completamento del deploy, puoi eseguire il comando "up" per avviare il repository sulle macchine di destinazione.

### 2.5.6 Backup

![Procedura guidata di backup del repository](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(Video: Backup di un repository)*

Per eseguire il backup del repository:

1. Seleziona il repository e segui il percorso **fx** > **backup**.

![Operazione Backup](/assets/images/user-guide/57_backup_button.png)
*(Figura 57: Opzione "backup" dal menu fx)*

2. Compila il modulo:
   - **{{t:functions.functions.fork.params.tag.label}}**: Inserisci un nome descrittivo (es. backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}**: Seleziona la posizione di backup
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: Abilita o disabilita l'opzione
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: Esamina l'impostazione

![Modulo di backup](/assets/images/user-guide/58_backup_form.png)
*(Figura 58: Modulo di configurazione del backup - destinazione, nome file e opzioni)*

3. Fai clic sul pulsante **{{t:common.actions.addToQueue}}**.

> **Suggerimento**: Usa un nome descrittivo per il tag di backup. Considera di abilitare il checkpoint per i repository di grandi dimensioni.

4. Attendi il messaggio **{{t:queue.statusCompleted}}**.

![Backup completato](/assets/images/user-guide/59_backup_completed.png)
*(Figura 59: Attività di backup completata con successo)*

> **Suggerimento**: Attendi con pazienza prima che venga raggiunto lo stato completato; i backup di grandi dimensioni possono richiedere diversi minuti.

### 2.5.7 Applicazione del template

![Procedura guidata di applicazione del template](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(Video: Applicazione di un template a un repository)*

Per applicare un nuovo template al repository:

1. Seleziona il repository e segui il percorso **fx** > **{{t:resources.templates.selectTemplate}}**.

![Operazione Template](/assets/images/user-guide/60_templates_button.png)
*(Figura 60: Opzione "Templates" dal menu fx)*

2. Filtra i template digitando nella casella di ricerca.
3. Fai clic sul template desiderato per selezionarlo (il template selezionato è evidenziato con un bordo più spesso).
4. Fai clic sul pulsante **{{t:common.actions.addToQueue}}**.

![Modulo di selezione template](/assets/images/user-guide/61_templates_form.png)
*(Figura 61: Ricerca e selezione dei template disponibili)*

> **Suggerimento**: Usa la casella di ricerca per trovare rapidamente i template. Usa "{{t:common.viewDetails}}" per scoprire le caratteristiche del template.

5. Attendi il messaggio **{{t:queue.statusCompleted}}**.

![Template applicato](/assets/images/user-guide/62_templates_completed.png)
*(Figura 62: Applicazione del template completata con successo)*

### 2.5.8 Smontaggio (Unmount)

![Procedura guidata di smontaggio del repository](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(Video: Smontaggio di un repository)*

Per disconnettere il repository:

1. Seleziona il repository e segui il percorso **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}**.

![Operazione Unmount](/assets/images/user-guide/63_unmount_button.png)
*(Figura 63: Opzione "Unmount" nel menu avanzato)*

2. Attendi il messaggio **{{t:queue.statusCompleted}}**.

![Smontaggio completato](/assets/images/user-guide/64_unmount_completed.png)
*(Figura 64: Operazione di smontaggio completata)*

> **Suggerimento**: Prima di smontare, assicurati che non ci siano operazioni attive sul repository. Dopo lo smontaggio, il repository diventa inaccessibile.

### 2.5.9 Espansione

![Procedura guidata di espansione del repository](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(Video: Espansione della dimensione del repository)*

Per aumentare la dimensione del repository:

1. Seleziona il repository e segui il percorso **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}**.

![Operazione Espandi](/assets/images/user-guide/65_expand_button.png)
*(Figura 65: Opzione "Expand" nel menu avanzato)*

2. Inserisci la dimensione desiderata nel campo **{{t:functions.functions.repository_expand.params.size.label}}**.
3. Seleziona l'unità dal menu a tendina a destra (GB, TB).
4. Fai clic sul pulsante **{{t:common.actions.addToQueue}}**.

![Modulo di espansione](/assets/images/user-guide/66_expand_form.png)
*(Figura 66: Parametro della nuova dimensione per aumentare la dimensione del repository)*

> **Suggerimento**: Non inserire un valore inferiore alla dimensione attuale. Il servizio non viene interrotto durante l'espansione del repository.

5. Attendi il messaggio **{{t:queue.statusCompleted}}**.

![Espansione completata](/assets/images/user-guide/67_expand_completed.png)
*(Figura 67: Espansione del repository completata)*

### 2.5.10 Rinomina

![Procedura guidata di rinomina del repository](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(Video: Rinomina di un repository)*

Per cambiare il nome del repository:

1. Seleziona il repository e segui il percorso **fx** > **{{t:common.actions.rename}}**.

![Operazione Rinomina](/assets/images/user-guide/68_rename_button.png)
*(Figura 68: Opzione "Rename" dal menu fx)*

2. Inserisci il nuovo nome del repository.
3. Fai clic sul pulsante **{{t:common.save}}**.

![Modulo di rinomina](/assets/images/user-guide/69_rename_form.png)
*(Figura 69: Finestra di dialogo per l'inserimento del nuovo nome del repository)*

> **Suggerimento**: I nomi dei repository devono essere significativi per riflettere il tipo e lo scopo del repository. Evita i caratteri speciali.

### 2.5.11 Eliminazione del repository

![Procedura guidata di eliminazione del repository](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(Video: Eliminazione di un repository)*

Per eliminare definitivamente il repository:

1. Seleziona il repository e segui il percorso **fx** > **{{t:resources.repositories.deleteRepository}}**.

![Operazione Elimina repository](/assets/images/user-guide/70_delete_repo_button.png)
*(Figura 70: Opzione "Delete Repository" dal menu fx - in rosso)*

2. Fai clic sul pulsante **{{t:common.delete}}** nella finestra di conferma.

> **Avvertenza**: L'eliminazione del repository è irreversibile. Assicurati che i dati del repository siano stati sottoposti a backup prima di eliminarlo.

### 2.5.12 Dettagli del repository

![Procedura guidata dei dettagli del repository](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(Video: Visualizzazione dei dettagli del repository)*

Per ottenere informazioni dettagliate sul repository:

1. Seleziona il repository.
2. Fai clic sull'icona occhio (**{{t:common.viewDetails}}**).

![Pulsante Visualizza dettagli](/assets/images/user-guide/71_repo_view_button.png)
*(Figura 71: Icona occhio per aprire i dettagli del repository)*

3. Esamina le informazioni nel pannello dei dettagli:
   - **Nome repository** e tipo
   - **Team**: Il team a cui appartiene
   - **Machine**: La macchina su cui si trova
   - **Vault Version**: Versione della crittografia
   - **Repository GUID**: Identificatore univoco
   - **Status**: Stato montato/smontato
   - **Image Size**: Dimensione totale
   - **Last Modified**: Data dell'ultima modifica

![Pannello dei dettagli del repository](/assets/images/user-guide/72_repo_details_view.png)
*(Figura 72: Informazioni complete sul repository selezionato)*

> **Suggerimento**: Tutte le informazioni mostrate in questo pannello sono di riferimento. Usa le opzioni del menu fx per le operazioni sul repository.

---

## 2.6 Operazioni di connessione al repository

Puoi connetterti ai repository utilizzando metodi diversi.

### 2.6.1 Connessione tramite applicazione desktop

![Procedura guidata di connessione desktop](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(Video: Connessione tramite applicazione desktop)*

1. Fai clic sul pulsante **{{t:resources.localActions.local}}** nella riga del repository.

![Pulsante di connessione locale](/assets/images/user-guide/73_repo_connection_local.png)
*(Figura 73: Pulsante "Local" nella riga del repository - accesso all'applicazione desktop)*

2. Seleziona il metodo di accesso dal menu a tendina:
   - **{{t:resources.localActions.openInDesktop}}**: Accedi con interfaccia grafica
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: Apri nell'editor di codice
   - **{{t:common.terminal.terminal}}**: Accedi tramite riga di comando
   - **{{t:resources.localActions.showCLICommands}}**: Strumenti da riga di comando

![Menu delle opzioni di connessione](/assets/images/user-guide/74_repo_connection.png)
*(Figura 74: Menu di connessione al repository - percorsi di accesso diversi)*

> **Suggerimento**: Se lavori con VS Code, l'opzione "{{t:resources.localCommandBuilder.vscodeTab}}" offre l'integrazione più rapida.

3. Fai clic sul pulsante **{{t:common.vscodeSelection.open}}** quando il browser richiede l'autorizzazione.

![Autorizzazione apertura applicazione desktop](/assets/images/user-guide/75_desktop_open_page.png)
*(Figura 75: Il browser chiede l'autorizzazione per aprire l'applicazione desktop)*

> **Suggerimento**: Se non vuoi concedere l'autorizzazione ogni volta che apri l'applicazione desktop, spunta l'opzione "Consenti sempre".

---

## 2.7 Impostazioni

Puoi gestire il tuo profilo e le impostazioni di sistema dalla sezione Impostazioni.

### 2.7.1 Cambio password

![Procedura guidata di cambio password](/assets/videos/user-guide/02-07-03-password-change.webm)
*(Video: Cambio della password)*

1. Vai alla scheda **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}** dal menu di sinistra.

![Pagina impostazioni profilo](/assets/images/user-guide/76_profiles_button.png)
*(Figura 76: Pagina Impostazioni > Profilo - impostazioni del vault personale)*

2. Fai clic sul pulsante **{{t:settings.personal.changePassword.submit}}**.

![Pulsante Cambia password](/assets/images/user-guide/77_profiles_change_button.png)
*(Figura 77: Pulsante "Cambia password" nella sezione delle impostazioni personali)*

3. Inserisci la tua nuova password. Requisiti della password:
   - Almeno 8 caratteri
   - Deve contenere lettere maiuscole e minuscole
   - Deve contenere almeno un numero
   - Deve contenere almeno un carattere speciale

4. Reinserisci la stessa password nel campo **{{t:settings.personal.changePassword.confirmPasswordLabel}}**.
5. Fai clic sul pulsante **{{t:settings.personal.changePassword.submit}}**.

![Modulo di cambio password](/assets/images/user-guide/78_profiles_change_form.png)
*(Figura 78: Modulo Cambia password - requisiti di sicurezza visibili)*

> **Suggerimento**: Usa combinazioni casuali quando crei una password sicura.

---

## 2.8 Archiviazione

La sezione Archiviazione consente di gestire le aree fisiche in cui verranno archiviati i dati di backup.

### 2.8.1 Aggiunta di un'area di archiviazione

![Procedura guidata di creazione area di archiviazione](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(Video: Aggiunta di una posizione di archiviazione)*

1. Vai alla scheda **{{t:common.navigation.storage}}** dal menu di sinistra.
2. Fai clic sul pulsante **{{t:resources.storage.createStorage}}**.

![Pulsante Aggiungi archiviazione](/assets/images/user-guide/79_storage_add_button.png)
*(Figura 79: Pagina di gestione archiviazione - pulsante "Aggiungi archiviazione")*

3. Compila il modulo:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: Inserisci un nome descrittivo
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: Seleziona (es. s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: Aggiungi una descrizione opzionale
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: Opzionale
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: Flag rclone (es. --transfers 4)

![Modulo di creazione area di archiviazione](/assets/images/user-guide/80_storage_form.png)
*(Figura 80: Modulo Aggiungi archiviazione - nome, provider, descrizione e parametri)*

4. Fai clic sul pulsante **{{t:common.actions.create}}**.

> **Suggerimento**: I parametri aggiuntivi accettano flag rclone per ottimizzare le prestazioni dell'archiviazione.

---

## 2.9 Credenziali

La sezione Credenziali consente di gestire in modo sicuro le informazioni di accesso ai tuoi repository.

### 2.9.1 Modifica delle credenziali

![Procedura guidata di modifica credenziali](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(Video: Modifica delle credenziali)*

1. Vai alla scheda **{{t:common.navigation.credentials}}** dal menu di sinistra.
2. Seleziona il record che vuoi modificare.
3. Fai clic sul pulsante **{{t:common.actions.edit}}**.

![Elenco credenziali](/assets/images/user-guide/81_credentials.png)
*(Figura 81: Pagina Credenziali - nomi dei repository, team e pulsanti di gestione)*

4. Cambia il **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}** se necessario.
5. Salva con il pulsante **{{t:common.save}}**.

![Modulo di modifica credenziali](/assets/images/user-guide/82_credentials_form.png)
*(Figura 82: Modulo Modifica nome repository - campi di configurazione vault)*

> **Suggerimento**: Le credenziali sono memorizzate in modo crittografato e vengono decrittografate solo durante il deploy.

### 2.9.2 Traccia delle credenziali

![Procedura guidata di traccia delle credenziali](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(Video: Visualizzazione della cronologia audit delle credenziali)*

1. Seleziona il record che vuoi tracciare.
2. Fai clic sul pulsante **{{t:common.actions.trace}}**.

![Pulsante Traccia](/assets/images/user-guide/83_credentials_trace_button.png)
*(Figura 83: Pulsante "Trace" nella tabella Credenziali)*

3. Esamina la cronologia audit.
4. Seleziona il formato dal pulsante **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** o **{{t:common.exportJSON}}**.

![Cronologia audit delle credenziali](/assets/images/user-guide/84_credentials_list_export.png)
*(Figura 84: Elenco credenziali - Opzioni di esportazione)*

> **Suggerimento**: La funzione di traccia fornisce il monitoraggio dell'utilizzo delle credenziali a scopo di audit della sicurezza.

### 2.9.3 Eliminazione delle credenziali

![Procedura guidata di eliminazione credenziali](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(Video: Eliminazione di una credenziale)*

1. Seleziona il record che vuoi eliminare.
2. Fai clic sul pulsante rosso **{{t:common.delete}}**.

![Pulsante Elimina](/assets/images/user-guide/85_credentials_delete.png)
*(Figura 85: Pulsante rosso "Delete" nella pagina Credenziali)*

3. Fai clic sul pulsante **{{t:common.delete}}** nella finestra di conferma.

![Conferma eliminazione](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(Figura 86: Finestra di dialogo di conferma eliminazione - avviso azione irreversibile)*

> **Avvertenza**: Prima di eliminare, assicurati che la credenziale non sia in uso su altre macchine o in altre operazioni. Assicurati di avere un backup delle credenziali critiche prima di eliminarle.

---

## 2.10 Coda

La sezione Coda consente di monitorare le operazioni in attesa e completate nel sistema.

### 2.10.1 Operazioni sulla coda

![Procedura guidata delle operazioni sulla coda](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(Video: Gestione delle operazioni sulla coda)*

1. Fai clic sulla scheda **{{t:common.navigation.queue}}** dal menu di sinistra.

![Pagina Coda](/assets/images/user-guide/87_queue_button.png)
*(Figura 87: Pagina Coda - opzioni di filtraggio e schede di stato)*

2. Per filtrare gli elementi della coda:
   - Usa i filtri **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}** e **{{t:queue.trace.bridge}}**
   - Specifica **{{t:system.audit.filters.dateRange}}**
   - Spunta l'opzione **{{t:queue.filters.onlyStale}}**

3. Visualizza i dettagli nelle schede di stato:
   - **{{t:queue.statusActive}}**: Attività in elaborazione
   - **{{t:queue.statusCompleted}}**: Attività completate con successo
   - **{{t:queue.statusCancelled}}**: Attività annullate
   - **{{t:queue.statusFailed}}**: Attività non riuscite

4. Seleziona un formato dal pulsante **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** o **{{t:common.exportJSON}}**.

![Esportazione coda](/assets/images/user-guide/88_queue_export.png)
*(Figura 88: Elenco coda - Opzioni di esportazione)*

> **Suggerimento**: L'opzione "{{t:queue.filters.onlyStale}}" aiuta a trovare le attività in elaborazione da molto tempo. Esporta regolarmente la cronologia della coda per analizzare le tendenze di esecuzione delle attività.

---

## 2.11 Audit

La sezione Audit mantiene i registri di tutte le operazioni eseguite nel sistema.

### 2.11.1 Record di audit

![Procedura guidata dei record di audit](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(Video: Visualizzazione dei record di audit del sistema)*

1. Fai clic sulla scheda **{{t:common.navigation.audit}}** dal menu di sinistra.

![Elenco audit](/assets/images/user-guide/89_audit_list.png)
*(Figura 89: Pagina Audit - registro dettagliato di tutte le operazioni di sistema)*

2. Filtra i record di audit:
   - **Intervallo di date**: Filtra per un periodo specifico
   - **Tipo di entità**: Filtra per Request, Machine, Queue, ecc.
   - **Ricerca**: Esegui una ricerca testuale

3. Esamina le informazioni per ciascun record:
   - **Timestamp**: Data e ora dell'operazione
   - **Action**: Tipo di operazione (Creazione, Modifica, Eliminazione, ecc.)
   - **Entity Type**: Tipo di oggetto interessato
   - **Entity Name**: Identificatore dell'oggetto specifico
   - **User**: Utente che ha eseguito l'operazione
   - **Details**: Informazioni aggiuntive sull'operazione

4. Seleziona un formato dal pulsante **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** o **{{t:common.exportJSON}}**.

![Esportazione audit](/assets/images/user-guide/90_audit_export.png)
*(Figura 90: Esportazione record di audit - opzioni CSV e JSON)*

> **Suggerimento**: Il record di audit è fondamentale per monitorare tutte le attività di sistema a fini di sicurezza e conformità. Esporta regolarmente il record di audit e conservalo in un luogo sicuro.

---

**© 2025 Rediacc Platform - Tutti i diritti riservati.**
