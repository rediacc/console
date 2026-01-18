---
title: Webanwendung
description: Verständnis der Webanwendungsarchitektur und Bereitstellung mit Rediacc
category: Core Concepts
order: 1
language: de
---

# Rediacc-Plattform Benutzerhandbuch

## Überblick

**Rediacc** ist eine Cloud-Plattform, die KI-gestützte Backup-Dienste anbietet.

Dieses Handbuch beschreibt die grundlegende Verwendung der Weboberfläche unter [https://www.rediacc.com/](https://www.rediacc.com/).

### Zweck dieses Handbuchs

- Neuen Benutzern helfen, sich schnell an die Plattform anzupassen
- Grundfunktionen (Ressourcenverwaltung, Backup) Schritt für Schritt erklären

---

## 1. Kontoerstellung und Anmeldung

### 1.1 Registrierung

Um die Rediacc-Plattform nutzen zu können, müssen Sie zunächst ein Konto erstellen.

![Rediacc Anmeldeseite - immer verfügbare Infrastruktur](/assets/images/UserGuideEng/01_login.png)
*(Abbildung 1: Hauptanmeldeseite mit den wichtigsten Funktionen der Rediacc-Plattform)*

1. Navigieren Sie in Ihrem Browser zu [https://www.rediacc.com/](https://www.rediacc.com/).
2. Klicken Sie auf die Schaltfläche **{{t:auth.login.signIn}}** in der oberen rechten Ecke der Seite.
3. Wählen Sie **Get Started** für kostenlosen Zugang oder **Request Demo** für eine Demonstration.

> **Tipp**: Sie können ein kostenloses Konto ohne Kreditkarte erstellen. Beinhaltet 10 CPU-Kerne und unbegrenzte Teams.

![Rediacc Anmeldeformular - E-Mail und Passwort Felder](/assets/images/UserGuideEng/02_register.png)
*(Abbildung 2: Anmeldebildschirm für bestehende Benutzer)*

4. Falls Sie kein Konto haben, klicken Sie auf den Link **{{t:auth.login.register}}**, um ein neues Konto zu erstellen.

5. Füllen Sie die folgenden Informationen im Formular aus:
   - **{{t:auth.registration.organizationName}}**: Geben Sie Ihren Organisationsnamen ein
   - **{{t:auth.login.email}}**: Geben Sie eine gültige E-Mail-Adresse ein
   - **{{t:auth.login.password}}**: Erstellen Sie ein Passwort mit mindestens 8 Zeichen
   - **{{t:auth.registration.passwordConfirm}}**: Geben Sie das Passwort erneut ein

![Konto erstellen Modal - Registrierung, Verifizierung und Abschluss](/assets/images/UserGuideEng/03_create_account.png)
*(Abbildung 3: Schritt-für-Schritt-Formular für neue Benutzerregistrierung - Registrieren > Verifizieren > Abschließen)*

6. Aktivieren Sie das Kontrollkästchen, um die Nutzungsbedingungen und Datenschutzrichtlinie zu akzeptieren.
7. Klicken Sie auf die Schaltfläche **{{t:auth.registration.createAccount}}**.

> **Tipp**: Das Passwort muss mindestens 8 Zeichen lang und stark sein. Alle Felder sind erforderlich.

8. Geben Sie den 6-stelligen Verifizierungscode, der an Ihre E-Mail gesendet wurde, der Reihe nach in die Felder ein.
9. Klicken Sie auf die Schaltfläche **{{t:auth.registration.verifyAccount}}**.

![Verifizierungscode-Eingabe - 6-stelliger Aktivierungscode](/assets/images/UserGuideEng/04_verification_code.png)
*(Abbildung 4: Fenster zur Eingabe des an den Administrator gesendeten Aktivierungscodes)*

> **Tipp**: Der Verifizierungscode ist zeitlich begrenzt gültig. Falls Sie den Code nicht erhalten, überprüfen Sie Ihren Spam-Ordner.

---

### 1.2 Anmelden

Nach der Kontoerstellung können Sie sich bei der Plattform anmelden.

1. Füllen Sie das Feld **{{t:auth.login.email}}** aus (erforderlich wenn eine rote Warnung erscheint).
2. Füllen Sie das Feld **{{t:auth.login.password}}** aus.
3. Klicken Sie auf die Schaltfläche **{{t:auth.login.signIn}}**.

![Anmeldeformular - Pflichtfelder mit Fehlerwarnung](/assets/images/UserGuideEng/05_sign_in.png)
*(Abbildung 5: Anmeldeformular - Fehlermeldungen werden mit rotem Rahmen markiert)*

> **Tipp**: Wenn die Fehlermeldung "Dieses Feld ist erforderlich" lautet, füllen Sie die leeren Felder aus. Kontaktieren Sie den Administrator bei vergessenem Passwort.

4. Nach erfolgreicher Anmeldung werden Sie zum **{{t:common.navigation.dashboard}}**-Bildschirm weitergeleitet.

![Rediacc Dashboard - Maschinenliste und Sidebar-Menü](/assets/images/UserGuideEng/06_dashboard.png)
*(Abbildung 6: Haupt-Dashboard nach erfolgreicher Anmeldung - Organisation, Maschinen und Einstellungen Menüs in der linken Seitenleiste)*

> **Tipp**: Das Dashboard aktualisiert sich automatisch. Sie können die Seite mit F5 für aktuelle Informationen aktualisieren.

---

## 2. Schnittstellenübersicht

Nach der Anmeldung besteht der Bildschirm aus diesen Hauptbereichen:

- **{{t:common.navigation.organization}}**: Benutzer, Teams und Zugriffskontrolle
- **{{t:common.navigation.machines}}**: Server- und Repository-Verwaltung
- **{{t:common.navigation.settings}}**: Profil- und Systemeinstellungen
- **{{t:common.navigation.storage}}**: Speicherbereichsverwaltung
- **{{t:common.navigation.credentials}}**: Zugangsdaten
- **{{t:common.navigation.queue}}**: Auftragswarteschlangenverwaltung
- **{{t:common.navigation.audit}}**: System-Prüfprotokolle

---

## 2.1 Organisation - Benutzer

Die Benutzerverwaltung ermöglicht Ihnen, den Zugang zur Plattform für Personen in Ihrer Organisation zu kontrollieren.

### 2.1.1 Benutzer hinzufügen

1. Klicken Sie in der linken Seitenleiste auf **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**.
2. Zeigen Sie die Liste aller Benutzer im Tabellenformat an.
3. Jede Benutzerzeile zeigt E-Mail, Status ({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), Berechtigungsgruppe und letzte Aktivitätszeit an.

![Benutzerverwaltungsseite - Liste aktiver Benutzer](/assets/images/UserGuideEng/07_users.png)
*(Abbildung 7: Benutzerbereich unter Organisation - alle Benutzerinformationen werden angezeigt)*

4. Klicken Sie auf das **"+"** Symbol in der oberen rechten Ecke.
5. Klicken Sie auf die Schaltfläche **{{t:organization.users.modals.createTitle}}** und füllen Sie das Formular aus:
   - **{{t:organization.users.form.emailLabel}}**: Geben Sie die E-Mail-Adresse des Benutzers ein
   - **{{t:organization.users.form.passwordLabel}}**: Geben Sie ein temporäres Passwort ein

![Benutzer-Erstellungsmodal - E-Mail und Passwort Felder](/assets/images/UserGuideEng/08_user_add.png)
*(Abbildung 8: Modal-Fenster zum Hinzufügen eines neuen Benutzers - einfaches und schnelles Benutzer-Erstellungsformular)*

6. Klicken Sie auf die Schaltfläche **{{t:common.actions.create}}**.

> **Tipp**: Anmeldedaten sollten dem erstellten Benutzer sicher mitgeteilt werden. Eine Passwortänderung bei der ersten Anmeldung wird empfohlen.

![Benutzerliste - vollständige Tabellenansicht mit drei Benutzern](/assets/images/UserGuideEng/09_user_list.png)
*(Abbildung 9: Alle aktiven und inaktiven Benutzer auf der Benutzerverwaltungsseite)*

> **Tipp**: Die Seite zeigt automatisch 20 Einträge an. Verwenden Sie die Seitennavigation für weitere Einträge.

### 2.1.2 Benutzerberechtigungen zuweisen

Sie können Zugriffsrechte verwalten, indem Sie Benutzern bestimmte Berechtigungsgruppen zuweisen.

1. Wählen Sie einen Benutzer aus der Registerkarte **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**.
2. Klicken Sie auf das Schild-Symbol in der Aktionsspalte (**Berechtigungen**).

![Berechtigungsverwaltung - Schild-, Zahnrad- und Löschen-Symbole](/assets/images/UserGuideEng/10_users_permissions.png)
*(Abbildung 10: Symbolanzeige der Benutzeraktionen - jedes Symbol repräsentiert eine andere Aktion)*

3. Wählen Sie eine **{{t:organization.users.modals.permissionGroupLabel}}** aus dem Formular.
4. Die Anzahl der Benutzer und Berechtigungen in der Gruppe wird neben dem Benutzer angezeigt.
5. Klicken Sie auf die Schaltfläche **{{t:organization.users.modals.assignTitle}}**, um die Änderungen zu speichern.

![Berechtigungszuweisungsmodal - Administratorengruppe](/assets/images/UserGuideEng/11_user_permissions_form.png)
*(Abbildung 11: Modal zur Zuweisung einer Berechtigungsgruppe an den ausgewählten Benutzer - Dropdown mit verfügbaren Gruppen)*

> **Tipp**: Einige Berechtigungsgruppen sind vom System festgelegt und können nicht geändert werden.

### 2.1.3 Benutzeraktivierung

Sie können deaktivierte Benutzer reaktivieren.

1. Finden Sie den Benutzer mit inaktivem Status in der **Benutzer**-Liste.
2. Klicken Sie auf das rote Symbol in der Aktionsspalte.

![Benutzeraktivierung - "Aktivieren" Tooltip-Ansicht](/assets/images/UserGuideEng/12_users_activation.png)
*(Abbildung 12: Aktivieren eines inaktiven Benutzers)*

3. Klicken Sie auf die Schaltfläche **{{t:common.general.yes}}** im Bestätigungsfenster.

![Aktivierungsbestätigungs-Modal](/assets/images/UserGuideEng/13_users_activation_confirm.png)
*(Abbildung 13: Modal-Fenster zur Bestätigung der Benutzeraktivierung)*

> **Tipp**: Diese Aktion ist umkehrbar. Sie können den Benutzer auf die gleiche Weise deaktivieren.

### 2.1.4 Benutzer-Trace

Sie können die Trace-Funktion verwenden, um Benutzeraktivitäten zu überwachen.

1. Wählen Sie einen Benutzer und klicken Sie auf das Zahnrad-Symbol in der Aktionsspalte.
2. Klicken Sie auf die Option **{{t:common.actions.trace}}**, um die Aktivitätshistorie des Benutzers zu öffnen.

![Benutzer-Trace - "Trace" Tooltip mit Aktionsschaltfläche](/assets/images/UserGuideEng/14_users_trace.png)
*(Abbildung 14: Benutzeraktivitäts-Trace-Option)*

3. Die vergangenen Aktivitäten des Benutzers werden auf dem geöffneten Bildschirm aufgelistet.
4. Statistiken werden oben angezeigt: Gesamteinträge, Angezeigte Einträge, Letzte Aktivität.
5. Klicken Sie auf die Schaltfläche **{{t:common.actions.export}}** und wählen Sie das Format: **{{t:common.exportCSV}}** oder **{{t:common.exportJSON}}**.

![Audit-Historie - Export-Optionen](/assets/images/UserGuideEng/15_user_trace_export.png)
*(Abbildung 15: Vollständige Aktivitätshistorie des Benutzers - Statistiken, Details und Export-Optionen)*

> **Tipp**: Exportieren Sie regelmäßig Audit-Daten, um Sicherheits- und Compliance-Aufzeichnungen zu führen. Das CSV-Format kann in Excel geöffnet werden.

---

## 2.2 Organisation - Teams

Teams ermöglichen es Ihnen, Benutzer zu gruppieren und Massenzugriff auf Ressourcen zu gewähren.

### 2.2.1 Teams erstellen

1. Gehen Sie zur Registerkarte **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}**.
2. Klicken Sie auf die Schaltfläche **"+"**.
3. Geben Sie Ihren Teamnamen in das Feld **{{t:common.vaultEditor.fields.TEAM.name.label}}** ein.
4. Füllen Sie die Felder **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** und **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** im Abschnitt **{{t:common.vaultEditor.vaultConfiguration}}** aus.

![Neues Team-Erstellungsformular - Teamname und SSH-Schlüssel](/assets/images/UserGuideEng/16_teams_create.png)
*(Abbildung 16: Erstellen eines neuen Teams innerhalb von "Private Team")*

5. Klicken Sie auf die Schaltfläche **{{t:common.actions.create}}**, um das Team zu speichern.

> **Tipp**: SSH-Schlüssel sind für die Bridge-SSH-Authentifizierung erforderlich. Wenn Sie eine Warnung über fehlende Schlüssel erhalten, stellen Sie beide Schlüssel bereit.

### 2.2.2 Team bearbeiten

1. Klicken Sie auf das Stift-Symbol neben dem Team, das Sie bearbeiten möchten.
2. Ändern Sie bei Bedarf den Teamnamen im Feld **{{t:common.vaultEditor.fields.TEAM.name.label}}**.
3. Aktualisieren Sie die SSH-Schlüssel im Abschnitt **{{t:common.vaultEditor.vaultConfiguration}}**.
4. Klicken Sie auf die Schaltfläche **{{t:common.save}}**, um Änderungen anzuwenden.

![Team-Bearbeitungsformular - blaue Info-Nachricht](/assets/images/UserGuideEng/17_teams_edit_form.png)
*(Abbildung 17: Bearbeiten der Informationen eines bestehenden Teams)*

> **Tipp**: Die Team-Konfiguration wird für die Organisationsstruktur verwendet. Änderungen gelten für alle Teammitglieder.

### 2.2.3 Teammitglieder-Verwaltung

1. Wählen Sie ein Team und klicken Sie auf das Benutzer-Symbol.
2. Sehen Sie bereits zum Team zugewiesene Mitglieder im Tab **{{t:organization.teams.manageMembers.currentTab}}**.
3. Wechseln Sie zum Tab **{{t:organization.teams.manageMembers.addTab}}**.
4. Geben Sie eine E-Mail-Adresse ein oder wählen Sie einen Benutzer aus dem Dropdown.
5. Klicken Sie auf die Schaltfläche **"+"**, um das Mitglied zum Team hinzuzufügen.

![Teammitglieder-Verwaltungsformular - "Aktuelle Mitglieder" und "Mitglied hinzufügen" Registerkarten](/assets/images/UserGuideEng/18_teams_members_form.png)
*(Abbildung 18: Teammitglieder-Verwaltungspanel)*

> **Tipp**: Sie können dasselbe Mitglied mehreren Teams zuweisen.

### 2.2.4 Team-Trace

1. Wählen Sie das Team, das Sie verfolgen möchten.
2. Klicken Sie auf das Uhr-/Historie-Symbol.
3. Überprüfen Sie Gesamteinträge, Angezeigte Einträge und Letzte Aktivität im Fenster **{{t:resources.audit.title}}**.
4. Klicken Sie auf die Schaltfläche **{{t:common.actions.export}}**, um im Format {{t:common.exportCSV}} oder {{t:common.exportJSON}} zu exportieren.

![Audit-Historie-Modal - DataBassTeam Team](/assets/images/UserGuideEng/19_teams_trace.png)
*(Abbildung 19: Team-Audit-Historie anzeigen)*

> **Tipp**: Die Audit-Historie ist wichtig für Compliance- und Sicherheitskontrolle.

### 2.2.5 Team löschen

1. Klicken Sie auf das Papierkorb-Symbol (rot) neben dem Team, das Sie löschen möchten.
2. Überprüfen Sie, ob der Teamname im Bestätigungsdialog korrekt ist.
3. Klicken Sie auf die Schaltfläche **{{t:common.general.yes}}**.

![Team-Löschbestätigungsdialog](/assets/images/UserGuideEng/20_teams_delete.png)
*(Abbildung 20: Team-Löschbestätigung)*

> **Warnung**: Die Team-Löschung ist unwiderruflich. Überprüfen Sie, ob wichtige Daten im Team vorhanden sind, bevor Sie löschen.

---

## 2.3 Organisation - Zugriffskontrolle

Die Zugriffskontrolle ermöglicht es Ihnen, Benutzerberechtigungen zentral zu verwalten, indem Sie Berechtigungsgruppen erstellen.

### 2.3.1 Berechtigungsgruppen erstellen

1. Gehen Sie zur Registerkarte **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}**.
2. Klicken Sie auf die Schaltfläche **"+"**.
3. Geben Sie einen aussagekräftigen Namen in das Feld **{{t:organization.access.modals.groupPlaceholder}}** ein.
4. Klicken Sie auf die Schaltfläche **{{t:common.actions.confirm}}**, um die Gruppe zu erstellen.

![Berechtigungsgruppen-Erstellungsformular](/assets/images/UserGuideEng/21_create_access.png)
*(Abbildung 21: Erstellen einer neuen Berechtigungsgruppe)*

> **Tipp**: Berechtigungsgruppen werden verwendet, um Benutzer mit ähnlichen Berechtigungen zu organisieren. Halten Sie Gruppennamen beschreibend (z.B. "Admin", "Nur Lesen", "Repository-Manager").

### 2.3.2 Berechtigungsverwaltung

1. Wählen Sie eine Berechtigungsgruppe und klicken Sie auf die Option **{{t:organization.access.modals.managePermissionsTitle}}**.
2. Sehen Sie die Zugriffsrechte der Gruppe im Tab **{{t:organization.access.modals.currentPermissionsTab}}**.
3. Sie können eine Berechtigung widerrufen, indem Sie auf die rote Schaltfläche **{{t:common.delete}}** neben jeder Aktion klicken.
4. Klicken Sie auf den Tab **{{t:organization.access.modals.addPermissionsTab}}**, um neue Berechtigungen zur Gruppe hinzuzufügen.

![Berechtigungsverwaltungs-Panel - Liste zugewiesener Berechtigungen](/assets/images/UserGuideEng/22_access_permission.png)
*(Abbildung 22: Berechtigungen für Berechtigungsgruppe verwalten)*

> **Tipp**: Gewähren Sie Berechtigungen nach dem Prinzip der geringsten Privilegien. Überprüfen und entfernen Sie regelmäßig unnötige Berechtigungen.

---

## 2.4 Maschinen

Der Maschinenbereich ermöglicht es Ihnen, Ihre Server und Repository-Ressourcen zu verwalten.

### 2.4.1 Maschinen hinzufügen

1. Gehen Sie im linken Menü zur Registerkarte **{{t:common.navigation.machines}}**.
2. Klicken Sie auf die Schaltfläche **{{t:machines.createMachine}}** in der oberen rechten Ecke.

![Maschinen-Seite - "Maschine hinzufügen" Schaltfläche](/assets/images/UserGuideEng/23_machines_add.png)
*(Abbildung 23: Hauptseite der Maschinenverwaltung)*

3. Füllen Sie das Formular aus:
   - **{{t:machines.machineName}}**: Geben Sie einen eindeutigen Namen ein (z.B. "server-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: Geben Sie die Maschinen-IP-Adresse ein (z.B. 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: Geben Sie das Speicherverzeichnis an (z.B. /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: Geben Sie den SSH-Benutzernamen ein
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: Geben Sie die Portnummer ein (Standard: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: Geben Sie das Passwort ein (optional)

![Maschinen-Hinzufügen-Formular - alle Felder](/assets/images/UserGuideEng/24_machine_create.png)
*(Abbildung 24: Neues Maschinen-Hinzufügen-Formular - Maschinenname, Netzwerkeinstellungen, SSH-Anmeldedaten)*

4. Klicken Sie auf die Schaltfläche **{{t:common.vaultEditor.testConnection.button}}**, um die Verbindung zu überprüfen.
5. Nach erfolgreichem Test klicken Sie auf die Schaltfläche **{{t:common.actions.create}}**.

> **Tipp**: Wenn die Option "Setup nach Maschinenerstellung automatisch starten" aktiviert ist, führt die Maschine automatisch zusätzliche Setup-Schritte durch.

![Maschinenerstellung abgeschlossen - Aufgabenverfolgungsfenster](/assets/images/UserGuideEng/25_machine_create_complete.png)
*(Abbildung 25: Aufgabenverfolgungsfenster nach erfolgreicher Maschinenerstellung)*

6. Beobachten Sie die Phasen: **Assigned** → **Processing** → **{{t:queue.statusCompleted}}**
7. Klicken Sie auf die Schaltfläche **{{t:common.actions.close}}**, um den Vorgang zu beenden.

> **Tipp**: Klicken Sie auf die Schaltfläche "{{t:common.actions.refresh}}", um den neuesten Status manuell zu überprüfen.

### 2.4.2 Konnektivitätstest

Sie können den Verbindungsstatus vorhandener Maschinen überprüfen.

1. Klicken Sie auf die Schaltfläche **{{t:machines.connectivityTest}}**.

![Konnektivitätstest-Schaltfläche](/assets/images/UserGuideEng/26_connectivity_test_button.png)
*(Abbildung 26: Konnektivitätstest-Schaltfläche in der Maschinenaktions-Symbolleiste)*

2. Sehen Sie die Liste der zu testenden Maschinen.
3. Klicken Sie auf die Schaltfläche **{{t:machines.runTest}}**.
4. Erfolgreiche Ergebnisse werden in Grün, Fehler in Rot angezeigt.

![Konnektivitätstest-Formular - Maschinenliste](/assets/images/UserGuideEng/27_connectivity_test_form.png)
*(Abbildung 27: Konnektivitätstest-Formular - Ping-Funktion für ausgewählte Maschinen)*

> **Tipp**: Wenn der Test fehlschlägt, überprüfen Sie die Maschinen-IP-Adresse und SSH-Einstellungen.

### 2.4.3 Maschinenliste aktualisieren

Klicken Sie auf die Schaltfläche **{{t:common.actions.refresh}}**, um die Maschinenliste zu aktualisieren.

![Aktualisieren-Schaltfläche](/assets/images/UserGuideEng/28_refresh.png)
*(Abbildung 28: Aktualisieren-Schaltfläche in der Maschinenaktions-Symbolleiste)*

### 2.4.4 Maschinendetails

1. Wählen Sie die Maschine, deren Details Sie sehen möchten.
2. Klicken Sie auf das Auge-Symbol (**Details anzeigen**).

![Details anzeigen Schaltfläche](/assets/images/UserGuideEng/29_view_details_button.png)
*(Abbildung 29: Auge-Symbol in der Maschinenaktionsspalte)*

3. Das Maschinendetail-Panel öffnet sich auf der rechten Seite:
   - **Hostname**: Maschinenname
   - **Uptime**: Laufzeit
   - **Betriebssystem**: OS und Version
   - **Kernel**: Kernel-Version
   - **CPU**: Prozessorinformationen
   - **Systemzeit**: Systemuhr

![Maschinendetail-Panel - Systeminformationen](/assets/images/UserGuideEng/30_machine_view_details.png)
*(Abbildung 30: Maschinendetail-Panel - Hostname, Uptime, OS, Kernel, CPU-Informationen)*

> **Tipp**: Überprüfen Sie diese Informationen regelmäßig, um OS-Kompatibilität und Ressourcenverfügbarkeit zu prüfen.

### 2.4.5 Maschine bearbeiten

1. Wählen Sie die Maschine, die Sie bearbeiten möchten.
2. Klicken Sie auf das Stift-Symbol (**{{t:common.actions.edit}}**).

![Bearbeiten-Schaltfläche](/assets/images/UserGuideEng/31_edit_button.png)
*(Abbildung 31: Stift-Symbol in der Maschinenaktionsspalte)*

3. Nehmen Sie die erforderlichen Änderungen vor.
4. Klicken Sie auf die Schaltfläche **{{t:common.vaultEditor.testConnection.button}}**.
5. Bei erfolgreicher Verbindung klicken Sie auf die Schaltfläche **{{t:common.save}}**.

![Maschinen-Bearbeitungsformular](/assets/images/UserGuideEng/32_edit_form.png)
*(Abbildung 32: Maschinen-Bearbeitungsformular - Maschinenname, Region und Vault-Konfiguration)*

> **Tipp**: Führen Sie nach Änderung kritischer Einstellungen immer "Verbindung testen" aus.

### 2.4.6 Maschinen-Trace

1. Wählen Sie die Maschine und klicken Sie auf das Uhr-Symbol (**{{t:common.actions.trace}}**).

![Trace-Schaltfläche](/assets/images/UserGuideEng/33_trace_button.png)
*(Abbildung 33: Uhr-Symbol in der Maschinenaktionsspalte)*

2. Überprüfen Sie Operationen im Audit-Historie-Fenster:
   - **{{t:resources.audit.action}}**: Art der durchgeführten Operation
   - **Details**: Geänderte Felder
   - **{{t:resources.audit.performedBy}}**: Benutzer, der die Aktion durchgeführt hat
   - **{{t:resources.audit.timestamp}}**: Datum und Uhrzeit

![Maschinen-Audit-Historie-Fenster](/assets/images/UserGuideEng/34_trace_list.png)
*(Abbildung 34: Audit-Historie - Liste aller Änderungen)*

> **Tipp**: Klicken Sie auf die Zeitstempel-Spalte, um Änderungen in chronologischer Reihenfolge anzuzeigen.

### 2.4.7 Maschine löschen

1. Wählen Sie die Maschine, die Sie löschen möchten.
2. Klicken Sie auf das Papierkorb-Symbol (**{{t:common.delete}}**).

![Löschen-Schaltfläche](/assets/images/UserGuideEng/35_delete_button.png)
*(Abbildung 35: Papierkorb-Symbol in der Maschinenaktionsspalte)*

3. Klicken Sie im Bestätigungsfenster auf die Schaltfläche **{{t:common.delete}}**.

![Maschinen-Löschbestätigungsfenster](/assets/images/UserGuideEng/36_delete_form.png)
*(Abbildung 36: "Sind Sie sicher, dass Sie diese Maschine löschen möchten?" Bestätigungsfenster)*

> **Warnung**: Wenn eine Maschine gelöscht wird, werden alle Repository-Definitionen darauf ebenfalls entfernt. Diese Aktion ist unwiderruflich.

### 2.4.8 Remote-Operationen

Sie können verschiedene Remote-Operationen auf Maschinen durchführen.

1. Wählen Sie die Maschine und klicken Sie auf die Schaltfläche **{{t:common.actions.remote}}**.
2. Sehen Sie Optionen im Dropdown-Menü:
   - **{{t:machines.runAction}}**: Funktion auf Maschine ausführen
   - **{{t:common.vaultEditor.testConnection.button}}**: Maschine anpingen

![Remote-Menü - Auf Server ausführen und Verbindung testen](/assets/images/UserGuideEng/37_remote_button.png)
*(Abbildung 37: Remote-Schaltfläche - Funktionsausführungsmenü auf ausgewählter Maschine)*

> **Tipp**: Verwenden Sie die Option "{{t:common.vaultEditor.testConnection.button}}", um zu überprüfen, ob die Maschine erreichbar ist, bevor Sie Funktionen ausführen.

#### Setup

1. Wählen Sie die Option **{{t:machines.runAction}}**.
2. Finden Sie die Funktion **setup** in der Liste **{{t:functions.availableFunctions}}**.
3. Klicken Sie auf den Funktionsnamen, um sie auszuwählen.

![Maschinenfunktionsliste - setup Funktion](/assets/images/UserGuideEng/38_server_setup.png)
*(Abbildung 38: Setup-Funktion - bereitet die Maschine mit erforderlichen Tools und Konfigurationen vor)*

> **Tipp**: Es wird empfohlen, die Funktion "setup" zuerst auszuführen, wenn Sie eine neue Maschine einrichten.

#### Verbindungsprüfung (Hello)

1. Wählen Sie **{{t:machines.runAction}}** > Funktion **hello**.
2. Klicken Sie auf die Schaltfläche **{{t:common.actions.addToQueue}}**.

![Hello-Funktionsauswahl](/assets/images/UserGuideEng/39_remote_hello.png)
*(Abbildung 39: Hello-Funktion - einfache Testfunktion, gibt Hostname zurück)*

3. Beobachten Sie die Ergebnisse im Aufgabenverfolgungsfenster.
4. Sehen Sie die Ausgabe der Maschine im Abschnitt **{{t:queue.trace.responseConsole}}**.

![Hello-Funktion abgeschlossen](/assets/images/UserGuideEng/40_remote_hello_complete.png)
*(Abbildung 40: Hello-Funktion erfolgreich abgeschlossen - Hostname-Antwort)*

> **Tipp**: Die Hello-Funktion ist ideal zur Überprüfung der Maschinenkonnektivität.

#### Erweiterte Operationen

1. Folgen Sie dem Pfad **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}**.
2. Sehen Sie verfügbare Funktionen: setup, hello, ping, ssh_test, uninstall
3. Wählen Sie die erforderliche Funktion und klicken Sie auf die Schaltfläche **{{t:common.actions.addToQueue}}**.

![Liste erweiterter Funktionen](/assets/images/UserGuideEng/41_remote_advanced.png)
*(Abbildung 41: Erweiterte Option - Liste erweiterter Funktionen)*

> **Tipp**: Stellen Sie sicher, dass das Maschinen-Setup abgeschlossen ist, bevor Sie erweiterte Funktionen verwenden.

#### Schneller Konnektivitätstest

![Remote-Menü - Verbindung testen](/assets/images/UserGuideEng/42_connectivity_test.png)
*(Abbildung 42: Verbindung testen Option aus Remote-Menü)*

> **Tipp**: Wenn die Maschine SSH- oder Netzwerkprobleme hat, können Sie mit diesem Test schnell Probleme identifizieren.

---

## 2.5 Repository-Erstellung und Operationen

Repositories sind die grundlegenden Einheiten, in denen Ihre Backup-Daten gespeichert werden.

### 2.5.1 Repositories erstellen

1. Wählen Sie eine Maschine aus der Registerkarte **{{t:common.navigation.machines}}**.
2. Klicken Sie auf die Schaltfläche **{{t:machines.createRepository}}** in der oberen rechten Ecke.

![Repository erstellen Schaltfläche](/assets/images/UserGuideEng/43_create_repo_add.png)
*(Abbildung 43: Maschinen-Repository-Verwaltungsbildschirm - Repository erstellen Schaltfläche)*

3. Füllen Sie das Formular aus:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: Geben Sie den Repository-Namen ein (z.B. postgresql)
   - **{{t:resources.repositories.size}}**: Geben Sie die Repository-Größe ein (z.B. 2GB)
   - **{{t:resources.repositories.repositoryGuid}}**: Sehen Sie die automatisch generierte Anmeldedaten
   - **{{t:resources.templates.selectTemplate}}**: Wählen Sie eine Vorlage (z.B. databases_postgresql)

![Repository-Erstellungsformular](/assets/images/UserGuideEng/44_repo_form.png)
*(Abbildung 44: Repository-Erstellungsformular - Repository-Name, Größe und Vorlagenauswahl)*

4. Klicken Sie auf die Schaltfläche **{{t:common.actions.create}}**.

> **Tipp**: Die Credential ID wird automatisch generiert, eine manuelle Änderung wird nicht empfohlen.

5. Beobachten Sie die Phasen im Aufgabenverfolgungsfenster: **Assigned** → **Processing** → **{{t:queue.statusCompleted}}**

![Repository-Erstellung abgeschlossen](/assets/images/UserGuideEng/45_repo_complete.png)
*(Abbildung 45: Repository-Erstellung in Warteschlange - Aufgabenüberwachung)*

6. Klicken Sie auf die Schaltfläche **{{t:common.actions.close}}**.

> **Tipp**: Die Aufgabe wird typischerweise innerhalb von 1-2 Minuten abgeschlossen.

![Repository-Liste](/assets/images/UserGuideEng/46_repo_list.png)
*(Abbildung 46: Erstelltes Repository erscheint in der Liste)*

### 2.5.2 Repository Fork

Sie können ein neues Repository erstellen, indem Sie ein vorhandenes kopieren.

1. Wählen Sie das Repository, das Sie kopieren möchten.
2. Klicken Sie auf das **fx** (Funktion) Menü.
3. Klicken Sie auf die Option **fork**.

![fx Menü - fork Option](/assets/images/UserGuideEng/47_fork_button.png)
*(Abbildung 47: fx Menü auf der rechten Seite - Repository-Operationen)*

4. Geben Sie ein neues Tag in das Feld **{{t:functions.functions.fork.params.tag.label}}** ein (z.B. 2025-12-06-20-37-08).
5. Klicken Sie auf die Schaltfläche **{{t:common.actions.addToQueue}}**.

![Fork-Konfigurationsformular](/assets/images/UserGuideEng/48_fork_form.png)
*(Abbildung 48: Neues Tag für das Repository im Fork-Vorgang angeben)*

6. Warten Sie auf die Nachricht **{{t:queue.statusCompleted}}** und klicken Sie auf die Schaltfläche **{{t:common.actions.close}}**.

![Fork abgeschlossen](/assets/images/UserGuideEng/49_repo_completed.png)
*(Abbildung 49: Fork-Vorgang erfolgreich abgeschlossen)*

> **Tipp**: Das Erstellen von Tags im Standard-Datum-Zeit-Format ist eine gute Praxis. Der Fork-Vorgang wirkt sich nicht auf das ursprüngliche Repository aus.

### 2.5.3 Repository Up

Um das Repository zu aktivieren:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **up**.

![Up-Operation](/assets/images/UserGuideEng/50_repo_up.png)
*(Abbildung 50: "up" Option aus fx Menü - Repository starten)*

2. Warten Sie auf die Nachricht **{{t:queue.statusCompleted}}**.

![Up abgeschlossen](/assets/images/UserGuideEng/51_repo_up_complete.png)
*(Abbildung 51: Repository-Start abgeschlossen)*

> **Tipp**: Die "Up"-Operation startet die definierten Docker-Dienste des Repositories.

### 2.5.4 Repository Down

Um ein aktives Repository zu stoppen:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **down**.

![Down-Operation](/assets/images/UserGuideEng/52_down_button.png)
*(Abbildung 52: "down" Option aus fx Menü - Repository herunterfahren)*

2. Warten Sie auf die Nachricht **{{t:queue.statusCompleted}}**.

![Down abgeschlossen](/assets/images/UserGuideEng/53_down_completed.png)
*(Abbildung 53: Repository-Herunterfahren abgeschlossen)*

> **Tipp**: Die "Down"-Operation fährt das Repository sicher herunter. Es gehen keine Daten verloren, nur Dienste werden gestoppt.

### 2.5.5 Deploy

Um das Repository an einen anderen Ort bereitzustellen:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **deploy**.

![Deploy-Operation](/assets/images/UserGuideEng/54_deploy_button.png)
*(Abbildung 54: "deploy" Option aus fx Menü)*

2. Geben Sie die bereitzustellende Version in das Feld **{{t:functions.functions.fork.params.tag.label}}** ein.
3. Wählen Sie Zielmaschinen im Feld **{{t:functions.functions.backup_deploy.params.machines.label}}**.
4. Aktivieren Sie die Option **{{t:functions.checkboxOptions.overrideExistingFile}}** (falls zutreffend).
5. Klicken Sie auf die Schaltfläche **{{t:common.actions.addToQueue}}**.

![Deploy-Formular](/assets/images/UserGuideEng/55_deploy_form.png)
*(Abbildung 55: Deploy-Operation konfigurieren - Tag, Zielmaschinen und Optionen)*

6. Warten Sie auf die Nachricht **{{t:queue.statusCompleted}}**.

![Deploy abgeschlossen](/assets/images/UserGuideEng/56_deploy_completed.png)
*(Abbildung 56: Repository-Bereitstellung abgeschlossen)*

> **Tipp**: Nach Abschluss der Deploy-Operation können Sie den "up"-Befehl ausführen, um das Repository auf Zielmaschinen zu starten.

### 2.5.6 Backup

Um das Repository zu sichern:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **backup**.

![Backup-Operation](/assets/images/UserGuideEng/57_backup_button.png)
*(Abbildung 57: "backup" Option aus fx Menü)*

2. Füllen Sie das Formular aus:
   - **{{t:functions.functions.fork.params.tag.label}}**: Geben Sie einen beschreibenden Namen ein (z.B. backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}**: Wählen Sie den Backup-Speicherort
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: Aktivieren oder deaktivieren Sie die Option
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: Überprüfen Sie die Einstellung

![Backup-Formular](/assets/images/UserGuideEng/58_backup_form.png)
*(Abbildung 58: Backup-Konfigurationsformular - Ziel, Dateiname und Optionen)*

3. Klicken Sie auf die Schaltfläche **{{t:common.actions.addToQueue}}**.

> **Tipp**: Verwenden Sie einen beschreibenden Namen für das Backup-Tag. Erwägen Sie die Aktivierung von Checkpoint für große Repositories.

4. Warten Sie auf die Nachricht **{{t:queue.statusCompleted}}**.

![Backup abgeschlossen](/assets/images/UserGuideEng/59_backup_completed.png)
*(Abbildung 59: Backup-Aufgabe erfolgreich abgeschlossen)*

> **Tipp**: Warten Sie geduldig, bis der Status "Abgeschlossen" erreicht ist; große Backups können mehrere Minuten dauern.

### 2.5.7 Vorlagenanwendung

Um eine neue Vorlage auf das Repository anzuwenden:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **Vorlagen**.

![Vorlagen-Operation](/assets/images/UserGuideEng/60_templates_button.png)
*(Abbildung 60: "Vorlagen" Option aus fx Menü)*

2. Filtern Sie Vorlagen durch Eingabe im Suchfeld.
3. Klicken Sie auf die gewünschte Vorlage, um sie auszuwählen (ausgewählte Vorlage ist mit fettem Rahmen hervorgehoben).
4. Klicken Sie auf die Schaltfläche **{{t:common.actions.addToQueue}}**.

![Vorlagenauswahlformular](/assets/images/UserGuideEng/61_templates_form.png)
*(Abbildung 61: Suchen und Auswählen verfügbarer Vorlagen)*

> **Tipp**: Verwenden Sie das Suchfeld, um schnell Vorlagen zu finden. Verwenden Sie "{{t:common.viewDetails}}", um mehr über Vorlagenfunktionen zu erfahren.

5. Warten Sie auf die Nachricht **{{t:queue.statusCompleted}}**.

![Vorlage angewendet](/assets/images/UserGuideEng/62_templates_completed.png)
*(Abbildung 62: Vorlagenanwendung erfolgreich abgeschlossen)*

### 2.5.8 Unmount

Um das Repository zu trennen:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}**.

![Unmount-Operation](/assets/images/UserGuideEng/63_unmount_button.png)
*(Abbildung 63: "Unmount" Option im erweiterten Menü)*

2. Warten Sie auf die Nachricht **{{t:queue.statusCompleted}}**.

![Unmount abgeschlossen](/assets/images/UserGuideEng/64_unmount_completed.png)
*(Abbildung 64: Unmount-Operation abgeschlossen)*

> **Tipp**: Stellen Sie sicher, dass keine aktiven Operationen auf dem Repository laufen, bevor Sie den Unmount durchführen. Nach dem Unmount wird das Repository unzugänglich.

### 2.5.9 Erweitern

Um die Repository-Größe zu erhöhen:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}**.

