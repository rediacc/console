---
title: Time Travel Recovery
description: Recover accidentally deleted data from weeks ago with snapshot-based time travel.
category: Use Cases
order: 2
language: en
---

> **When Others Lose Data Forever, You Can Travel Back In Time.**

**Note:** This is a **use case example** demonstrating how Rediacc can solve this problem. As a startup, these scenarios represent potential applications rather than completed case studies.

**Crisis Scenario:** A newly hired employee **accidentally deleted** critical data from the live database 3 weeks ago. The organization's backup system only kept backups for 2 weeks, making data recovery nearly impossible through conventional means.

## The Problem

Mehmet is a system expert responsible for the database of a large online shopping organization. One morning, upon customer complaints, he notices that some past order records **are not visible** in the system. The investigation reveals that a newly hired employee **accidentally deleted** some critical data from the live database 3 weeks ago, **connecting to the live database instead of the test environment**.

**Existing Backup System:**
* Full backups are taken once a week
* **Incremental backups** are recorded daily

**Dilemma:** The deletion took place **before the date of the full backups**, so the lost data is not in the backups. Daily backups **only record the latest data**, so **deleted items cannot be recovered**.

## Crisis Impact

Due to lost data:
* Customers **cannot process refund requests**
* Inconsistencies occur in the payment system
* Complaints spread rapidly on social media

**Results:**
* The customer support team is under **intense pressure**
* The organization's reputation is **rapidly damaged**
* Manual data recovery efforts achieve **only 15% success**

**Additional Challenge:**
* To reduce storage costs, the organization keeps **only the last 2 weeks of backups**
* The deleted data is not in the **recent backups**

## Rediacc Solution

Mehmet offers a "time machine"-like solution with Rediacc:

### 1. **Snapshots**
* Rediacc automatically takes snapshots of the system every hour
* These snapshots also cover the moments just before the data was deleted

### 2. **Going Back in Time**
* Mehmet selects the date and time when the deletion occurred in the Rediacc interface
* Restores a snapshot of the system from 3 weeks ago to a new instance in 1 minute

### 3. **Complete Recovery**
* Lost data is restored completely and consistently

## Result

* The organization's reputation was repaired **within 24 hours**
* Financial loss was prevented by **95%**
* Rediacc proved that frequent backups could be made **without increasing storage costs**
