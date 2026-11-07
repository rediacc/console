---
title: "Backup Destinations"
description: "Send each backup strategy to more than one store, restore from the store that holds the best snapshot, and read one status row per destination."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: en
---

# Backup Destinations

A backup strategy can write to more than one store. Each destination is a separate recovery point: it gets its own snapshot, its own commit and its own status row, so a store that fails never spoils another one.

All stores belong to one account. One config, one licence and one bill cover them. A machine signed in to two accounts keeps the existing refusal, because several destinations means several stores inside one account.

## Stores

A store is a bucket the account server writes to on the machine's behalf. Every subscription has one from the first day, named `home`: the hosted store the backup verbs have always used. A destination that names no store writes to `home`.

Two kinds can be registered besides it.

| Kind | What it is | What registration takes |
|------|------------|-------------------------|
| `hosted-r2` | A second hosted region, chosen from the regions the deployment offers | An id and the region. No credentials |
| `customer-s3` | A bucket the customer runs, on S3, RustFS or any S3-compatible service | An id, the HTTPS endpoint, the bucket, the signing region (default `us-east-1`), an optional public endpoint, and one access key pair |

A machine never holds the keys of a customer bucket. The keys live on the account server, sealed, and the machine receives short-lived presigned URLs for the one store its session names.

### Registering a store

Registration is a call to the account API, not an `rdc` command. `POST /backups/stores` registers a store, `GET /backups/stores` lists the registered ones, and `DELETE /backups/stores/<id>` retires one. Registering, rotating and retiring take an API token with the `backup:manage` scope that was created by a current organization owner or admin, and each is audited. Listing needs `backup:read`.

The server checks a store before it accepts it.

- **Conformance probe.** The server runs the same checks a hosted store passes. A store that does not enforce checksums is refused at registration rather than found out at the first backup.
- **Delete probe.** The probe also tries a delete. When the store refuses it, the store is registered with clean-up disabled (see below).
- **Endpoint rules.** HTTPS only, port 443, and no endpoint on an internal network.
- **Store limit.** The number of stores per subscription depends on the plan, `home` included and retired stores not counted.

| Plan | Stores |
|------|--------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

Registering an id that already exists rotates its credentials and nothing else, and the probe runs again. A store whose credentials stop working is marked suspended by the first refused grant. `GET /backups/stores` shows the endpoint, the bucket and the last characters of the key id, never a secret.

A store cannot be retired while an enabled destination still names it, and `home` cannot be retired.

## Naming a destination's store

A destination names its store with `--target`, which is used together with `--destination`:

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| Option | Description |
|--------|-------------|
| `--destination <name>` | The destination to create or change |
| `--target <storeId>` | Registered store id the destination writes to (default `home`). Needs `--destination` |

Two enabled destinations of one strategy cannot name the same store, and a store that is not registered is refused with the list of registered ids.

Each scheduled run takes one snapshot per enabled destination, in the order the destinations were declared, each with its own bandwidth cap. Every snapshot is a fresh copy-on-write reflink, so each one is a consistent point in time of its own. A destination that fails does not skip the next one. The unit still exits non-zero when any destination failed, so systemd and the missed-run check see the failure.

## Restoring from a store

`rdc backup restore`, `rdc backup restore --path`, `rdc backup browse --at` and `rdc backup download --store` accept `--from <storeId>`:

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

Without `--from`, the CLI asks the account server which stores hold the repository's lineage, ranked with the store whose newest snapshot passed its last verify first, and tries them in that order. A store with no snapshot is skipped. If the ranking cannot be read, the restore uses `home` and says so.

The whole-image restore falls back to the next store when a failure belongs to the store: a server error, a refused grant or session, or an endpoint that does not answer. It says which store served the restore. It never falls back for a fault of the snapshot itself. A missing, expired or corrupt snapshot looks the same in every store, so the error is shown instead. A restore with `--from` never falls back. `restore --path`, `browse --at` and `download --store` read the first store and do not fall back.

A snapshot id given without `--from` is looked up across the lineage's stores.

## Status per destination

`rdc backup status` prints one row per destination alongside the schedule table:

| Column | Meaning |
|--------|---------|
| Store | The store id the destination writes to |
| Last run | When the last run for that store finished |
| Result | The outcome of that run |
| Newest snapshot | The most recent snapshot the store holds |
| Verify | The result of the store's last verify |
| Clean-up | `enabled`, or disabled with the reason |

A store the account cannot report on shows `-` in its columns. The missed-run check runs per store, so a store that stopped receiving backups raises its own alarm while the others stay green.

## What counts toward the quota

Hosted stores, `home` and any second region, are metered by physical unique stored bytes, and their bytes count toward the same plan quota. `rdc backup usage` shows them.

The bytes of a customer bucket are not stored by Rediacc and are not counted toward the quota. The metadata the account keeps for it (manifest rows, verify runs and index objects) is metered like a hosted store's.

## Stores with clean-up disabled

A store whose delete is refused keeps every object. Retention and garbage collection never delete from it. When a snapshot expires, the sweep marks it expired on the account, stops offering it for restore, and leaves its objects in the bucket.

`rdc backup status` and the backup health digest report the store as clean-up disabled. The bucket keeps growing until delete credentials are added by registering the same id again with keys that may delete.