![Erweitern-Operation](/assets/images/UserGuideEng/65_expand_button.png)
*(Abbildung 65: "Erweitern" Option im erweiterten Menü)*

2. Geben Sie die gewünschte Größe in das Feld **{{t:functions.functions.repository_expand.params.size.label}}** ein.
3. Wählen Sie die Einheit aus dem Dropdown rechts (GB, TB).
4. Klicken Sie auf die Schaltfläche **{{t:common.actions.addToQueue}}**.

![Erweitern-Formular](/assets/images/UserGuideEng/66_expand_form.png)
*(Abbildung 66: Neuer Größenparameter zur Erhöhung der Repository-Größe)*

> **Tipp**: Geben Sie keinen Wert kleiner als die aktuelle Größe ein. Der Dienst wird während der Repository-Erweiterung nicht unterbrochen.

5. Warten Sie auf die Nachricht **{{t:queue.statusCompleted}}**.

![Erweitern abgeschlossen](/assets/images/UserGuideEng/67_expand_completed.png)
*(Abbildung 67: Repository-Erweiterung abgeschlossen)*

### 2.5.10 Umbenennen

Um den Repository-Namen zu ändern:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **{{t:common.actions.rename}}**.

![Umbenennen-Operation](/assets/images/UserGuideEng/68_rename_button.png)
*(Abbildung 68: "Umbenennen" Option aus fx Menü)*

