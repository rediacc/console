---
title: Time Travel Recovery
description: "Recover data deleted weeks ago using btrfs snapshots, even after your normal backups have rolled past it."
category: Use Cases
order: 2
language: en
---

> **When Others Lose Data Forever, You Can Travel Back In Time.**

**Note:** This is a **use case example** showing how Rediacc handles this kind of problem. We're a startup. These are realistic scenarios the product is built for, not customer case studies we've already shipped.

**Crisis Scenario:** A new hire **accidentally deleted** critical rows from your live database 3 weeks ago. Your backup system only keeps 2 weeks of history. With a normal setup, that data is gone.

## The Problem

Mehmet runs the database for a large e-commerce platform. One morning customers start complaining that past order records **are not visible** anymore. He investigates. A newly hired engineer had **accidentally deleted** critical rows from the live database 3 weeks ago, **connecting to the live database instead of the test environment**. The classic mistake every DBA has either made themselves or watched a junior make.

**Existing Backup System:**
* Full backups are taken once a week
* **Incremental backups** are recorded daily

**The dilemma:** the deletion happened **before the date of the full backups**, so the lost data isn't in any backup file. The daily backups **only record the latest data**, so **deleted items cannot be recovered**.

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

Here's the time-machine setup Mehmet builds with Rediacc:

![Time Travel Recovery](/img/time-travel-recovery.svg)

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
