---
title: Application Web
description: Comprendre l'architecture et le déploiement de l'application web avec Rediacc
category: Reference
order: 1
language: fr
sourceHash: "ee9dff9ac2c8bce1"
---

# Guide d'Utilisation de la Plateforme Rediacc

## Vue d'Ensemble

**Rediacc** est une plateforme cloud offrant des services de sauvegarde alimentés par l'IA.

Ce guide explique l'utilisation de base de l'interface web sur [https://www.rediacc.com/](https://www.rediacc.com/).

### Objectif de Ce Guide

- Aider les nouveaux utilisateurs à s'adapter rapidement à la plateforme
- Expliquer les fonctions de base (gestion des ressources, sauvegarde) étape par étape

---

## 1. Création de Compte et Connexion

### 1.1 Inscription

![Registration process walkthrough](/assets/videos/user-guide/01-01-registration.webm)
*(Vidéo: Complete registration flow from start to finish)*

Pour commencer à utiliser la plateforme Rediacc, vous devez d'abord créer un compte.

![Page de connexion Rediacc - infrastructure toujours active](/assets/images/user-guide/01_login.png)
*(Figure 1 : Page de connexion principale, présentant les principales fonctionnalités de la plateforme Rediacc)*

1. Accédez à [https://www.rediacc.com/](https://www.rediacc.com/) dans votre navigateur.
2. Cliquez sur le bouton **{{t:auth.login.signIn}}** dans le coin supérieur droit de la page.
3. Choisissez **Commencer** pour un accès gratuit ou **Demander une démo** pour une démonstration.

> **Astuce** : Vous pouvez créer un compte gratuit sans carte de crédit. Comprend 10 cœurs CPU et des équipes illimitées.

![Formulaire de connexion Rediacc - champs email et mot de passe](/assets/images/user-guide/02_register.png)
*(Figure 2 : Écran de connexion pour les utilisateurs existants)*

4. Si vous n'avez pas de compte, cliquez sur le lien **{{t:auth.login.register}}** pour créer un nouveau compte.

5. Remplissez les informations suivantes dans le formulaire qui s'ouvre :
   - **{{t:auth.registration.organizationName}}** : Entrez le nom de votre organisation
   - **{{t:auth.login.email}}** : Entrez une adresse email valide
   - **{{t:auth.login.password}}** : Créez un mot de passe d'au moins 8 caractères
   - **{{t:auth.registration.passwordConfirm}}** : Saisissez à nouveau le même mot de passe

![Modal Créer un Compte - étapes inscription, vérification et finalisation](/assets/images/user-guide/03_create_account.png)
*(Figure 3 : Formulaire d'inscription étape par étape pour nouvel utilisateur - Inscription > Vérification > Finalisation)*

6. Cochez la case pour accepter les conditions d'utilisation et la politique de confidentialité.
7. Cliquez sur le bouton **{{t:auth.registration.createAccount}}**.

> **Astuce** : Le mot de passe doit contenir au moins 8 caractères et être robuste. Tous les champs sont obligatoires.

8. Entrez le code de vérification à 6 chiffres envoyé à votre email dans les cases de manière séquentielle.
9. Cliquez sur le bouton **{{t:auth.registration.verifyAccount}}**.

![Saisie du code de vérification - code d'activation à 6 chiffres](/assets/images/user-guide/04_verification_code.png)
*(Figure 4 : Fenêtre pour saisir le code d'activation envoyé à l'administrateur)*

> **Astuce** : Le code de vérification est valide pendant une durée limitée. Si vous ne recevez pas le code, vérifiez votre dossier spam.

---

### 1.2 Connexion

![Sign in process walkthrough](/assets/videos/user-guide/01-02-login.webm)
*(Vidéo: Complete sign in flow)*

Une fois votre compte créé, vous pouvez vous connecter à la plateforme.

1. Remplissez le champ **{{t:auth.login.email}}** (obligatoire si un avertissement rouge apparaît).
2. Remplissez le champ **{{t:auth.login.password}}**.
3. Cliquez sur le bouton **{{t:auth.login.signIn}}**.

![Formulaire de connexion - champs obligatoires avec avertissement d'erreur](/assets/images/user-guide/05_sign_in.png)
*(Figure 5 : Formulaire de connexion - les messages d'erreur sont marqués d'une bordure rouge)*

> **Astuce** : Si le message d'erreur indique "Ce champ est obligatoire", remplissez les champs vides. Contactez l'administrateur pour les mots de passe oubliés.

4. Après une connexion réussie, vous serez redirigé vers l'écran **{{t:common.navigation.dashboard}}**.

![Tableau de bord Rediacc - liste des machines et menu de la barre latérale](/assets/images/user-guide/06_dashboard.png)
*(Figure 6 : Tableau de bord principal après connexion réussie - menus Organisation, Machines et Paramètres dans la barre latérale gauche)*

> **Astuce** : Le tableau de bord se rafraîchit automatiquement. Vous pouvez actualiser la page avec F5 pour obtenir des informations à jour.

---

## 2. Vue d'Ensemble de l'Interface

Après vous être connecté, l'écran que vous voyez se compose de ces sections principales :

- **{{t:common.navigation.organization}}** : Utilisateurs, équipes et contrôle d'accès
- **{{t:common.navigation.machines}}** : Gestion des serveurs et des dépôts
- **{{t:common.navigation.settings}}** : Profil et paramètres système
- **{{t:common.navigation.storage}}** : Gestion de la zone de stockage
- **{{t:common.navigation.credentials}}** : Informations d'identification d'accès
- **{{t:common.navigation.queue}}** : Gestion de la file d'attente des tâches
- **{{t:common.navigation.audit}}** : Journaux d'audit système

---

## 2.1 Organisation - Utilisateurs

La gestion des utilisateurs vous permet de contrôler l'accès à la plateforme pour les personnes de votre organisation.

### 2.1.1 Ajout d'Utilisateurs

![Adding users walkthrough](/assets/videos/user-guide/02-01-01-user-create.webm)
*(Vidéo: Creating a new user)*

1. Cliquez sur l'option **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** dans la barre latérale gauche.
2. Visualisez la liste de tous les utilisateurs au format tableau.
3. Chaque ligne d'utilisateur affiche l'email, le statut ({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), le groupe de permissions et l'heure de dernière activité.

![Page de gestion des utilisateurs - liste des utilisateurs actifs](/assets/images/user-guide/07_users.png)
*(Figure 7 : Section Utilisateurs sous Organisation - toutes les informations des utilisateurs sont affichées)*

4. Cliquez sur l'icône **"+"** dans le coin supérieur droit.
5. Cliquez sur le bouton **{{t:organization.users.modals.createTitle}}** et remplissez le formulaire qui s'ouvre :
   - **{{t:organization.users.form.emailLabel}}** : Entrez l'adresse email de l'utilisateur
   - **{{t:organization.users.form.passwordLabel}}** : Entrez un mot de passe temporaire

![Modal de création d'utilisateur - champs email et mot de passe](/assets/images/user-guide/08_user_add.png)
*(Figure 8 : Fenêtre modale pour ajouter un nouvel utilisateur - formulaire simple et rapide de création d'utilisateur)*

6. Cliquez sur le bouton **{{t:common.actions.create}}**.

> **Astuce** : Les identifiants de connexion doivent être communiqués de manière sécurisée à l'utilisateur créé. Il est recommandé de changer le mot de passe à la première connexion.

![Liste des utilisateurs - vue tableau complète avec trois utilisateurs](/assets/images/user-guide/09_user_list.png)
*(Figure 9 : Tous les utilisateurs actifs et inactifs sur la page de gestion des utilisateurs)*

> **Astuce** : La page affiche automatiquement 20 enregistrements. Utilisez la pagination pour voir plus d'enregistrements.

### 2.1.2 Attribution des Permissions Utilisateur

![User permissions walkthrough](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(Vidéo: Assigning permission groups to users)*

Vous pouvez gérer les droits d'accès en attribuant des groupes de permissions spécifiques aux utilisateurs.

1. Sélectionnez un utilisateur dans l'onglet **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**.
2. Cliquez sur l'icône de bouclier dans la colonne d'actions (**{{t:organization.access.tabs.permissions}}**).

![Gestion des permissions - icônes bouclier, engrenage et suppression](/assets/images/user-guide/10_users_permissions.png)
*(Figure 10 : Affichage des icônes d'actions utilisateur - chaque icône représente une action différente)*

3. Sélectionnez un **{{t:organization.users.modals.permissionGroupLabel}}** dans le formulaire qui s'ouvre.
4. Le nombre d'utilisateurs et de permissions dans le groupe est affiché à côté de l'utilisateur.
5. Cliquez sur le bouton **{{t:organization.users.modals.assignTitle}}** pour enregistrer les modifications.

![Modal d'attribution de permissions - groupe Administrateurs](/assets/images/user-guide/11_user_permissions_form.png)
*(Figure 11 : Modal pour attribuer un groupe de permissions à l'utilisateur sélectionné - liste déroulante avec les groupes disponibles)*

> **Astuce** : Certains groupes de permissions sont fixés par le système et ne peuvent pas être modifiés.

### 2.1.3 Activation d'Utilisateur

![User activation walkthrough](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(Vidéo: Activating an inactive user)*

Vous pouvez réactiver les utilisateurs désactivés.

1. Trouvez l'utilisateur avec le statut inactif dans la liste **Utilisateurs**.
2. Cliquez sur l'icône rouge dans la colonne d'actions.

![Activation d'utilisateur - vue de l'infobulle "Activer"](/assets/images/user-guide/12_users_activation.png)
*(Figure 12 : Activation d'un utilisateur inactif)*

3. Cliquez sur le bouton **{{t:common.general.yes}}** dans la fenêtre de confirmation.

![Modal de confirmation d'activation](/assets/images/user-guide/13_users_activation_confirm.png)
*(Figure 13 : Fenêtre modale pour confirmer l'activation de l'utilisateur)*

> **Astuce** : Cette action est réversible. Vous pouvez désactiver l'utilisateur de la même manière.

### 2.1.4 Traçabilité Utilisateur

![User trace walkthrough](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(Vidéo: Viewing user activity trace)*

Vous pouvez utiliser la fonction de traçabilité pour surveiller les activités des utilisateurs.

1. Sélectionnez un utilisateur et cliquez sur l'icône d'engrenage dans la colonne d'actions.
2. Cliquez sur l'option **{{t:common.actions.trace}}** pour ouvrir l'historique d'activité de l'utilisateur.

![Traçabilité utilisateur - infobulle "Trace" avec bouton d'action](/assets/images/user-guide/14_users_trace.png)
*(Figure 14 : Option de traçabilité de l'activité utilisateur)*

3. Les activités passées de l'utilisateur sont répertoriées sur l'écran ouvert.
4. Les statistiques sont affichées en haut : Enregistrements Totaux, Enregistrements Consultés, Dernière Activité.
5. Cliquez sur le bouton **{{t:common.actions.export}}** et sélectionnez le format : **{{t:common.exportCSV}}** ou **{{t:common.exportJSON}}**.

![Historique d'Audit - Options d'exportation](/assets/images/user-guide/15_user_trace_export.png)
*(Figure 15 : Historique d'activité complet de l'utilisateur - statistiques, détails et options d'exportation)*

> **Astuce** : Exportez régulièrement les données d'audit pour maintenir des enregistrements de sécurité et de conformité. Le format CSV peut être ouvert dans Excel.

---

## 2.2 Organisation - Équipes

Les équipes vous permettent de regrouper des utilisateurs et de fournir un accès groupé aux ressources.

### 2.2.1 Création d'Équipes

![Creating teams walkthrough](/assets/videos/user-guide/02-02-01-team-create.webm)
*(Vidéo: Creating a new team)*

1. Accédez à l'onglet **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}**.
2. Cliquez sur le bouton **"+"**.
3. Entrez le nom de votre équipe dans le champ **{{t:common.vaultEditor.fields.TEAM.name.label}}**.
4. Remplissez les champs **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** et **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** dans la section **{{t:common.vaultEditor.vaultConfiguration}}**.

![Formulaire de création de nouvelle équipe - nom d'équipe et clés SSH](/assets/images/user-guide/16_teams_create.png)
*(Figure 16 : Création d'une nouvelle équipe dans "Équipe Privée")*

5. Cliquez sur le bouton **{{t:common.actions.create}}** pour enregistrer l'équipe.

> **Astuce** : Les clés SSH sont requises pour l'authentification SSH du Bridge. Si vous recevez un avertissement de clé manquante, fournissez les deux clés.

### 2.2.2 Modification d'Équipe

![Team editing walkthrough](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(Vidéo: Editing team information)*

1. Cliquez sur l'icône de crayon à côté de l'équipe que vous souhaitez modifier dans la liste des équipes.
2. Changez le nom de l'équipe dans le champ **{{t:common.vaultEditor.fields.TEAM.name.label}}** si nécessaire.
3. Mettez à jour les clés SSH dans la section **{{t:common.vaultEditor.vaultConfiguration}}**.
4. Cliquez sur le bouton **{{t:common.save}}** pour appliquer les modifications.

![Formulaire de modification d'équipe - message d'information bleu](/assets/images/user-guide/17_teams_edit_form.png)
*(Figure 17 : Modification des informations d'une équipe existante)*

> **Astuce** : La configuration de l'équipe est utilisée pour la structure organisationnelle. Les modifications prennent effet pour tous les membres de l'équipe.

### 2.2.3 Gestion des Membres de l'Équipe

![Team members management walkthrough](/assets/videos/user-guide/02-02-03-team-members.webm)
*(Vidéo: Managing team members)*

1. Sélectionnez une équipe et cliquez sur l'icône d'utilisateur.
2. Consultez les membres déjà assignés à l'équipe dans l'onglet **{{t:organization.teams.manageMembers.currentTab}}**.
3. Passez à l'onglet **{{t:organization.teams.manageMembers.addTab}}**.
4. Entrez une adresse email ou sélectionnez un utilisateur dans la liste déroulante.
5. Cliquez sur le bouton **"+"** pour ajouter le membre à l'équipe.

![Formulaire de gestion des membres de l'équipe - onglets "Membres Actuels" et "Ajouter un Membre"](/assets/images/user-guide/18_teams_members_form.png)
*(Figure 18 : Panneau de gestion des membres de l'équipe)*

> **Astuce** : Vous pouvez attribuer le même membre à plusieurs équipes.

### 2.2.4 Traçabilité de l'Équipe

![Team trace walkthrough](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(Vidéo: Viewing team audit history)*

1. Sélectionnez l'équipe que vous souhaitez tracer.
2. Cliquez sur l'icône d'horloge/historique.
3. Vérifiez les compteurs Enregistrements Totaux, Enregistrements Consultés et Dernière Activité dans la fenêtre **{{t:resources.audit.title}}**.
4. Cliquez sur le bouton **{{t:common.actions.export}}** pour exporter au format {{t:common.exportCSV}} ou {{t:common.exportJSON}}.

![Modal d'historique d'audit - équipe DataBassTeam](/assets/images/user-guide/19_teams_trace.png)
*(Figure 19 : Visualisation de l'historique d'audit de l'équipe)*

> **Astuce** : L'historique d'audit est important pour la conformité et le contrôle de sécurité.

### 2.2.5 Suppression d'Équipe

![Team deletion walkthrough](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(Vidéo: Deleting a team)*

1. Cliquez sur l'icône de corbeille (rouge) à côté de l'équipe que vous souhaitez supprimer.
2. Vérifiez que le nom de l'équipe est correct dans la boîte de dialogue de confirmation.
3. Cliquez sur le bouton **{{t:common.general.yes}}**.

![Dialogue de confirmation de suppression d'équipe](/assets/images/user-guide/20_teams_delete.png)
*(Figure 20 : Confirmation de suppression d'équipe)*

> **Avertissement** : La suppression d'équipe est irréversible. Vérifiez s'il y a des données importantes dans l'équipe avant de supprimer.

---

## 2.3 Organisation - Contrôle d'Accès

Le contrôle d'accès vous permet de gérer de manière centralisée les permissions des utilisateurs en créant des groupes de permissions.

### 2.3.1 Création de Groupes de Permissions

![Permission group creation walkthrough](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(Vidéo: Creating a permission group)*

1. Accédez à l'onglet **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}**.
2. Cliquez sur le bouton **"+"**.
3. Entrez un nom significatif dans le champ **{{t:organization.access.modals.groupPlaceholder}}**.
4. Cliquez sur le bouton **{{t:common.actions.confirm}}** pour créer le groupe.

![Formulaire de création de groupe de permissions](/assets/images/user-guide/21_create_access.png)
*(Figure 21 : Création d'un nouveau Groupe de Permissions)*

> **Astuce** : Les groupes de permissions sont utilisés pour organiser les utilisateurs avec des permissions similaires. Gardez les noms de groupes descriptifs (par exemple, "Admin", "Lecture Seule", "Gestionnaire de Dépôt").

### 2.3.2 Gestion des Permissions

![Permission management walkthrough](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(Vidéo: Managing permissions for a group)*

1. Sélectionnez un Groupe de Permissions et cliquez sur l'option **{{t:organization.access.modals.managePermissionsTitle}}**.
2. Consultez les droits d'accès du groupe dans l'onglet **{{t:organization.access.modals.currentPermissionsTab}}**.
3. Vous pouvez révoquer une permission en cliquant sur le bouton rouge **{{t:common.delete}}** à côté de chaque action.
4. Cliquez sur l'onglet **{{t:organization.access.modals.addPermissionsTab}}** pour ajouter de nouvelles permissions au groupe.

![Panneau de gestion des permissions - liste des permissions attribuées](/assets/images/user-guide/22_access_permission.png)
*(Figure 22 : Gestion des Permissions pour le Groupe de Permissions)*

> **Astuce** : Accordez les permissions selon le principe du moindre privilège. Révisez et supprimez régulièrement les permissions inutiles.

---

## 2.4 Machines

La section Machines vous permet de gérer vos serveurs et ressources de dépôt.

### 2.4.1 Ajout de Machines

![Adding machines walkthrough](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(Vidéo: Adding a new machine)*

1. Accédez à l'onglet **{{t:common.navigation.machines}}** depuis le menu de gauche.
2. Cliquez sur le bouton **{{t:machines.createMachine}}** dans le coin supérieur droit.

![Page Machines - bouton "Ajouter une Machine"](/assets/images/user-guide/23_machines_add.png)
*(Figure 23 : Page d'accueil de gestion des Machines)*

3. Remplissez le formulaire qui s'ouvre :
   - **{{t:machines.machineName}}** : Entrez un nom unique (par exemple, "server-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}** : Entrez l'adresse IP de la machine (par exemple, 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}** : Spécifiez le répertoire de stockage (par exemple, /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}** : Entrez le nom d'utilisateur SSH
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}** : Entrez le numéro de port (par défaut : 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}** : Entrez le mot de passe (optionnel)

![Formulaire d'ajout de machine - tous les champs](/assets/images/user-guide/24_machine_create.png)
*(Figure 24 : Formulaire d'ajout de nouvelle machine - nom de machine, paramètres réseau, identifiants SSH)*

4. Cliquez sur le bouton **{{t:common.vaultEditor.testConnection.button}}** pour vérifier la connexion.
5. Après le succès du test, cliquez sur le bouton **{{t:common.actions.create}}**.

> **Astuce** : Si l'option "Démarrer automatiquement la configuration après la création de la machine" est cochée, la machine effectuera automatiquement des étapes de configuration supplémentaires.

![Création de machine terminée - fenêtre de suivi de tâche](/assets/images/user-guide/25_machine_create_complete.png)
*(Figure 25 : Fenêtre de suivi de tâche après la création réussie de la machine)*

6. Observez les étapes : **{{t:queue.trace.assigned}}** → **Traitement** → **{{t:queue.statusCompleted}}**
7. Cliquez sur le bouton **{{t:common.actions.close}}** pour fermer l'opération.

> **Astuce** : Cliquez sur le bouton "{{t:common.actions.refresh}}" pour vérifier manuellement le dernier statut.

### 2.4.2 Test de Connectivité

![Connectivity test walkthrough](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(Vidéo: Running a connectivity test)*

Vous pouvez vérifier l'état de connexion des machines existantes.

1. Cliquez sur le bouton **{{t:machines.connectivityTest}}**.

![Bouton Test de Connectivité](/assets/images/user-guide/26_connectivity_test_button.png)
*(Figure 26 : Bouton Test de Connectivité dans la barre d'outils d'actions de la machine)*

2. Consultez la liste des machines à tester.
3. Cliquez sur le bouton **{{t:machines.runTest}}**.
4. Les résultats réussis sont affichés en vert, les échecs en rouge.

![Formulaire de test de connectivité - liste des machines](/assets/images/user-guide/27_connectivity_test_form.png)
*(Figure 27 : Formulaire de test de connectivité - fonction ping pour les machines sélectionnées)*

> **Astuce** : Si le test échoue, vérifiez l'adresse IP de la machine et les paramètres SSH.

### 2.4.3 Actualisation de la Liste des Machines

![Machine list refresh walkthrough](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(Vidéo: Refreshing the machine list)*

Cliquez sur le bouton **{{t:common.actions.refresh}}** pour mettre à jour la liste des machines.

![Bouton Actualiser](/assets/images/user-guide/28_refresh.png)
*(Figure 28 : Bouton Actualiser dans la barre d'outils d'actions de la machine)*

### 2.4.4 Détails de la Machine

![Machine details walkthrough](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(Vidéo: Viewing machine details)*

1. Sélectionnez la machine dont vous souhaitez voir les détails.
2. Cliquez sur le bouton icône œil (**{{t:common.viewDetails}}**).

![Bouton Voir les Détails](/assets/images/user-guide/29_view_details_button.png)
*(Figure 29 : Icône œil dans la colonne d'actions de la machine)*

3. Le panneau de détails de la machine s'ouvre sur le côté droit :
   - **Nom d'hôte** : Nom de la machine
   - **Temps de fonctionnement** : Temps de fonctionnement
   - **{{t:queue.trace.operatingSystem}}** : OS et version
   - **{{t:queue.trace.kernelVersion}}** : Version du noyau
   - **CPU** : Informations sur le processeur
   - **Heure système** : Horloge système

![Panneau de détails de la machine - informations système](/assets/images/user-guide/30_machine_view_details.png)
*(Figure 30 : Panneau de détails de la machine - hostname, uptime, OS, noyau, informations CPU)*

> **Astuce** : Révisez régulièrement ces informations pour vérifier la compatibilité de l'OS et la disponibilité des ressources.

### 2.4.5 Modification de Machine

![Machine editing walkthrough](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(Vidéo: Editing machine settings)*

1. Sélectionnez la machine que vous souhaitez modifier.
2. Cliquez sur le bouton icône crayon (**{{t:common.actions.edit}}**).

![Bouton Modifier](/assets/images/user-guide/31_edit_button.png)
*(Figure 31 : Icône crayon dans la colonne d'actions de la machine)*

3. Effectuez les modifications nécessaires.
4. Cliquez sur le bouton **{{t:common.vaultEditor.testConnection.button}}**.
5. Lorsque la connexion est réussie, cliquez sur le bouton **{{t:common.save}}**.

![Formulaire de modification de machine](/assets/images/user-guide/32_edit_form.png)
*(Figure 32 : Formulaire de modification de machine - nom de machine, région et configuration du coffre-fort)*

> **Astuce** : Exécutez toujours "Test Connection" après avoir modifié des paramètres critiques.

### 2.4.6 Traçabilité de la Machine

![Machine trace walkthrough](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(Vidéo: Viewing machine audit history)*

1. Sélectionnez la machine et cliquez sur le bouton icône horloge (**{{t:common.actions.trace}}**).

![Bouton Traçabilité](/assets/images/user-guide/33_trace_button.png)
*(Figure 33 : Icône horloge dans la colonne d'actions de la machine)*

2. Consultez les opérations dans la fenêtre d'historique d'audit :
   - **{{t:resources.audit.action}}** : Type d'opération effectuée
   - **Détails** : Champs modifiés
   - **{{t:resources.audit.performedBy}}** : Utilisateur ayant effectué l'action
   - **Horodatage** : Date et heure

![Fenêtre d'historique d'audit de la machine](/assets/images/user-guide/34_trace_list.png)
*(Figure 34 : Historique d'audit - liste de tous les changements)*

> **Astuce** : Cliquez sur la colonne Horodatage pour visualiser les changements par ordre chronologique.

### 2.4.7 Suppression de Machine

![Machine deletion walkthrough](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(Vidéo: Deleting a machine)*

1. Sélectionnez la machine que vous souhaitez supprimer.
2. Cliquez sur le bouton icône corbeille (**{{t:common.delete}}**).

![Bouton Supprimer](/assets/images/user-guide/35_delete_button.png)
*(Figure 35 : Icône corbeille dans la colonne d'actions de la machine)*

3. Cliquez sur le bouton **{{t:common.delete}}** dans la fenêtre de confirmation.

![Fenêtre de confirmation de suppression de machine](/assets/images/user-guide/36_delete_form.png)
*(Figure 36 : Fenêtre de confirmation "Êtes-vous sûr de vouloir supprimer cette machine ?")*

> **Avertissement** : Lorsqu'une machine est supprimée, toutes les définitions de dépôt qu'elle contient sont également supprimées. Cette action est irréversible.

### 2.4.8 Opérations à Distance

![Remote operations walkthrough](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(Vidéo: Running remote operations on a machine)*

Vous pouvez effectuer diverses opérations à distance sur les machines.

1. Sélectionnez la machine et cliquez sur le bouton **{{t:common.actions.remote}}**.
2. Consultez les options dans le menu déroulant :
   - **{{t:machines.runAction}}** : Exécuter une fonction sur la machine
   - **{{t:common.vaultEditor.testConnection.button}}** : Tester la connectivité de la machine

![Menu Remote - Exécuter sur le serveur et Tester la connexion](/assets/images/user-guide/37_remote_button.png)
*(Figure 37 : Bouton Remote - menu d'exécution de fonction sur la machine sélectionnée)*

> **Astuce** : Utilisez l'option "{{t:common.vaultEditor.testConnection.button}}" pour vérifier que la machine est accessible avant d'exécuter des fonctions.

#### Configuration

1. Sélectionnez l'option **{{t:machines.runAction}}**.
2. Trouvez la fonction **Setup** dans la liste **{{t:functions.availableFunctions}}**.
3. Cliquez sur le nom de la fonction pour la sélectionner.

![Liste des fonctions de la machine - fonction de configuration](/assets/images/user-guide/38_server_setup.png)
*(Figure 38 : Fonction Configuration - prépare la machine avec les outils et configurations requis)*

> **Astuce** : Il est recommandé d'exécuter d'abord la fonction "Setup" lors de la configuration d'une nouvelle machine.

#### Bonjour

1. Sélectionnez **{{t:machines.runAction}}** > fonction **Bonjour**.
2. Cliquez sur le bouton **{{t:common.actions.addToQueue}}**.

![Sélection de la fonction Bonjour](/assets/images/user-guide/39_remote_hello.png)
*(Figure 39 : Fonction Bonjour - fonction de test simple, renvoie le nom d'hôte)*

3. Observez les résultats dans la fenêtre de suivi de tâche.
4. Consultez la sortie de la machine dans la section **{{t:queue.trace.responseConsole}}**.

![Fonction Bonjour terminée](/assets/images/user-guide/40_remote_hello_complete.png)
*(Figure 40 : Fonction Bonjour terminée avec succès - réponse nom d'hôte)*

> **Astuce** : La fonction Hello est idéale pour vérifier la connectivité de la machine.

#### Opérations Avancées

1. Suivez le chemin **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}**.
2. Consultez les fonctions disponibles : setup, hello, ping, ssh_test, uninstall
3. Sélectionnez la fonction requise et cliquez sur le bouton **{{t:common.actions.addToQueue}}**.

![Liste des fonctions avancées](/assets/images/user-guide/41_remote_advanced.png)
*(Figure 41 : Option Avancées - liste des fonctions avancées)*

> **Astuce** : Assurez-vous que la configuration de la machine est terminée avant d'utiliser les fonctions Avancées.

#### Test de Connectivité Rapide

![Menu Remote - Test de Connexion](/assets/images/user-guide/42_connectivity_test.png)
*(Figure 42 : Option Test de Connexion depuis le menu Distant)*

> **Astuce** : Si la machine a des problèmes SSH ou réseau, vous pouvez identifier rapidement les problèmes avec ce test.

---

## 2.5 Création et Opérations de Dépôt

Les dépôts sont les unités fondamentales où vos données de sauvegarde sont stockées.

### 2.5.1 Création de Dépôts

![Repository creation walkthrough](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(Vidéo: Creating a new repository)*

1. Sélectionnez une machine dans l'onglet **{{t:common.navigation.machines}}**.
2. Cliquez sur le bouton **{{t:machines.createRepository}}** dans le coin supérieur droit.

![Bouton Créer un Dépôt](/assets/images/user-guide/43_create_repo_add.png)
*(Figure 43 : Écran de gestion des dépôts de la machine - bouton Créer un Dépôt)*

3. Remplissez le formulaire :
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}** : Entrez le nom du dépôt (par exemple, postgresql)
   - **{{t:resources.repositories.size}}** : Entrez la taille du dépôt (par exemple, 2GB)
   - **{{t:resources.repositories.repositoryGuid}}** : Consultez l'identifiant généré automatiquement
   - **{{t:resources.templates.selectTemplate}}** : Choisissez un modèle (par exemple, databases_postgresql)

![Formulaire de création de dépôt](/assets/images/user-guide/44_repo_form.png)
*(Figure 44 : Formulaire de création de dépôt - nom du dépôt, taille et sélection de modèle)*

4. Cliquez sur le bouton **{{t:common.actions.create}}**.

> **Astuce** : L'ID d'identification est généré automatiquement, la modification manuelle n'est pas recommandée.

5. Observez les étapes dans la fenêtre de suivi de tâche : **{{t:queue.trace.assigned}}** → **Traitement** → **{{t:queue.statusCompleted}}**

![Création de dépôt terminée](/assets/images/user-guide/45_repo_complete.png)
*(Figure 45 : Création de dépôt mise en file d'attente - surveillance de tâche)*

6. Cliquez sur le bouton **{{t:common.actions.close}}**.

> **Astuce** : La tâche se termine généralement en 1-2 minutes.

![Liste des dépôts](/assets/images/user-guide/46_repo_list.png)
*(Figure 46 : Le dépôt créé apparaît dans la liste)*

### 2.5.2 Fork de Dépôt

![Repository fork walkthrough](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(Vidéo: Forking a repository)*

Vous pouvez créer un nouveau dépôt en copiant un dépôt existant.

1. Sélectionnez le dépôt que vous souhaitez copier.
2. Cliquez sur le menu **fx** (fonction).
3. Cliquez sur l'option **fork**.

![Menu fx - option fork](/assets/images/user-guide/47_fork_button.png)
*(Figure 47 : Menu fx sur le côté droit - opérations de dépôt)*

4. Entrez un nouveau tag dans le champ **{{t:functions.functions.fork.params.tag.label}}** (par exemple, 2025-12-06-20-37-08).
5. Cliquez sur le bouton **{{t:common.actions.addToQueue}}**.

![Formulaire de configuration de Fork](/assets/images/user-guide/48_fork_form.png)
*(Figure 48 : Spécifier le nouveau tag pour le dépôt dans l'opération fork)*

6. Attendez le message **{{t:queue.statusCompleted}}** et cliquez sur le bouton **{{t:common.actions.close}}**.

![Fork terminé](/assets/images/user-guide/49_repo_completed.png)
*(Figure 49 : Opération Fork terminée avec succès)*

> **Astuce** : Créer des tags au format date-heure par défaut est une bonne pratique. L'opération fork n'affecte pas le dépôt original.

### 2.5.3 Démarrage de Dépôt (Up)

![Repository up walkthrough](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(Vidéo: Starting a repository)*

Pour activer le dépôt :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **up**.

![Opération Up](/assets/images/user-guide/50_repo_up.png)
*(Figure 50 : Option "up" du menu fx - démarrage du dépôt)*

2. Attendez le message **{{t:queue.statusCompleted}}**.

![Up terminé](/assets/images/user-guide/51_repo_up_complete.png)
*(Figure 51 : Démarrage du dépôt terminé)*

> **Astuce** : L'opération "Up" démarre les services Docker définis dans le dépôt.

### 2.5.4 Arrêt de Dépôt (Down)

![Repository down walkthrough](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(Vidéo: Stopping a repository)*

Pour arrêter un dépôt actif :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **down**.

![Opération Down](/assets/images/user-guide/52_down_button.png)
*(Figure 52 : Option "down" du menu fx - arrêt du dépôt)*

2. Attendez le message **{{t:queue.statusCompleted}}**.

![Down terminé](/assets/images/user-guide/53_down_completed.png)
*(Figure 53 : Arrêt du dépôt terminé)*

> **Astuce** : L'opération "Down" arrête le dépôt en toute sécurité. Aucune donnée n'est perdue, seuls les services sont arrêtés.

### 2.5.5 Déploiement

![Repository deploy walkthrough](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(Vidéo: Deploying a repository)*

Pour déployer le dépôt vers un emplacement différent :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **deploy**.

![Opération Deploy](/assets/images/user-guide/54_deploy_button.png)
*(Figure 54 : Option "deploy" du menu fx)*

2. Entrez la version à déployer dans le champ **{{t:functions.functions.fork.params.tag.label}}**.
3. Sélectionnez les machines cibles dans le champ **{{t:functions.functions.backup_deploy.params.machines.label}}**.
4. Cochez l'option **{{t:functions.checkboxOptions.overrideExistingFile}}** (si applicable).
5. Cliquez sur le bouton **{{t:common.actions.addToQueue}}**.

![Formulaire Deploy](/assets/images/user-guide/55_deploy_form.png)
*(Figure 55 : Configuration de l'opération deploy - tag, machines cibles et options)*

6. Attendez le message **{{t:queue.statusCompleted}}**.

![Deploy terminé](/assets/images/user-guide/56_deploy_completed.png)
*(Figure 56 : Déploiement du dépôt terminé)*

> **Astuce** : Une fois l'opération deploy terminée, vous pouvez exécuter la commande "up" pour démarrer le dépôt sur les machines cibles.

### 2.5.6 Sauvegarde

![Repository backup walkthrough](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(Vidéo: Backing up a repository)*

Pour sauvegarder le dépôt :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **backup**.

![Opération Backup](/assets/images/user-guide/57_backup_button.png)
*(Figure 57 : Option "backup" du menu fx)*

2. Remplissez le formulaire :
   - **{{t:functions.functions.fork.params.tag.label}}** : Entrez un nom descriptif (par exemple, backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}** : Sélectionnez l'emplacement de sauvegarde
   - **{{t:functions.checkboxOptions.overrideExistingFile}}** : Activez ou désactivez l'option
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}** : Vérifiez le paramètre

![Formulaire Backup](/assets/images/user-guide/58_backup_form.png)
*(Figure 58 : Formulaire de configuration de sauvegarde - cible, nom de fichier et options)*

3. Cliquez sur le bouton **{{t:common.actions.addToQueue}}**.

> **Astuce** : Utilisez un nom descriptif pour le tag de sauvegarde. Envisagez d'activer le checkpoint pour les grands dépôts.

4. Attendez le message **{{t:queue.statusCompleted}}**.

![Backup terminé](/assets/images/user-guide/59_backup_completed.png)
*(Figure 59 : Tâche de sauvegarde terminée avec succès)*

> **Astuce** : Attendez patiemment avant d'atteindre le statut terminé ; les grandes sauvegardes peuvent prendre plusieurs minutes.

### 2.5.7 Application de Modèle

![Template application walkthrough](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(Vidéo: Applying a template to a repository)*

Pour appliquer un nouveau modèle au dépôt :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **{{t:resources.templates.selectTemplate}}**.

![Opération Templates](/assets/images/user-guide/60_templates_button.png)
*(Figure 60 : Option "Templates" du menu fx)*

2. Filtrez les modèles en tapant dans la boîte de recherche.
3. Cliquez sur le modèle souhaité pour le sélectionner (le modèle sélectionné est surligné avec une bordure en gras).
4. Cliquez sur le bouton **{{t:common.actions.addToQueue}}**.

![Formulaire de sélection de modèle](/assets/images/user-guide/61_templates_form.png)
*(Figure 61 : Recherche et sélection des modèles disponibles)*

> **Astuce** : Utilisez la boîte de recherche pour trouver rapidement des modèles. Utilisez **{{t:common.viewDetails}}** pour en savoir plus sur les fonctionnalités des modèles.

5. Attendez le message **{{t:queue.statusCompleted}}**.

![Modèle appliqué](/assets/images/user-guide/62_templates_completed.png)
*(Figure 62 : Application du modèle terminée avec succès)*

### 2.5.8 Démontage

![Repository unmount walkthrough](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(Vidéo: Unmounting a repository)*

Pour déconnecter le dépôt :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}**.

![Opération Unmount](/assets/images/user-guide/63_unmount_button.png)
*(Figure 63 : Option "Unmount" dans le menu avancé)*

2. Attendez le message **{{t:queue.statusCompleted}}**.

![Unmount terminé](/assets/images/user-guide/64_unmount_completed.png)
*(Figure 64 : Opération Unmount terminée)*

> **Astuce** : Assurez-vous qu'il n'y a pas d'opérations actives sur le dépôt avant de démonter. Après démontage, le dépôt devient inaccessible.

### 2.5.9 Extension

![Repository expand walkthrough](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(Vidéo: Expanding repository size)*

Pour augmenter la taille du dépôt :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}**.

![Opération Expand](/assets/images/user-guide/65_expand_button.png)
*(Figure 65 : Option "Expand" dans le menu avancé)*

2. Entrez la taille souhaitée dans le champ **{{t:functions.functions.repository_expand.params.size.label}}**.
3. Sélectionnez l'unité dans la liste déroulante à droite (GB, TB).
4. Cliquez sur le bouton **{{t:common.actions.addToQueue}}**.

![Formulaire Expand](/assets/images/user-guide/66_expand_form.png)
*(Figure 66 : Nouveau paramètre de taille pour augmenter la taille du dépôt)*

> **Astuce** : N'entrez pas une valeur inférieure à la taille actuelle. Le service n'est pas interrompu pendant l'extension du dépôt.

5. Attendez le message **{{t:queue.statusCompleted}}**.

![Expand terminé](/assets/images/user-guide/67_expand_completed.png)
*(Figure 67 : Extension du dépôt terminée)*

### 2.5.10 Renommage

![Repository rename walkthrough](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(Vidéo: Renaming a repository)*

Pour changer le nom du dépôt :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **{{t:common.actions.rename}}**.

![Opération Rename](/assets/images/user-guide/68_rename_button.png)
*(Figure 68 : Option "Rename" du menu fx)*

2. Entrez le nouveau nom du dépôt.
3. Cliquez sur le bouton **{{t:common.save}}**.

![Formulaire Rename](/assets/images/user-guide/69_rename_form.png)
*(Figure 69 : Dialogue pour entrer le nouveau nom du dépôt)*

> **Astuce** : Les noms de dépôt doivent être significatifs pour refléter le type et l'objectif du dépôt. Évitez les caractères spéciaux.

### 2.5.11 Suppression de Dépôt

![Repository deletion walkthrough](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(Vidéo: Deleting a repository)*

Pour supprimer définitivement le dépôt :

1. Sélectionnez le dépôt et suivez le chemin **fx** > **{{t:resources.repositories.deleteRepository}}**.

![Opération Supprimer le Dépôt](/assets/images/user-guide/70_delete_repo_button.png)
*(Figure 70 : Option "Supprimer le Dépôt" du menu fx - rouge)*

2. Cliquez sur le bouton **{{t:common.delete}}** dans la fenêtre de confirmation.

> **Avertissement** : La suppression du dépôt est irréversible. Assurez-vous que les données du dépôt sont sauvegardées avant de supprimer.

### 2.5.12 Détails du Dépôt

![Repository details walkthrough](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(Vidéo: Viewing repository details)*

Pour obtenir des informations détaillées sur le dépôt :

1. Sélectionnez le dépôt.
2. Cliquez sur l'icône œil (**{{t:common.viewDetails}}**).

![Bouton Afficher les détails](/assets/images/user-guide/71_repo_view_button.png)
*(Figure 71 : Icône œil pour ouvrir les détails du dépôt)*

3. Consultez les informations dans le panneau de détails :
   - **Nom du dépôt** et type
   - **Équipe** : L'équipe à laquelle il appartient
   - **Machine** : La machine sur laquelle il se trouve
   - **Version du coffre-fort** : Version de chiffrement
   - **GUID du dépôt** : Identifiant unique
   - **Statut** : Statut Monté/Démonté
   - **Taille de l'image** : Taille totale
   - **Dernière modification** : Date de dernière modification

![Panneau de détails du dépôt](/assets/images/user-guide/72_repo_details_view.png)
*(Figure 72 : Informations complètes sur le dépôt sélectionné)*

> **Astuce** : Toutes les informations affichées dans ce panneau sont à titre de référence. Utilisez les options du menu fx pour les opérations de dépôt.

---

## 2.6 Opérations de Connexion au Dépôt

Vous pouvez vous connecter aux dépôts en utilisant différentes méthodes.

### 2.6.1 Connexion par Application de Bureau

![Desktop connection walkthrough](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(Vidéo: Connecting via desktop application)*

1. Cliquez sur le bouton **{{t:resources.localActions.local}}** dans la ligne du dépôt.

![Bouton de connexion Local](/assets/images/user-guide/73_repo_connection_local.png)
*(Figure 73 : Bouton "Local" dans la ligne du dépôt - accès à l'application de bureau)*

2. Sélectionnez la méthode d'accès dans le menu déroulant :
   - **{{t:resources.localActions.openInDesktop}}** : Accès avec interface graphique
   - **{{t:resources.localCommandBuilder.vscodeTab}}** : Ouvrir dans l'éditeur de code
   - **{{t:common.terminal.terminal}}** : Accès via ligne de commande
   - **{{t:resources.localActions.showCLICommands}}** : Outils en ligne de commande

![Menu d'options de connexion](/assets/images/user-guide/74_repo_connection.png)
*(Figure 74 : Menu de connexion au dépôt - différents chemins d'accès)*

> **Astuce** : Si vous travaillez avec VS Code, l'option "{{t:resources.localCommandBuilder.vscodeTab}}" offre l'intégration la plus rapide.

3. Cliquez sur le bouton **{{t:common.vscodeSelection.open}}** lorsque le navigateur demande la permission.

![Permission d'ouverture de l'application de bureau](/assets/images/user-guide/75_desktop_open_page.png)
*(Figure 75 : Le navigateur demandant la permission d'ouvrir l'application de bureau)*

> **Astuce** : Si vous ne souhaitez pas accorder la permission à chaque fois que vous ouvrez l'application de bureau, cochez l'option "Toujours autoriser".

---

## 2.7 Paramètres

Vous pouvez gérer votre profil et les paramètres système depuis la section Paramètres.

### 2.7.1 Changement de Mot de Passe

![Password change walkthrough](/assets/videos/user-guide/02-07-03-password-change.webm)
*(Vidéo: Changing your password)*

1. Accédez à l'onglet **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}** depuis le menu de gauche.

![Page des paramètres de profil](/assets/images/user-guide/76_profiles_button.png)
*(Figure 76 : Page Paramètres → Profil - paramètres du coffre-fort personnel)*

2. Cliquez sur le bouton **{{t:settings.personal.changePassword.submit}}**.

![Bouton Changer le Mot de Passe](/assets/images/user-guide/77_profiles_change_button.png)
*(Figure 77 : Bouton "Change Password" dans la section des paramètres personnels)*

3. Entrez votre nouveau mot de passe. Exigences du mot de passe :
   - Au moins 8 caractères
   - Doit contenir des lettres majuscules et minuscules
   - Doit contenir au moins un chiffre
   - Doit contenir au moins un caractère spécial

4. Saisissez à nouveau le même mot de passe dans le champ **{{t:settings.personal.changePassword.confirmPasswordLabel}}**.
5. Cliquez sur le bouton **{{t:settings.personal.changePassword.submit}}**.

![Formulaire de changement de mot de passe](/assets/images/user-guide/78_profiles_change_form.png)
*(Figure 78 : Formulaire Change Password - exigences de sécurité visibles)*

> **Astuce** : Utilisez des combinaisons aléatoires lors de la création d'un mot de passe robuste.

---

## 2.8 Stockage

La section Stockage vous permet de gérer les zones physiques où vos données de sauvegarde seront stockées.

### 2.8.1 Ajout de Stockage

![Storage creation walkthrough](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(Vidéo: Adding a storage location)*

1. Accédez à l'onglet **{{t:common.navigation.storage}}** depuis le menu de gauche.
2. Cliquez sur le bouton **{{t:resources.storage.createStorage}}**.

![Bouton Add Storage](/assets/images/user-guide/79_storage_add_button.png)
*(Figure 79 : Page de gestion du stockage - bouton "Add Storage")*

3. Remplissez le formulaire :
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}** : Entrez un nom descriptif
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}** : Sélectionnez (par exemple, s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}** : Ajoutez une description optionnelle
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}** : Optionnel
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}** : Drapeaux rclone (par exemple, --transfers 4)

![Formulaire de création de stockage](/assets/images/user-guide/80_storage_form.png)
*(Figure 80 : Formulaire Add Storage - nom, fournisseur, description et paramètres)*

4. Cliquez sur le bouton **{{t:common.actions.create}}**.

> **Astuce** : Les Paramètres Additionnels acceptent les drapeaux rclone pour optimiser les performances du stockage.

---

## 2.9 Identifiants

La section Identifiants vous permet de gérer de manière sécurisée les informations d'accès pour vos dépôts.

### 2.9.1 Modification d'Identifiants

![Credential editing walkthrough](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(Vidéo: Editing credentials)*

1. Accédez à l'onglet **{{t:common.navigation.credentials}}** depuis le menu de gauche.
2. Sélectionnez l'enregistrement que vous souhaitez modifier.
3. Cliquez sur le bouton **{{t:common.actions.edit}}**.

![Liste des identifiants](/assets/images/user-guide/81_credentials.png)
*(Figure 81 : Page Identifiants - noms de dépôt, équipes et boutons de gestion)*

4. Modifiez le **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}** si nécessaire.
5. Enregistrez avec le bouton **{{t:common.save}}**.

![Formulaire de modification d'identifiants](/assets/images/user-guide/82_credentials_form.png)
*(Figure 82 : Formulaire Modifier le Nom du Dépôt - champs de configuration du coffre-fort)*

> **Astuce** : Les identifiants sont stockés chiffrés et ne sont déchiffrés que pendant le déploiement.

### 2.9.2 Traçabilité des Identifiants

![Credential trace walkthrough](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(Vidéo: Viewing credential audit history)*

1. Sélectionnez l'enregistrement que vous souhaitez tracer.
2. Cliquez sur le bouton **{{t:common.actions.trace}}**.

![Bouton Trace](/assets/images/user-guide/83_credentials_trace_button.png)
*(Figure 83 : Bouton "Trace" dans le tableau Identifiants)*

3. Consultez l'historique d'audit.
4. Sélectionnez le format depuis le bouton **{{t:common.actions.export}}** : **{{t:common.exportCSV}}** ou **{{t:common.exportJSON}}**.

![Historique d'audit des identifiants](/assets/images/user-guide/84_credentials_list_export.png)
*(Figure 84 : Liste des identifiants - Options d'exportation)*

> **Astuce** : La fonction de traçabilité fournit un suivi d'utilisation des identifiants à des fins d'audit de sécurité.

### 2.9.3 Suppression d'Identifiants

![Credential deletion walkthrough](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(Vidéo: Deleting a credential)*

1. Sélectionnez l'enregistrement que vous souhaitez supprimer.
2. Cliquez sur le bouton rouge **{{t:common.delete}}**.

![Bouton Supprimer](/assets/images/user-guide/85_credentials_delete.png)
*(Figure 85 : Bouton rouge "Supprimer" sur la page Identifiants)*

3. Cliquez sur le bouton **{{t:common.delete}}** dans la fenêtre de confirmation.

![Confirmation de suppression](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(Figure 86 : Dialogue de confirmation de suppression - avertissement d'action irréversible)*

> **Avertissement** : Avant de supprimer, assurez-vous que l'identifiant n'est pas utilisé sur d'autres machines ou dans d'autres opérations. Assurez-vous d'avoir une sauvegarde des identifiants critiques avant de supprimer.

---

## 2.10 File d'Attente

La section File d'Attente vous permet de suivre les opérations en attente et terminées dans le système.

### 2.10.1 Opérations de File d'Attente

![Queue operations walkthrough](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(Vidéo: Managing queue operations)*

1. Cliquez sur l'onglet **{{t:common.navigation.queue}}** depuis le menu de gauche.

![Page File d'Attente](/assets/images/user-guide/87_queue_button.png)
*(Figure 87 : Page File d'Attente - options de filtrage et onglets de statut)*

2. Pour filtrer les éléments de la file d'attente :
   - Utilisez les filtres **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}** et **{{t:queue.trace.bridge}}**
   - Spécifiez **{{t:system.audit.filters.dateRange}}**
   - Cochez l'option **{{t:queue.filters.onlyStale}}**

3. Visualisez les détails dans les onglets de statut :
   - **{{t:queue.statusActive}}** : Tâches en cours de traitement
   - **{{t:queue.statusCompleted}}** : Tâches terminées avec succès
   - **{{t:queue.statusCancelled}}** : Tâches annulées
   - **{{t:queue.statusFailed}}** : Tâches échouées

4. Sélectionnez un format depuis le bouton **{{t:common.actions.export}}** : **{{t:common.exportCSV}}** ou **{{t:common.exportJSON}}**.

![Exportation de la file d'attente](/assets/images/user-guide/88_queue_export.png)
*(Figure 88 : Liste de la file d'attente - Options d'exportation)*

> **Astuce** : L'option "{{t:queue.filters.onlyStale}}" aide à trouver les tâches qui sont en cours de traitement depuis longtemps. Exportez régulièrement l'historique de la file d'attente pour analyser les tendances d'exécution des tâches.

---

## 2.11 Audit

La section Audit conserve les enregistrements de toutes les opérations effectuées dans le système.

### 2.11.1 Enregistrements d'Audit

![Audit records walkthrough](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(Vidéo: Viewing system audit records)*

1. Cliquez sur l'onglet **{{t:common.navigation.audit}}** depuis le menu de gauche.

![Liste d'audit](/assets/images/user-guide/89_audit_list.png)
*(Figure 89 : Page Audit - enregistrement détaillé de toutes les opérations système)*

2. Filtrez les enregistrements d'audit :
   - **Plage de dates** : Filtrez pour une période spécifique
   - **Type d'entité** : Filtrez par Requête, Machine, File d'attente, etc.
   - **Recherche** : Effectuez une recherche textuelle

3. Consultez les informations pour chaque enregistrement :
   - **Horodatage** : Date et heure de l'opération
   - **Action** : Type d'opération (Créer, Modifier, Supprimer, etc.)
   - **Type d'entité** : Type d'objet affecté
   - **Nom de l'entité** : Identifiant d'objet spécifique
   - **Utilisateur** : Utilisateur ayant effectué l'opération
   - **Détails** : Informations supplémentaires sur l'opération

4. Sélectionnez un format depuis le bouton **{{t:common.actions.export}}** : **{{t:common.exportCSV}}** ou **{{t:common.exportJSON}}**.

![Exportation d'audit](/assets/images/user-guide/90_audit_export.png)
*(Figure 90 : Exportation d'enregistrement d'audit - options CSV et JSON)*

> **Astuce** : L'enregistrement d'audit est essentiel pour suivre toute l'activité du système à des fins de sécurité et de conformité. Exportez régulièrement l'enregistrement d'audit et stockez-le dans un emplacement sécurisé.

---

**© 2025 Plateforme Rediacc – Tous Droits Réservés.**