2. Geben Sie den neuen Repository-Namen ein.
3. Klicken Sie auf die Schaltfläche **{{t:common.save}}**.

![Umbenennen-Formular](/assets/images/UserGuideEng/69_rename_form.png)
*(Abbildung 69: Dialog zur Eingabe des neuen Repository-Namens)*

> **Tipp**: Repository-Namen sollten aussagekräftig sein, um den Repository-Typ und Zweck widerzuspiegeln. Vermeiden Sie Sonderzeichen.

### 2.5.11 Repository löschen

Um das Repository dauerhaft zu löschen:

1. Wählen Sie das Repository und folgen Sie dem Pfad **fx** > **{{t:resources.repositories.deleteRepository}}**.

![Repository löschen Operation](/assets/images/UserGuideEng/70_delete_repo_button.png)
*(Abbildung 70: "Repository löschen" Option aus fx Menü - rot)*

2. Klicken Sie im Bestätigungsfenster auf die Schaltfläche **{{t:common.delete}}**.

> **Warnung**: Das Löschen eines Repositories ist unwiderruflich. Stellen Sie sicher, dass Repository-Daten vor dem Löschen gesichert sind.

### 2.5.12 Repository-Details

Um detaillierte Informationen über das Repository zu erhalten:

1. Wählen Sie das Repository.
2. Klicken Sie auf das Auge-Symbol (**Details anzeigen**).

