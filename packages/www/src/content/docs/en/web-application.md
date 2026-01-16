---
title: Web Application
description: Understanding web application architecture and deployment with Rediacc.
category: Core Concepts
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

To start using the Rediacc platform, you first need to create an account.

![Rediacc login page - always-on infrastructure](/assets/images/UserGuideEng/01_login.png)
*(Figure 1: Main login page, showing the Rediacc platform's main features)*

1. Navigate to [https://www.rediacc.com/](https://www.rediacc.com/) in your browser.
2. Click the **Login** button in the top right corner of the page.
3. Choose **Get Started** for free access or **Request Demo** for a demonstration.

> **Tip**: You can create a free account without requiring any credit card. Includes 10 CPU cores and unlimited teams.

![Rediacc Sign In form - email and password fields](/assets/images/UserGuideEng/02_register.png)
*(Figure 2: Sign In screen for existing users)*

4. If you don't have an account, click the **Register** link to create a new account.

5. Fill in the following information in the form that opens:
   - **Company Name**: Enter your organization name
   - **Email**: Enter a valid email address
   - **Password**: Create a password with at least 8 characters
   - **Confirm Password**: Re-enter the same password

![Create Account modal - register, verify, and complete steps](/assets/images/UserGuideEng/03_create_account.png)
*(Figure 3: New user registration step-by-step form - Register > Verify > Complete)*

6. Check the box to accept the terms of service and privacy policy.
7. Click the **Create Account** button.

> **Tip**: Password must be at least 8 characters and should be strong. All fields are required.

8. Enter the 6-digit verification code sent to your email in the boxes sequentially.
9. Click the **Verify Account** button.

![Verification code entry - 6-digit activation code](/assets/images/UserGuideEng/04_verification_code.png)
*(Figure 4: Window for entering the activation code sent to the administrator)*

> **Tip**: The verification code is valid for a limited time. If you don't receive the code, check your spam folder.

---

### 1.2 Signing In

After your account is created, you can log in to the platform.

1. Fill in the **Email** field (required if a red warning appears).
2. Fill in the **Password** field.
3. Click the **Sign In** button.

![Sign In form - required fields with error warning](/assets/images/UserGuideEng/05_sign_in.png)
*(Figure 5: Login form - error messages are marked with a red border)*

> **Tip**: If the error message says "This field is required", fill in the empty fields. Contact the administrator for forgotten passwords.

4. After successful login, you will be redirected to the **Dashboard** screen.

![Rediacc dashboard - machine list and sidebar menu](/assets/images/UserGuideEng/06_dashboard.png)
*(Figure 6: Main dashboard after successful login - Organization, Machines, and Settings menus in the left sidebar)*

> **Tip**: The dashboard auto-refreshes. You can refresh the page with F5 for fresh information.

---

## 2. Interface Overview

After logging in, the screen you see consists of these main sections:

- **Organization**: Users, teams, and access control
- **Machines**: Server and repository management
- **Settings**: Profile and system settings
- **Storage**: Storage area management
- **Credentials**: Access credentials
- **Queue**: Job queue management
- **Audit**: System audit logs

---

## 2.1 Organization - Users

User management allows you to control access to the platform for people in your organization.

### 2.1.1 Adding Users

1. Click **Organization** > **Users** option in the left sidebar.
2. View the list of all users in table format.
3. Each user row shows email, status (Active/Inactive), permission group, and last activity time.

![Users management page - active users list](/assets/images/UserGuideEng/07_users.png)
*(Figure 7: Users section under Organization - all users' information is displayed)*

4. Click the **"+"** icon in the top right corner.
5. Click the **Create User** button and fill in the form that opens:
   - **Email**: Enter the user's email address
   - **Password**: Enter a temporary password

![User creation modal - email and password fields](/assets/images/UserGuideEng/08_user_add.png)
*(Figure 8: Modal window for adding new user - simple and quick user creation form)*

6. Click the **Create** button.

> **Tip**: Login credentials should be securely communicated to the created user. Changing the password on first login is recommended.

![User list - full table view with three users](/assets/images/UserGuideEng/09_user_list.png)
*(Figure 9: All active and inactive users on the users management page)*

> **Tip**: The page automatically shows 20 records. Use pagination to see more records.

---

## 2.2 Organization - Teams

Teams allow you to group users and provide bulk access to resources.

### 2.2.1 Creating Teams

1. Go to **Organization** > **Teams** tab.
2. Click the **"+"** button.
3. Enter your team name in the **Team Name** field.
4. Fill in the **SSH Private Key** and **SSH Public Key** fields in the **Vault Configuration** section.

![New team creation form - team name and SSH keys](/assets/images/UserGuideEng/16_teams_create.png)
*(Figure 16: Creating a new team within "Private Team")*

5. Click the **Create** button to save the team.

> **Tip**: SSH keys are required for Bridge SSH authentication. If you receive a missing key warning, provide both keys.

---

## 2.4 Machines

The Machines section allows you to manage your servers and repository resources.

### 2.4.1 Adding Machines

1. Go to the **Machines** tab from the left menu.
2. Click the **Add Machine** button in the top right corner.

![Machines page - "Add Machine" button](/assets/images/UserGuideEng/23_machines_add.png)
*(Figure 23: Machines management home page)*

3. Fill in the form that opens:
   - **Machine Name**: Enter a unique name (e.g., "server-01")
   - **IP Address**: Enter the machine IP address (e.g., 192.168.111.11)
   - **Datastore Path**: Specify the storage directory (e.g., /mnt/rediacc)
   - **Username**: Enter the SSH username
   - **SSH Port**: Enter the port number (default: 22)
   - **SSH Password**: Enter the password (optional)

![Machine addition form - all fields](/assets/images/UserGuideEng/24_machine_create.png)
*(Figure 24: New machine addition form - machine name, network settings, SSH credentials)*

4. Click the **Test Connection** button to verify the connection.
5. After the test is successful, click the **Create** button.

> **Tip**: If "Automatically start setup after machine creation" option is checked, the machine will automatically perform additional setup steps.

---

## 2.5 Repository Creation and Operations

Repositories are the fundamental units where your backup data is stored.

### 2.5.1 Creating Repositories

1. Select a machine from the **Machines** tab.
2. Click the **Create Repository** button in the top right corner.

![Create Repository button](/assets/images/UserGuideEng/43_create_repo_add.png)
*(Figure 43: Machine repository management screen - Create Repository button)*

3. Fill in the form:
   - **Repository Name**: Enter the repository name (e.g., postgresql)
   - **Size**: Enter the repository size (e.g., 2GB)
   - **Credential ID**: View the automatically generated credential
   - **Select Template**: Choose a template (e.g., databases_postgresql)

![Repository creation form](/assets/images/UserGuideEng/44_repo_form.png)
*(Figure 44: Repository creation form - repository name, size, and template selection)*

4. Click the **Create** button.

> **Tip**: Credential ID is automatically generated, manual modification is not recommended.

---

## 2.8 Storage

The Storage section allows you to manage the physical areas where your backup data will be stored.

### 2.8.1 Adding Storage

1. Go to the **Storage** tab from the left menu.
2. Click the **Add Storage** button.

![Add Storage button](/assets/images/UserGuideEng/79_storage_add_button.png)
*(Figure 79: Storage management page - "Add Storage" button)*

3. Fill in the form:
   - **Storage Name**: Enter a descriptive name
   - **Storage Provider**: Select (e.g., s3)
   - **Description**: Add optional description
   - **Disable Versioning**: Optional
   - **Additional Parameters**: rclone flags (e.g., --transfers 4)

![Storage creation form](/assets/images/UserGuideEng/80_storage_form.png)
*(Figure 80: Add Storage form - name, provider, description, and parameters)*

4. Click the **Create** button.

> **Tip**: Additional Parameters accept rclone flags to optimize storage performance.

---

## 2.10 Queue

The Queue section allows you to track pending and completed operations in the system.

### 2.10.1 Queue Operations

1. Click the **Queue** tab from the left menu.

![Queue page](/assets/images/UserGuideEng/87_queue_button.png)
*(Figure 87: Queue page - filtering options and status tabs)*

2. To filter queue items:
   - Use **Team**, **Machine**, **Region**, and **Bridge** filters
   - Specify **Date range**
   - Check **Only Old Items** option

3. View details in status tabs:
   - **Active**: Tasks being processed
   - **Completed**: Successfully completed tasks
   - **Canceled**: Canceled tasks
   - **Failed**: Failed tasks

4. Select a format from the **Export** button: **CSV** or **JSON**.

![Queue export](/assets/images/UserGuideEng/88_queue_export.png)
*(Figure 88: Queue list - Export options)*

> **Tip**: The "Only Old Items" option helps find tasks that have been processing for a long time. Regularly export queue history to analyze task execution trends.

---

**© 2025 Rediacc Platform – All Rights Reserved.**
