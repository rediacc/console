---
title: Web Application
description: Understanding web application architecture and deployment with Rediacc
category: Reference
order: 1
language: en
---

# Rediacc Platform User Guide

## Overview

**Rediacc** is a cloud platform offering AI-powered backup services.

This guide explains the basic usage of the web interface at [https://www.rediacc.com/](https://www.rediacc.com/).

### Purpose of This Guide

- Help new users quickly adapt to the platform
- Explain basic functions (resource management, backup) step by step

---

## 1. Account Creation and Login

### 1.1 Registration

![Registration process walkthrough](/assets/videos/user-guide/01-01-registration.webm)
*(Video: Complete registration flow from start to finish)*

To start using the Rediacc platform, you first need to create an account.

![Rediacc login page - always-on infrastructure](/assets/images/user-guide/01_login.png)
*(Figure 1: Main login page, showing the Rediacc platform's main features)*

1. Navigate to [https://www.rediacc.com/](https://www.rediacc.com/) in your browser.
2. Click the **{{t:auth.login.signIn}}** button in the top right corner of the page.
3. Choose **Get Started** for free access or **Request Demo** for a demonstration.

> **Tip**: You can create a free account without requiring any credit card. Includes unlimited teams.

![Rediacc Sign In form - email and password fields](/assets/images/user-guide/02_register.png)
*(Figure 2: Sign In screen for existing users)*

4. If you don't have an account, click the **{{t:auth.login.register}}** link to create a new account.

5. Fill in the following information in the form that opens:
   - **{{t:auth.registration.organizationName}}**: Enter your organization name
   - **{{t:auth.login.email}}**: Enter a valid email address
   - **{{t:auth.login.password}}**: Create a password with at least 8 characters
   - **{{t:auth.registration.passwordConfirm}}**: Re-enter the same password

![Create Account modal - register, verify, and complete steps](/assets/images/user-guide/03_create_account.png)
*(Figure 3: New user registration step-by-step form - Register > Verify > Complete)*

6. Check the box to accept the terms of service and privacy policy.
7. Click the **{{t:auth.registration.createAccount}}** button.

> **Tip**: Password must be at least 8 characters and should be strong. All fields are required.

8. Enter the 6-digit verification code sent to your email in the boxes sequentially.
9. Click the **{{t:auth.registration.verifyAccount}}** button.

![Verification code entry - 6-digit activation code](/assets/images/user-guide/04_verification_code.png)
*(Figure 4: Window for entering the activation code sent to the administrator)*

> **Tip**: The verification code is valid for a limited time. If you don't receive the code, check your spam folder.

---

### 1.2 Signing In

![Sign in process walkthrough](/assets/videos/user-guide/01-02-login.webm)
*(Video: Complete sign in flow)*

After your account is created, you can log in to the platform.

1. Fill in the **{{t:auth.login.email}}** field (required if a red warning appears).
2. Fill in the **{{t:auth.login.password}}** field.
3. Click the **{{t:auth.login.signIn}}** button.

![Sign In form - required fields with error warning](/assets/images/user-guide/05_sign_in.png)
*(Figure 5: Login form - error messages are marked with a red border)*

> **Tip**: If the error message says "This field is required", fill in the empty fields. Contact the administrator for forgotten passwords.

4. After successful login, you will be redirected to the **{{t:common.navigation.dashboard}}** screen.

![Rediacc dashboard - machine list and sidebar menu](/assets/images/user-guide/06_dashboard.png)
*(Figure 6: Main dashboard after successful login - Organization, Machines, and Settings menus in the left sidebar)*

> **Tip**: The dashboard auto-refreshes. You can refresh the page with F5 for fresh information.

---

## 2. Interface Overview

After logging in, the screen you see consists of these main sections:

- **{{t:common.navigation.organization}}**: Users, teams, and access control
- **{{t:common.navigation.machines}}**: Server and repository management
- **{{t:common.navigation.settings}}**: Profile and system settings
- **{{t:common.navigation.storage}}**: Storage area management
- **{{t:common.navigation.credentials}}**: Access credentials
- **{{t:common.navigation.queue}}**: Job queue management
- **{{t:common.navigation.audit}}**: System audit logs

---

## 2.1 Organization - Users

User management allows you to control access to the platform for people in your organization.

### 2.1.1 Adding Users

![Adding users walkthrough](/assets/videos/user-guide/02-01-01-user-create.webm)
*(Video: Creating a new user)*

1. Click **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** option in the left sidebar.
2. View the list of all users in table format.
3. Each user row shows email, status ({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), permission group, and last activity time.

![Users management page - active users list](/assets/images/user-guide/07_users.png)
*(Figure 7: Users section under Organization - all users' information is displayed)*

4. Click the **"+"** icon in the top right corner.
5. Click the **{{t:organization.users.modals.createTitle}}** button and fill in the form that opens:
   - **{{t:organization.users.form.emailLabel}}**: Enter the user's email address
   - **{{t:organization.users.form.passwordLabel}}**: Enter a temporary password

![User creation modal - email and password fields](/assets/images/user-guide/08_user_add.png)
*(Figure 8: Modal window for adding new user - simple and quick user creation form)*

6. Click the **{{t:common.actions.create}}** button.

> **Tip**: Login credentials should be securely communicated to the created user. Changing the password on first login is recommended.

![User list - full table view with three users](/assets/images/user-guide/09_user_list.png)
*(Figure 9: All active and inactive users on the users management page)*

> **Tip**: The page automatically shows 20 records. Use pagination to see more records.

### 2.1.2 Assigning User Permissions

![User permissions walkthrough](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(Video: Assigning permission groups to users)*

You can manage access rights by assigning specific permission groups to users.

1. Select a user from the **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** tab.
2. Click the shield icon in the actions column (**{{t:organization.access.tabs.permissions}}**).

![Permission management - shield, gear, and delete icons](/assets/images/user-guide/10_users_permissions.png)
*(Figure 10: Icon display of user actions - each icon represents a different action)*

3. Select a **{{t:organization.users.modals.permissionGroupLabel}}** from the form that opens.
4. The number of users and permissions in the group is shown next to the user.
5. Click the **{{t:organization.users.modals.assignTitle}}** button to save the changes.

![Permission assignment modal - Administrators group](/assets/images/user-guide/11_user_permissions_form.png)
*(Figure 11: Modal for assigning permission group to selected user - dropdown with available groups)*

> **Tip**: Some permission groups are fixed by the system and cannot be changed.

### 2.1.3 User Activation

![User activation walkthrough](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(Video: Activating an inactive user)*

You can reactivate disabled users.

1. Find the user with inactive status in the **Users** list.
2. Click the red icon in the actions column.

![User activation - "Activate" tooltip view](/assets/images/user-guide/12_users_activation.png)
*(Figure 12: Activating an inactive user)*

3. Click the **{{t:common.general.yes}}** button in the confirmation window.

![Activation confirmation modal](/assets/images/user-guide/13_users_activation_confirm.png)
*(Figure 13: Modal window for confirming user activation)*

> **Tip**: This action is reversible. You can deactivate the user in the same way.

### 2.1.4 User Trace

![User trace walkthrough](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(Video: Viewing user activity trace)*

You can use the trace feature to monitor user activities.

1. Select a user and click the gear icon in the actions column.
2. Click the **{{t:common.actions.trace}}** option to open the user's activity history.

![User trace - "Trace" tooltip with action button](/assets/images/user-guide/14_users_trace.png)
*(Figure 14: User activity trace option)*

3. The user's past activities are listed on the opened screen.
4. Statistics are displayed at the top: Total Records, Viewed Records, Last Activity.
5. Click the **{{t:common.actions.export}}** button and select format: **{{t:common.exportCSV}}** or **{{t:common.exportJSON}}**.

![Audit History - Export options](/assets/images/user-guide/15_user_trace_export.png)
*(Figure 15: User's complete activity history - statistics, details, and Export options)*

> **Tip**: Regularly export audit data to maintain security and compliance records. CSV format can be opened in Excel.

---

## 2.2 Organization - Teams

Teams allow you to group users and provide bulk access to resources.

### 2.2.1 Creating Teams

![Creating teams walkthrough](/assets/videos/user-guide/02-02-01-team-create.webm)
*(Video: Creating a new team)*

1. Go to **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}** tab.
2. Click the **"+"** button.
3. Enter your team name in the **{{t:common.vaultEditor.fields.TEAM.name.label}}** field.
4. Fill in the **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** and **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** fields in the **{{t:common.vaultEditor.vaultConfiguration}}** section.

![New team creation form - team name and SSH keys](/assets/images/user-guide/16_teams_create.png)
*(Figure 16: Creating a new team within "Private Team")*

5. Click the **{{t:common.actions.create}}** button to save the team.

> **Tip**: SSH keys are required for Bridge SSH authentication. If you receive a missing key warning, provide both keys.

### 2.2.2 Team Editing

![Team editing walkthrough](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(Video: Editing team information)*

1. Click the pencil icon next to the team you want to edit in the teams list.
2. Change the team name in the **{{t:common.vaultEditor.fields.TEAM.name.label}}** field if needed.
3. Update SSH keys in the **{{t:common.vaultEditor.vaultConfiguration}}** section.
4. Click the **{{t:common.save}}** button to apply changes.

![Team editing form - blue info message](/assets/images/user-guide/17_teams_edit_form.png)
*(Figure 17: Editing an existing team's information)*

> **Tip**: Team configuration is used for organizational structure. Changes take effect for all team members.

### 2.2.3 Team Members Management

![Team members management walkthrough](/assets/videos/user-guide/02-02-03-team-members.webm)
*(Video: Managing team members)*

1. Select a team and click the user icon.
2. View members already assigned to the team in the **{{t:organization.teams.manageMembers.currentTab}}** tab.
3. Switch to the **{{t:organization.teams.manageMembers.addTab}}** tab.
4. Enter an email address or select a user from the dropdown.
5. Click the **"+"** button to add the member to the team.

![Team members management form - "Current Members" and "Add Member" tabs](/assets/images/user-guide/18_teams_members_form.png)
*(Figure 18: Team members management panel)*

> **Tip**: You can assign the same member to multiple teams.

### 2.2.4 Team Trace

![Team trace walkthrough](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(Video: Viewing team audit history)*

1. Select the team you want to trace.
2. Click the clock/history icon.
3. Review Total Records, Viewed Records, and Last Activity counts in the **{{t:resources.audit.title}}** modal.
4. Click the **{{t:common.actions.export}}** button to export in {{t:common.exportCSV}} or {{t:common.exportJSON}} format.

![Audit history modal - DataBassTeam team](/assets/images/user-guide/19_teams_trace.png)
*(Figure 19: Viewing team audit history)*

> **Tip**: Audit history is important for compliance and security control.

### 2.2.5 Team Deletion

![Team deletion walkthrough](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(Video: Deleting a team)*

1. Click the trash can (red) icon next to the team you want to delete.
2. Verify the team name is correct in the confirmation dialog.
3. Click the **{{t:common.general.yes}}** button.

![Team deletion confirmation dialog](/assets/images/user-guide/20_teams_delete.png)
*(Figure 20: Team deletion confirmation)*

> **Warning**: Team deletion is irreversible. Check if there is important data in the team before deleting.

---

## 2.3 Organization - Access Control

Access control allows you to centrally manage user permissions by creating permission groups.

### 2.3.1 Creating Permission Groups

![Permission group creation walkthrough](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(Video: Creating a permission group)*

1. Go to **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}** tab.
2. Click the **"+"** button.
3. Enter a meaningful name in the **{{t:organization.access.modals.groupPlaceholder}}** field.
4. Click the **{{t:common.actions.confirm}}** button to create the group.

![Permission group creation form](/assets/images/user-guide/21_create_access.png)
*(Figure 21: Creating a new Permission Group)*

> **Tip**: Permission groups are used to organize users with similar permissions. Keep group names descriptive (e.g., "Admin", "Read Only", "Repository Manager").

### 2.3.2 Permission Management

![Permission management walkthrough](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(Video: Managing permissions for a group)*

1. Select a Permission Group and click the **{{t:organization.access.modals.managePermissionsTitle}}** option.
2. View the group's access rights in the **{{t:organization.access.modals.currentPermissionsTab}}** tab.
3. You can revoke a permission by clicking the red **{{t:common.delete}}** button next to each action.
4. Click the **{{t:organization.access.modals.addPermissionsTab}}** tab to add new permissions to the group.

![Permission management panel - assigned permissions list](/assets/images/user-guide/22_access_permission.png)
*(Figure 22: Managing Permissions for Permission Group)*

> **Tip**: Grant permissions based on the principle of least privilege. Regularly review and remove unnecessary permissions.

---

## 2.4 Machines

The Machines section allows you to manage your servers and repository resources.

### 2.4.1 Adding Machines

![Adding machines walkthrough](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(Video: Adding a new machine)*

1. Go to the **{{t:common.navigation.machines}}** tab from the left menu.
2. Click the **{{t:machines.createMachine}}** button in the top right corner.

![Machines page - "Add Machine" button](/assets/images/user-guide/23_machines_add.png)
*(Figure 23: Machines management home page)*

3. Fill in the form that opens:
   - **{{t:machines.machineName}}**: Enter a unique name (e.g., "server-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: Enter the machine IP address (e.g., 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: Specify the storage directory (e.g., /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: Enter the SSH username
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: Enter the port number (default: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: Enter the password (optional)

![Machine addition form - all fields](/assets/images/user-guide/24_machine_create.png)
*(Figure 24: New machine addition form - machine name, network settings, SSH credentials)*

4. Click the **{{t:common.vaultEditor.testConnection.button}}** button to verify the connection.
5. After the test is successful, click the **{{t:common.actions.create}}** button.

> **Tip**: If "Automatically start setup after machine creation" option is checked, the machine will automatically perform additional setup steps.

![Machine creation completed - task tracking window](/assets/images/user-guide/25_machine_create_complete.png)
*(Figure 25: Task tracking window after machine is successfully created)*

6. Watch the stages: **{{t:queue.trace.assigned}}** → **Processing** → **{{t:queue.statusCompleted}}**
7. Click the **{{t:common.actions.close}}** button to close the operation.

> **Tip**: Click the "{{t:common.actions.refresh}}" button to manually check the latest status.

### 2.4.2 Connectivity Test

![Connectivity test walkthrough](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(Video: Running a connectivity test)*

You can check the connection status of existing machines.

1. Click the **{{t:machines.connectivityTest}}** button.

![Connectivity Test button](/assets/images/user-guide/26_connectivity_test_button.png)
*(Figure 26: Connectivity Test button in machine actions toolbar)*

2. See the list of machines to be tested.
3. Click the **{{t:machines.runTest}}** button.
4. Successful results are shown in green, failures in red.

![Connectivity test form - machine list](/assets/images/user-guide/27_connectivity_test_form.png)
*(Figure 27: Connectivity test form - ping function for selected machines)*

> **Tip**: If the test fails, check the machine IP address and SSH settings.

### 2.4.3 Refreshing Machine List

![Machine list refresh walkthrough](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(Video: Refreshing the machine list)*

Click the **{{t:common.actions.refresh}}** button to update the machine list.

![Refresh button](/assets/images/user-guide/28_refresh.png)
*(Figure 28: Refresh button in machine actions toolbar)*

### 2.4.4 Machine Details

![Machine details walkthrough](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(Video: Viewing machine details)*

1. Select the machine whose details you want to see.
2. Click the eye icon button (**{{t:common.viewDetails}}**).

![View Details button](/assets/images/user-guide/29_view_details_button.png)
*(Figure 29: Eye icon in machine actions column)*

3. The machine details panel opens on the right side:
   - **Hostname**: Machine name
   - **Uptime**: Running time
   - **{{t:queue.trace.operatingSystem}}**: OS and version
   - **{{t:queue.trace.kernelVersion}}**: Kernel version
   - **CPU**: Processor information
   - **System Time**: System clock

![Machine detail panel - system information](/assets/images/user-guide/30_machine_view_details.png)
*(Figure 30: Machine detail panel - hostname, uptime, OS, kernel, CPU information)*

> **Tip**: Regularly review this information to check OS compatibility and resource availability.

### 2.4.5 Machine Editing

![Machine editing walkthrough](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(Video: Editing machine settings)*

1. Select the machine you want to edit.
2. Click the pencil icon button (**{{t:common.actions.edit}}**).

![Edit button](/assets/images/user-guide/31_edit_button.png)
*(Figure 31: Pencil icon in machine actions column)*

3. Make the necessary changes.
4. Click the **{{t:common.vaultEditor.testConnection.button}}** button.
5. When the connection is successful, click the **{{t:common.save}}** button.

![Machine editing form](/assets/images/user-guide/32_edit_form.png)
*(Figure 32: Machine editing form - machine name, region, and vault configuration)*

> **Tip**: Always run "Test Connection" after changing critical settings.

### 2.4.6 Machine Trace

![Machine trace walkthrough](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(Video: Viewing machine audit history)*

1. Select the machine and click the clock icon button (**{{t:common.actions.trace}}**).

![Trace button](/assets/images/user-guide/33_trace_button.png)
*(Figure 33: Clock icon in machine actions column)*

2. Review operations in the audit history window:
   - **{{t:resources.audit.action}}**: Type of operation performed
   - **Details**: Changed fields
   - **{{t:resources.audit.performedBy}}**: User who performed the action
   - **Timestamp**: Date and time

![Machine audit history window](/assets/images/user-guide/34_trace_list.png)
*(Figure 34: Audit history - list of all changes)*

> **Tip**: Click the Timestamp column to view changes in chronological order.

### 2.4.7 Machine Deletion

![Machine deletion walkthrough](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(Video: Deleting a machine)*

1. Select the machine you want to delete.
2. Click the trash can icon button (**{{t:common.delete}}**).

![Delete button](/assets/images/user-guide/35_delete_button.png)
*(Figure 35: Trash can icon in machine actions column)*

3. Click the **{{t:common.delete}}** button in the confirmation window.

![Machine deletion confirmation window](/assets/images/user-guide/36_delete_form.png)
*(Figure 36: "Are you sure you want to delete this machine?" confirmation window)*

> **Warning**: When a machine is deleted, all repository definitions on it are also removed. This action is irreversible.

### 2.4.8 Remote Operations

![Remote operations walkthrough](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(Video: Running remote operations on a machine)*

You can perform various remote operations on machines.

1. Select the machine and click the **{{t:common.actions.remote}}** button.
2. See options in the dropdown menu:
   - **{{t:machines.runAction}}**: Execute function on machine
   - **{{t:common.vaultEditor.testConnection.button}}**: Ping the machine

![Remote menu - Run on Server and Test Connection](/assets/images/user-guide/37_remote_button.png)
*(Figure 37: Remote button - function execution menu on selected machine)*

> **Tip**: Use "{{t:common.vaultEditor.testConnection.button}}" option to verify the machine is accessible before running functions.

#### Setup

1. Select the **{{t:machines.runAction}}** option.
2. Find the **Setup** function in the **{{t:functions.availableFunctions}}** list.
3. Click on the function name to select it.

![Machine functions list - setup function](/assets/images/user-guide/38_server_setup.png)
*(Figure 38: Setup function - prepares the machine with required tools and configurations)*

> **Tip**: It's recommended to run the "setup" function first when setting up a new machine.

#### Connection Check (Hello)

1. Select **{{t:machines.runAction}}** > **Hello** function.
2. Click the **{{t:common.actions.addToQueue}}** button.

![Hello function selection](/assets/images/user-guide/39_remote_hello.png)
*(Figure 39: Hello function - simple test function, returns hostname)*

3. Watch the results in the task tracking window.
4. See the machine's output in the **{{t:queue.trace.responseConsole}}** section.

![Hello function completed](/assets/images/user-guide/40_remote_hello_complete.png)
*(Figure 40: Hello function completed successfully - hostname response)*

> **Tip**: The hello function is ideal for verifying machine connectivity.

#### Advanced Operations

1. Follow the **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}** path.
2. See available functions: setup, hello, ping, ssh_test, uninstall
3. Select the required function and click the **{{t:common.actions.addToQueue}}** button.

![Advanced functions list](/assets/images/user-guide/41_remote_advanced.png)
*(Figure 41: Advanced option - advanced functions list)*

> **Tip**: Make sure machine setup is complete before using Advanced functions.

#### Quick Connectivity Test

![Remote menu - Test Connection](/assets/images/user-guide/42_connectivity_test.png)
*(Figure 42: Test Connection option from Remote menu)*

> **Tip**: If the machine has SSH or network issues, you can quickly identify problems with this test.

---

## 2.5 Repository Creation and Operations

Repositories are the fundamental units where your backup data is stored.

### 2.5.1 Creating Repositories

![Repository creation walkthrough](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(Video: Creating a new repository)*

1. Select a machine from the **{{t:common.navigation.machines}}** tab.
2. Click the **{{t:machines.createRepository}}** button in the top right corner.

![Create Repository button](/assets/images/user-guide/43_create_repo_add.png)
*(Figure 43: Machine repository management screen - Create Repository button)*

3. Fill in the form:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: Enter the repository name (e.g., postgresql)
   - **{{t:resources.repositories.size}}**: Enter the repository size (e.g., 2GB)
   - **{{t:resources.repositories.repositoryGuid}}**: View the automatically generated credential
   - **{{t:resources.templates.selectTemplate}}**: Choose a template (e.g., databases_postgresql)

![Repository creation form](/assets/images/user-guide/44_repo_form.png)
*(Figure 44: Repository creation form - repository name, size, and template selection)*

4. Click the **{{t:common.actions.create}}** button.

> **Tip**: Credential ID is automatically generated, manual modification is not recommended.

5. Watch the stages in the task tracking window: **{{t:queue.trace.assigned}}** → **Processing** → **{{t:queue.statusCompleted}}**

![Repository creation completed](/assets/images/user-guide/45_repo_complete.png)
*(Figure 45: Repository creation queued - task monitoring)*

6. Click the **{{t:common.actions.close}}** button.

> **Tip**: The task typically completes within 1-2 minutes.

![Repository list](/assets/images/user-guide/46_repo_list.png)
*(Figure 46: Created repository appears in the list)*

### 2.5.2 Repository Fork

![Repository fork walkthrough](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(Video: Forking a repository)*

You can create a new repository by copying an existing one.

1. Select the repository you want to copy.
2. Click the **fx** (function) menu.
3. Click the **fork** option.

![fx menu - fork option](/assets/images/user-guide/47_fork_button.png)
*(Figure 47: fx menu on the right side - repository operations)*

4. Enter a new tag in the **{{t:functions.functions.fork.params.tag.label}}** field (e.g., 2025-12-06-20-37-08).
5. Click the **{{t:common.actions.addToQueue}}** button.

![Fork configuration form](/assets/images/user-guide/48_fork_form.png)
*(Figure 48: Specify the new tag for the repository in the fork operation)*

6. Wait for the **{{t:queue.statusCompleted}}** message and click the **{{t:common.actions.close}}** button.

![Fork completed](/assets/images/user-guide/49_repo_completed.png)
*(Figure 49: Fork operation completed successfully)*

> **Tip**: Creating tags in the default date-time format is good practice. The fork operation does not affect the original repository.

### 2.5.3 Repository Up

![Repository up walkthrough](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(Video: Starting a repository)*

To activate the repository:

1. Select the repository and follow the **fx** > **up** path.

![Up operation](/assets/images/user-guide/50_repo_up.png)
*(Figure 50: "up" option from fx menu - starting the repository)*

2. Wait for the **{{t:queue.statusCompleted}}** message.

![Up completed](/assets/images/user-guide/51_repo_up_complete.png)
*(Figure 51: Repository startup completed)*

> **Tip**: The "Up" operation starts the repository's defined Docker services.

### 2.5.4 Repository Down

![Repository down walkthrough](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(Video: Stopping a repository)*

To stop an active repository:

1. Select the repository and follow the **fx** > **down** path.

![Down operation](/assets/images/user-guide/52_down_button.png)
*(Figure 52: "down" option from fx menu - shutting down the repository)*

2. Wait for the **{{t:queue.statusCompleted}}** message.

![Down completed](/assets/images/user-guide/53_down_completed.png)
*(Figure 53: Repository shutdown completed)*

> **Tip**: The "Down" operation safely shuts down the repository. No data is lost, only services are stopped.

### 2.5.5 Deploy

![Repository deploy walkthrough](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(Video: Deploying a repository)*

To deploy the repository to a different location:

1. Select the repository and follow the **fx** > **deploy** path.

![Deploy operation](/assets/images/user-guide/54_deploy_button.png)
*(Figure 54: "deploy" option from fx menu)*

2. Enter the version to deploy in the **{{t:functions.functions.fork.params.tag.label}}** field.
3. Select target machines in the **{{t:functions.functions.backup_deploy.params.machines.label}}** field.
4. Check the **{{t:functions.checkboxOptions.overrideExistingFile}}** option (if applicable).
5. Click the **{{t:common.actions.addToQueue}}** button.

![Deploy form](/assets/images/user-guide/55_deploy_form.png)
*(Figure 55: Configuring deploy operation - tag, target machines, and options)*

6. Wait for the **{{t:queue.statusCompleted}}** message.

![Deploy completed](/assets/images/user-guide/56_deploy_completed.png)
*(Figure 56: Repository deployment completed)*

> **Tip**: After the deploy operation completes, you can run the "up" command to start the repository on target machines.

### 2.5.6 Backup

![Repository backup walkthrough](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(Video: Backing up a repository)*

To backup the repository:

1. Select the repository and follow the **fx** > **backup** path.

![Backup operation](/assets/images/user-guide/57_backup_button.png)
*(Figure 57: "backup" option from fx menu)*

2. Fill in the form:
   - **{{t:functions.functions.fork.params.tag.label}}**: Enter a descriptive name (e.g., backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}**: Select the backup location
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: Enable or disable the option
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: Review the setting

![Backup form](/assets/images/user-guide/58_backup_form.png)
*(Figure 58: Backup configuration form - target, filename, and options)*

3. Click the **{{t:common.actions.addToQueue}}** button.

> **Tip**: Use a descriptive name for the backup tag. Consider enabling checkpoint for large repositories.

4. Wait for the **{{t:queue.statusCompleted}}** message.

![Backup completed](/assets/images/user-guide/59_backup_completed.png)
*(Figure 59: Backup task completed successfully)*

> **Tip**: Wait patiently before reaching completed status; large backups may take several minutes.

### 2.5.7 Template Application

![Template application walkthrough](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(Video: Applying a template to a repository)*

To apply a new template to the repository:

1. Select the repository and follow the **fx** > **{{t:resources.templates.selectTemplate}}** path.

![Templates operation](/assets/images/user-guide/60_templates_button.png)
*(Figure 60: "Templates" option from fx menu)*

2. Filter templates by typing in the search box.
3. Click on the desired template to select it (selected template is highlighted with a bold border).
4. Click the **{{t:common.actions.addToQueue}}** button.

![Template selection form](/assets/images/user-guide/61_templates_form.png)
*(Figure 61: Searching and selecting available templates)*

> **Tip**: Use the search box to quickly find templates. Use "{{t:common.viewDetails}}" to learn about template features.

5. Wait for the **{{t:queue.statusCompleted}}** message.

![Template applied](/assets/images/user-guide/62_templates_completed.png)
*(Figure 62: Template application completed successfully)*

### 2.5.8 Unmount

![Repository unmount walkthrough](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(Video: Unmounting a repository)*

To disconnect the repository:

1. Select the repository and follow the **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}** path.

![Unmount operation](/assets/images/user-guide/63_unmount_button.png)
*(Figure 63: "Unmount" option in the advanced menu)*

2. Wait for the **{{t:queue.statusCompleted}}** message.

![Unmount completed](/assets/images/user-guide/64_unmount_completed.png)
*(Figure 64: Unmount operation completed)*

> **Tip**: Make sure there are no active operations on the repository before unmounting. After unmounting, the repository becomes inaccessible.

### 2.5.9 Expand

![Repository expand walkthrough](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(Video: Expanding repository size)*

To increase the repository size:

1. Select the repository and follow the **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}** path.

![Expand operation](/assets/images/user-guide/65_expand_button.png)
*(Figure 65: "Expand" option in the advanced menu)*

2. Enter the desired size in the **{{t:functions.functions.repository_expand.params.size.label}}** field.
3. Select the unit from the dropdown on the right (GB, TB).
4. Click the **{{t:common.actions.addToQueue}}** button.

![Expand form](/assets/images/user-guide/66_expand_form.png)
*(Figure 66: New size parameter to increase repository size)*

> **Tip**: Do not enter a value smaller than the current size. Service is not interrupted during repository expansion.

5. Wait for the **{{t:queue.statusCompleted}}** message.

![Expand completed](/assets/images/user-guide/67_expand_completed.png)
*(Figure 67: Repository expansion completed)*

### 2.5.10 Rename

![Repository rename walkthrough](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(Video: Renaming a repository)*

To change the repository name:

1. Select the repository and follow the **fx** > **{{t:common.actions.rename}}** path.

![Rename operation](/assets/images/user-guide/68_rename_button.png)
*(Figure 68: "Rename" option from fx menu)*

2. Enter the new repository name.
3. Click the **{{t:common.save}}** button.

![Rename form](/assets/images/user-guide/69_rename_form.png)
*(Figure 69: Dialog for entering new repository name)*

> **Tip**: Repository names should be meaningful to reflect the repository type and purpose. Avoid special characters.

### 2.5.11 Repository Deletion

![Repository deletion walkthrough](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(Video: Deleting a repository)*

To permanently delete the repository:

1. Select the repository and follow the **fx** > **{{t:resources.repositories.deleteRepository}}** path.

![Delete Repository operation](/assets/images/user-guide/70_delete_repo_button.png)
*(Figure 70: "Delete Repository" option from fx menu - red)*

2. Click the **{{t:common.delete}}** button in the confirmation window.

> **Warning**: Repository deletion is irreversible. Make sure repository data is backed up before deleting.

### 2.5.12 Repository Details

![Repository details walkthrough](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(Video: Viewing repository details)*

To get detailed information about the repository:

1. Select the repository.
2. Click the eye icon (**{{t:common.viewDetails}}**).

![View Details button](/assets/images/user-guide/71_repo_view_button.png)
*(Figure 71: Eye icon to open repository details)*

3. Review information in the detail panel:
   - **Repository name** and type
   - **Team**: The team it belongs to
   - **Machine**: The machine it's on
   - **Vault Version**: Encryption version
   - **Repository GUID**: Unique identifier
   - **Status**: Mounted/Unmounted status
   - **Image Size**: Total size
   - **Last Modified**: Last modification date

![Repository detail panel](/assets/images/user-guide/72_repo_details_view.png)
*(Figure 72: Comprehensive information about the selected repository)*

> **Tip**: All information shown in this panel is for reference. Use fx menu options for repository operations.

---

## 2.6 Repository Connection Operations

You can connect to repositories using different methods.

### 2.6.1 Desktop Application Connection

![Desktop connection walkthrough](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(Video: Connecting via desktop application)*

1. Click the **{{t:resources.localActions.local}}** button in the repository row.

![Local connection button](/assets/images/user-guide/73_repo_connection_local.png)
*(Figure 73: "Local" button in repository row - desktop application access)*

2. Select the access method from the dropdown menu:
   - **{{t:resources.localActions.openInDesktop}}**: Access with graphical interface
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: Open in code editor
   - **{{t:common.terminal.terminal}}**: Access via command line
   - **{{t:resources.localActions.showCLICommands}}**: Command line tools

![Connection options menu](/assets/images/user-guide/74_repo_connection.png)
*(Figure 74: Repository connection menu - different access paths)*

> **Tip**: If working with VS Code, the "{{t:resources.localCommandBuilder.vscodeTab}}" option provides the fastest integration.

3. Click the **{{t:common.vscodeSelection.open}}** button when the browser requests permission.

![Desktop application open permission](/assets/images/user-guide/75_desktop_open_page.png)
*(Figure 75: Browser asking for permission to open desktop application)*

> **Tip**: If you don't want to grant permission every time you open the desktop application, check the "Always allow" option.

---

## 2.7 Settings

You can manage your profile and system settings from the Settings section.

### 2.7.1 Password Change

![Password change walkthrough](/assets/videos/user-guide/02-07-03-password-change.webm)
*(Video: Changing your password)*

1. Go to **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}** tab from the left menu.

![Profile settings page](/assets/images/user-guide/76_profiles_button.png)
*(Figure 76: Settings → Profile page - personal vault settings)*

2. Click the **{{t:settings.personal.changePassword.submit}}** button.

![Change Password button](/assets/images/user-guide/77_profiles_change_button.png)
*(Figure 77: "Change Password" button in personal settings section)*

3. Enter your new password. Password requirements:
   - At least 8 characters long
   - Must contain uppercase and lowercase letters
   - Must contain at least one number
   - Must contain at least one special character

4. Re-enter the same password in the **{{t:settings.personal.changePassword.confirmPasswordLabel}}** field.
5. Click the **{{t:settings.personal.changePassword.submit}}** button.

![Password change form](/assets/images/user-guide/78_profiles_change_form.png)
*(Figure 78: Change Password form - security requirements visible)*

> **Tip**: Use random combinations when creating a strong password.

---

## 2.8 Storage

The Storage section allows you to manage the physical areas where your backup data will be stored.

### 2.8.1 Adding Storage

![Storage creation walkthrough](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(Video: Adding a storage location)*

1. Go to the **{{t:common.navigation.storage}}** tab from the left menu.
2. Click the **{{t:resources.storage.createStorage}}** button.

![Add Storage button](/assets/images/user-guide/79_storage_add_button.png)
*(Figure 79: Storage management page - "Add Storage" button)*

3. Fill in the form:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: Enter a descriptive name
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: Select (e.g., s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: Add optional description
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: Optional
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: rclone flags (e.g., --transfers 4)

![Storage creation form](/assets/images/user-guide/80_storage_form.png)
*(Figure 80: Add Storage form - name, provider, description, and parameters)*

4. Click the **{{t:common.actions.create}}** button.

> **Tip**: Additional Parameters accept rclone flags to optimize storage performance.

---

## 2.9 Credentials

The Credentials section allows you to securely manage access information for your repositories.

### 2.9.1 Credential Editing

![Credential editing walkthrough](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(Video: Editing credentials)*

1. Go to the **{{t:common.navigation.credentials}}** tab from the left menu.
2. Select the record you want to edit.
3. Click the **{{t:common.actions.edit}}** button.

![Credentials list](/assets/images/user-guide/81_credentials.png)
*(Figure 81: Credentials page - repository names, teams, and management buttons)*

4. Change the **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}** if needed.
5. Save with the **{{t:common.save}}** button.

![Credential editing form](/assets/images/user-guide/82_credentials_form.png)
*(Figure 82: Edit Repository Name form - vault configuration fields)*

> **Tip**: Credentials are stored encrypted and only decrypted during deployment.

### 2.9.2 Credential Trace

![Credential trace walkthrough](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(Video: Viewing credential audit history)*

1. Select the record you want to trace.
2. Click the **{{t:common.actions.trace}}** button.

![Trace button](/assets/images/user-guide/83_credentials_trace_button.png)
*(Figure 83: "Trace" button in Credentials table)*

3. Review the audit history.
4. Select format from the **{{t:common.actions.export}}** button: **{{t:common.exportCSV}}** or **{{t:common.exportJSON}}**.

![Credential audit history](/assets/images/user-guide/84_credentials_list_export.png)
*(Figure 84: Credentials list - Export options)*

> **Tip**: The trace feature provides usage tracking of credentials for security audit purposes.

### 2.9.3 Credential Deletion

![Credential deletion walkthrough](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(Video: Deleting a credential)*

1. Select the record you want to delete.
2. Click the red **{{t:common.delete}}** button.

![Delete button](/assets/images/user-guide/85_credentials_delete.png)
*(Figure 85: Red "Delete" button on Credentials page)*

3. Click the **{{t:common.delete}}** button in the confirmation window.

![Deletion confirmation](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(Figure 86: Deletion confirmation dialog - irreversible action warning)*

> **Warning**: Before deleting, make sure the credential is not being used on other machines or in other operations. Ensure you have a backup of critical credentials before deleting.

---

## 2.10 Queue

The Queue section allows you to track pending and completed operations in the system.

### 2.10.1 Queue Operations

![Queue operations walkthrough](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(Video: Managing queue operations)*

1. Click the **{{t:common.navigation.queue}}** tab from the left menu.

![Queue page](/assets/images/user-guide/87_queue_button.png)
*(Figure 87: Queue page - filtering options and status tabs)*

2. To filter queue items:
   - Use **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}**, and **{{t:queue.trace.bridge}}** filters
   - Specify **{{t:system.audit.filters.dateRange}}**
   - Check **{{t:queue.filters.onlyStale}}** option

3. View details in status tabs:
   - **{{t:queue.statusActive}}**: Tasks being processed
   - **{{t:queue.statusCompleted}}**: Successfully completed tasks
   - **{{t:queue.statusCancelled}}**: Cancelled tasks
   - **{{t:queue.statusFailed}}**: Failed tasks

4. Select a format from the **{{t:common.actions.export}}** button: **{{t:common.exportCSV}}** or **{{t:common.exportJSON}}**.

![Queue export](/assets/images/user-guide/88_queue_export.png)
*(Figure 88: Queue list - Export options)*

> **Tip**: The "{{t:queue.filters.onlyStale}}" option helps find tasks that have been processing for a long time. Regularly export queue history to analyze task execution trends.

---

## 2.11 Audit

The Audit section maintains records of all operations performed in the system.

### 2.11.1 Audit Records

![Audit records walkthrough](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(Video: Viewing system audit records)*

1. Click the **{{t:common.navigation.audit}}** tab from the left menu.

![Audit list](/assets/images/user-guide/89_audit_list.png)
*(Figure 89: Audit page - detailed record of all system operations)*

2. Filter audit records:
   - **Date Range**: Filter for a specific period
   - **Entity Type**: Filter by Request, Machine, Queue, etc.
   - **Search**: Perform text search

3. Review information for each record:
   - **Timestamp**: Date and time of the operation
   - **Action**: Type of operation (Create, Edit, Delete, etc.)
   - **Entity Type**: Type of object affected
   - **Entity Name**: Specific object identifier
   - **User**: User who performed the operation
   - **Details**: Additional information about the operation

4. Select a format from the **{{t:common.actions.export}}** button: **{{t:common.exportCSV}}** or **{{t:common.exportJSON}}**.

![Audit export](/assets/images/user-guide/90_audit_export.png)
*(Figure 90: Audit record export - CSV and JSON options)*

> **Tip**: The audit record is critical for tracking all system activity for security and compliance purposes. Regularly export the audit record and store it in a secure location.

---

**© 2025 Rediacc Platform – All Rights Reserved.**