![Details anzeigen Schaltfläche](/assets/images/UserGuideEng/71_repo_view_button.png)
*(Abbildung 71: Auge-Symbol zum Öffnen der Repository-Details)*

3. Überprüfen Sie Informationen im Detail-Panel:
   - **Repository-Name** und Typ
   - **Team**: Das zugehörige Team
   - **Maschine**: Die Maschine, auf der es sich befindet
   - **Vault-Version**: Verschlüsselungsversion
   - **Repository-GUID**: Eindeutiger Bezeichner
   - **Status**: Mounted/Unmounted-Status
   - **Image-Größe**: Gesamtgröße
   - **Zuletzt geändert**: Letztes Änderungsdatum

![Repository-Detail-Panel](/assets/images/UserGuideEng/72_repo_details_view.png)
*(Abbildung 72: Umfassende Informationen über das ausgewählte Repository)*

> **Tipp**: Alle in diesem Panel angezeigten Informationen dienen nur zur Referenz. Verwenden Sie fx-Menüoptionen für Repository-Operationen.

---

## 2.6 Repository-Verbindungsoperationen

Sie können sich mit verschiedenen Methoden mit Repositories verbinden.

### 2.6.1 Desktop-Anwendungsverbindung

1. Klicken Sie auf die Schaltfläche **{{t:resources.localActions.local}}** in der Repository-Zeile.

