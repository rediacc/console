---
title: Risk-Free Upgrades
description: Test database upgrades without risk using instant cloning and hourly snapshots.
category: Use Cases
order: 4
language: en
---

> **Test Everything. Risk Nothing. Upgrade With Confidence.**

**Note:** This is a **use case example** demonstrating how Rediacc can solve this problem. As a startup, these scenarios represent potential applications rather than completed case studies.

**Crisis Scenario:** During a database upgrade, an **unexpected error** occurred that prevented reverting to the old version or proceeding to the new one. Customers couldn't access systems, and 5000+ employees couldn't work.

## The Problem

Mehmet is an experienced system administrator who manages large-scale databases. He decides to **upgrade a 100 TB PostgreSQL database from version 13 to 14**. His plan:

1. **Take a backup** → However, backing up takes **several days** due to data size
2. **Perform the upgrade on the weekend** → Departments are notified of an outage on **Saturday 01:00-05:00**

## Crisis Impact

* An **unexpected error** occurs during the upgrade
* The database **can neither revert to the old version nor proceed to the new version**
* Even external support teams cannot solve the problem

**Impacts:**
* Customers **cannot access payment and order systems**
* Organization employees (**5000+ people**) cannot work
* **Reputation loss** and increasing complaints begin

**Temporary Solution:**
* The last backup is loaded onto **a new server** → **Hardware cost doubles**
* Thursday and Friday data are **only in the live environment**, so data loss occurs
* **Two databases with different versions** are created → Inconsistencies increase

## Rediacc Solution

Mehmet solves the problem fundamentally with Rediacc:

### 1. **Instant Cloning**
* A **clone of the 100 TB database is created within seconds**
* Upgrade tests are performed **without affecting the live system**

### 2. **Hourly Snapshots**
* It is determined **which step has been failing since when** during the upgrade process
* Problematic operations are **identified in advance** and corrected

### 3. **Seamless Upgrade**
* If the upgrade fails, **the live environment is not affected**
* If the upgrade succeeds, the new live environment becomes the latest clone

## Result

**Time and Cost Savings:**
* Backup time was reduced from **7 days to 10 seconds**

**Risk-Free Upgrade:**
* Errors were detected in advance in the test environment → **No problems in the live system**

**Zero Downtime:**
* Customers and employees **felt no disruption**
