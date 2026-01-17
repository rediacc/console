---
title: "CLI API Reference"
description: "Complete API reference documentation for the Rediacc CLI."
category: "CLI API Reference"
language: "en"
---

# CLI API Reference

Complete API reference documentation for the Rediacc CLI.

## Command Categories

### [Audit](./audit)
Audit logging and compliance commands.

### [Authentication](./auth)
Authentication and session management commands.

### [Bridge](./bridge)
Bridge management and operations.

### [Clone](./clone)
Clone resources and configurations.

### [Organization](./organization)
Organization management commands.

### [Create](./create)
Create new resources in the system.

### [Ceph](./ceph)
Manage Ceph clusters and pools.

### [Inspect](./inspect)
Inspect resources and their details.

### [List](./list)
List and view resources.

### [Machine](./machine)
Machine-specific operations.

### [Miscellaneous](./misc)
Other commands and utilities.

### [Permissions](./permissions)
Manage user and resource permissions.

### [Queue](./queue)
Queue management and operations.

### [Region](./region)
Region management commands.

### [Remove](./rm)
Remove/delete resources from the system.

### [Team](./team)
Team management commands.

### [Team Members](./team-members)
Manage team membership.

### [Update](./update)
Update existing resources.

### [User](./user)
User management commands.

### [Vault](./vault)
Manage encrypted vault data for resources.

## Quick Links

- [Authentication](./auth) - Login and logout commands
- [Create](./create) - Create new resources
- [List](./list) - List and view resources
- [Update](./update) - Update existing resources
- [Remove](./rm) - Delete resources
- [Vault](./vault) - Manage encrypted configurations

## Getting Started

To use the CLI, first authenticate:

```bash
rediacc login
```

Then you can use any of the documented commands. Most commands require authentication and will use the stored token from your login session.