![Lokale Verbindungsschaltfläche](/assets/images/UserGuideEng/73_repo_connection_local.png)
*(Abbildung 73: "Lokal" Schaltfläche in der Repository-Zeile - Desktop-Anwendungszugriff)*

2. Wählen Sie die Zugriffsmethode aus dem Dropdown-Menü:
   - **{{t:resources.localActions.openInDesktop}}**: Zugriff mit grafischer Oberfläche
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: Im Code-Editor öffnen
   - **{{t:common.terminal.terminal}}**: Zugriff über Kommandozeile
   - **{{t:resources.localActions.showCLICommands}}**: Kommandozeilen-Tools

![Verbindungsoptionsmenü](/assets/images/UserGuideEng/74_repo_connection.png)
*(Abbildung 74: Repository-Verbindungsmenü - verschiedene Zugriffspfade)*

> **Tipp**: Wenn Sie mit VS Code arbeiten, bietet die Option "{{t:resources.localCommandBuilder.vscodeTab}}" die schnellste Integration.

3. Klicken Sie auf die Schaltfläche **Öffnen**, wenn der Browser um Erlaubnis bittet.

![Desktop-Anwendung Öffnungs-Erlaubnis](/assets/images/UserGuideEng/75_desktop_open_page.png)
*(Abbildung 75: Browser fragt nach Erlaubnis zum Öffnen der Desktop-Anwendung)*

> **Tipp**: Wenn Sie nicht jedes Mal um Erlaubnis gebeten werden möchten, wenn Sie die Desktop-Anwendung öffnen, aktivieren Sie die Option "Immer erlauben".

---

## 2.7 Einstellungen

Sie können Ihre Profil- und Systemeinstellungen im Einstellungsbereich verwalten.

### 2.7.1 Passwort ändern

1. Gehen Sie im linken Menü zur Registerkarte **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}**.

![Profileinstellungsseite](/assets/images/UserGuideEng/76_profiles_button.png)
*(Abbildung 76: Einstellungen → Profil-Seite - persönliche Vault-Einstellungen)*

2. Klicken Sie auf die Schaltfläche **{{t:settings.personal.changePassword.submit}}**.

![Passwort ändern Schaltfläche](/assets/images/UserGuideEng/77_profiles_change_button.png)
*(Abbildung 77: "Passwort ändern" Schaltfläche im persönlichen Einstellungsbereich)*

3. Geben Sie Ihr neues Passwort ein. Passwortanforderungen:
   - Mindestens 8 Zeichen lang
   - Muss Groß- und Kleinbuchstaben enthalten
   - Muss mindestens eine Zahl enthalten
   - Muss mindestens ein Sonderzeichen enthalten

4. Geben Sie das gleiche Passwort erneut in das Feld **{{t:settings.personal.changePassword.confirmPasswordLabel}}** ein.
5. Klicken Sie auf die Schaltfläche **{{t:settings.personal.changePassword.submit}}**.

![Passwort ändern Formular](/assets/images/UserGuideEng/78_profiles_change_form.png)
*(Abbildung 78: Passwort ändern Formular - Sicherheitsanforderungen sichtbar)*

> **Tipp**: Verwenden Sie zufällige Kombinationen bei der Erstellung eines starken Passworts.

---

## 2.8 Speicher

Der Speicherbereich ermöglicht es Ihnen, die physischen Bereiche zu verwalten, in denen Ihre Backup-Daten gespeichert werden.

### 2.8.1 Speicher hinzufügen

1. Gehen Sie im linken Menü zur Registerkarte **{{t:common.navigation.storage}}**.
2. Klicken Sie auf die Schaltfläche **{{t:resources.storage.createStorage}}**.

![Speicher hinzufügen Schaltfläche](/assets/images/UserGuideEng/79_storage_add_button.png)
*(Abbildung 79: Speicherverwaltungsseite - "Speicher hinzufügen" Schaltfläche)*

3. Füllen Sie das Formular aus:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: Geben Sie einen beschreibenden Namen ein
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: Wählen Sie (z.B. s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: Fügen Sie eine optionale Beschreibung hinzu
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: Optional
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: rclone-Flags (z.B. --transfers 4)

![Speicher-Erstellungsformular](/assets/images/UserGuideEng/80_storage_form.png)
*(Abbildung 80: Speicher hinzufügen Formular - Name, Anbieter, Beschreibung und Parameter)*

4. Klicken Sie auf die Schaltfläche **{{t:common.actions.create}}**.

> **Tipp**: Zusätzliche Parameter akzeptieren rclone-Flags zur Optimierung der Speicherleistung.

---

## 2.9 Anmeldedaten

Der Anmeldedatenbereich ermöglicht es Ihnen, Zugangsinformationen für Ihre Repositories sicher zu verwalten.

### 2.9.1 Anmeldedaten bearbeiten

1. Gehen Sie im linken Menü zur Registerkarte **{{t:common.navigation.credentials}}**.
2. Wählen Sie den Eintrag, den Sie bearbeiten möchten.
3. Klicken Sie auf die Schaltfläche **{{t:common.actions.edit}}**.

![Anmeldedatenliste](/assets/images/UserGuideEng/81_credentials.png)
*(Abbildung 81: Anmeldedatenseite - Repository-Namen, Teams und Verwaltungsschaltflächen)*

4. Ändern Sie den **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}** bei Bedarf.
5. Speichern Sie mit der Schaltfläche **{{t:common.save}}**.

![Anmeldedaten-Bearbeitungsformular](/assets/images/UserGuideEng/82_credentials_form.png)
*(Abbildung 82: Repository-Namen bearbeiten Formular - Vault-Konfigurationsfelder)*

> **Tipp**: Anmeldedaten werden verschlüsselt gespeichert und erst während der Bereitstellung entschlüsselt.

### 2.9.2 Anmeldedaten-Trace

1. Wählen Sie den Eintrag, den Sie verfolgen möchten.
2. Klicken Sie auf die Schaltfläche **{{t:common.actions.trace}}**.

![Trace-Schaltfläche](/assets/images/UserGuideEng/83_credentials_trace_button.png)
*(Abbildung 83: "Trace" Schaltfläche in der Anmeldedatentabelle)*

3. Überprüfen Sie die Audit-Historie.
4. Wählen Sie das Format über die Schaltfläche **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** oder **{{t:common.exportJSON}}**.

![Anmeldedaten-Audit-Historie](/assets/images/UserGuideEng/84_credentials_list_export.png)
*(Abbildung 84: Anmeldedatenliste - Export-Optionen)*

> **Tipp**: Die Trace-Funktion bietet Nutzungsverfolgung von Anmeldedaten für Sicherheits-Audit-Zwecke.

### 2.9.3 Anmeldedaten löschen

1. Wählen Sie den Eintrag, den Sie löschen möchten.
2. Klicken Sie auf die rote Schaltfläche **{{t:common.delete}}**.

![Löschen-Schaltfläche](/assets/images/UserGuideEng/85_credentials_delete.png)
*(Abbildung 85: Rote "Löschen" Schaltfläche auf der Anmeldedatenseite)*

3. Klicken Sie im Bestätigungsfenster auf die Schaltfläche **{{t:common.delete}}**.

![Löschbestätigung](/assets/images/UserGuideEng/86_credentials_delete_confirm.png)
*(Abbildung 86: Löschbestätigungsdialog - Warnung vor unwiderruflicher Aktion)*

> **Warnung**: Stellen Sie vor dem Löschen sicher, dass die Anmeldedaten nicht auf anderen Maschinen oder in anderen Operationen verwendet werden. Stellen Sie sicher, dass Sie ein Backup kritischer Anmeldedaten haben, bevor Sie löschen.

---

## 2.10 Warteschlange

Der Warteschlangenbereich ermöglicht es Ihnen, ausstehende und abgeschlossene Operationen im System zu verfolgen.

### 2.10.1 Warteschlangenoperationen

1. Klicken Sie im linken Menü auf die Registerkarte **{{t:common.navigation.queue}}**.

![Warteschlangenseite](/assets/images/UserGuideEng/87_queue_button.png)
*(Abbildung 87: Warteschlangenseite - Filteroptionen und Status-Registerkarten)*

2. Um Warteschlangenelemente zu filtern:
   - Verwenden Sie **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}** und **{{t:queue.trace.bridge}}** Filter
   - Geben Sie **{{t:system.audit.filters.dateRange}}** an
   - Aktivieren Sie die Option **{{t:queue.filters.onlyStale}}**

3. Zeigen Sie Details in Status-Registerkarten an:
   - **{{t:queue.statusActive}}**: Aufgaben, die verarbeitet werden
   - **{{t:queue.statusCompleted}}**: Erfolgreich abgeschlossene Aufgaben
   - **{{t:queue.statusCancelled}}**: Abgebrochene Aufgaben
   - **{{t:queue.statusFailed}}**: Fehlgeschlagene Aufgaben

4. Wählen Sie ein Format über die Schaltfläche **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** oder **{{t:common.exportJSON}}**.

![Warteschlangen-Export](/assets/images/UserGuideEng/88_queue_export.png)
*(Abbildung 88: Warteschlangenliste - Export-Optionen)*

> **Tipp**: Die Option "{{t:queue.filters.onlyStale}}" hilft, Aufgaben zu finden, die lange in Bearbeitung sind. Exportieren Sie regelmäßig die Warteschlangenhistorie, um Aufgabenausführungstrends zu analysieren.

---

## 2.11 Audit

Der Audit-Bereich führt Aufzeichnungen über alle im System durchgeführten Operationen.

### 2.11.1 Audit-Aufzeichnungen

1. Klicken Sie im linken Menü auf die Registerkarte **{{t:common.navigation.audit}}**.

![Audit-Liste](/assets/images/UserGuideEng/89_audit_list.png)
*(Abbildung 89: Audit-Seite - detaillierte Aufzeichnung aller Systemoperationen)*

2. Filtern Sie Audit-Aufzeichnungen:
   - **Datumsbereich**: Für einen bestimmten Zeitraum filtern
   - **Entitätstyp**: Nach Anfrage, Maschine, Warteschlange usw. filtern
   - **Suche**: Textsuche durchführen

3. Überprüfen Sie Informationen für jeden Eintrag:
   - **Zeitstempel**: Datum und Uhrzeit der Operation
   - **Aktion**: Art der Operation (Erstellen, Bearbeiten, Löschen usw.)
   - **Entitätstyp**: Typ des betroffenen Objekts
   - **Entitätsname**: Spezifischer Objektbezeichner
   - **Benutzer**: Benutzer, der die Operation durchgeführt hat
   - **Details**: Zusätzliche Informationen über die Operation

4. Wählen Sie ein Format über die Schaltfläche **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** oder **{{t:common.exportJSON}}**.

![Audit-Export](/assets/images/UserGuideEng/90_audit_export.png)
*(Abbildung 90: Audit-Aufzeichnung exportieren - CSV und JSON Optionen)*

> **Tipp**: Die Audit-Aufzeichnung ist entscheidend für die Verfolgung aller Systemaktivitäten zu Sicherheits- und Compliance-Zwecken. Exportieren Sie regelmäßig die Audit-Aufzeichnung und speichern Sie sie an einem sicheren Ort.

---

**© 2025 Rediacc-Plattform – Alle Rechte vorbehalten.**
