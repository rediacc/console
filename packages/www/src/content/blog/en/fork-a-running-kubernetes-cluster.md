---
title: "Fork a Running Kubernetes Cluster in 46 Seconds"
description: "Rediacc now forks or moves a whole running Kubernetes cluster, data included, to another machine or datacenter with a short cutover. The measured numbers are inside."
author: Rediacc
publishedDate: 2026-07-07
category: announcement
tags:
  - announcement
  - kubernetes
  - ceph
  - k3s
featured: true
language: en
---

> **TL;DR.** Rediacc can now fork or move a whole running Kubernetes cluster, data included, to another machine or datacenter. In our KVM test lab, a 2-node cluster fork took about 46 seconds. A cross-machine migrate had a cutover of about 16 seconds. This is not zero downtime, and we will not call it that. It is a short, measured cutover. Nobody else ships this at all.

## The one-file story, so far

Rediacc has always had one core trick. Your whole system lives in one file: apps, databases, and settings together. Copy the file and you have a second system. Move the file and the system moves with it.

Until now, that story ended at one machine. A repository was a Docker deployment on a single host. Vertical portability, if you like.

## What shipped

Today the same story works one level up. A cluster is now a thing Rediacc can hold as a set of files: the node images plus every persistent volume. That means the whole running cluster can be forked or moved, the same way a single repository always could.

The mental model does not change. A Kubernetes app is just a namespace inside the cluster. You fork it like any repo. The cluster is the container; the namespace is the repo.

## The flagship: fork or move the whole cluster

```bash
# Clone an entire cluster, including its repos' data, into a new cluster
rdc cluster fork prod --to spare --tag staging

# Move an entire cluster, including its repos' data, to another machine or datacenter
rdc cluster migrate prod --to spare
```

The honest numbers, measured end to end in the KVM test lab:

| Operation | What it does | Measured |
|---|---|---|
| Namespace fork | Clone one repo's namespace plus PVs in place | ~1 to 5 s |
| Single-image RBD fork | Copy-on-write one Ceph-backed PV clone | ~5 s |
| Whole 2-node cluster fork | Drain, reflink control plane and agent, rewrite identity to new IPs, parent untouched | ~46 s |
| Cross-machine cluster migrate | Hot pre-copy plus the stop-and-restart cutover | ~16 s cutover |

Fork leaves the parent running and untouched. Migrate pre-copies while the cluster keeps serving, then stops, sends the final delta, and restarts on the destination. The cutover is those 16 seconds.

## Why nobody else ships this

We checked before making the claim.

- Velero and Kasten K10 back up a cluster and restore it somewhere else. That is stop and restore. Good tools, different job.
- Cluster API's `clusterctl move` relocates the cluster's definition. The shape moves. The data does not.
- Ceph RBD mirroring replicates volumes to a second cluster, asynchronously. It is disaster recovery for the data, not a move of the cluster.

None of them fork a running cluster with its data. That is the gap this release fills.

## Keep your Kubernetes

This is not a new Kubernetes. Rediacc runs k3s for you, or connects to a cluster you already have with your own kubeconfig. Volumes ride on ceph-csi RBD. Your manifests stay yours.

Provisioning is provider-agnostic. Run it on your own KVM hosts, or on clouds like Linode with private VLANs. Node pools separate the disk-heavy Ceph nodes from the cpu-heavy Kubernetes nodes, so each side scales on its own terms.

## The constraints, stated plainly

Three things we want on the record.

Workloads restart on the destination during a migrate cutover. This is not live migration and we do not sell it as one.

The default consistency is crash-consistent: the same semantics as a power cycle. Application-consistent copies are available when the workload's filesystems are frozen during the copy.

The numbers above come from our KVM test lab on a 2-node cluster. Your hardware and cluster size will change them. The shape of the story holds because the copies are copy-on-write, but measure on your own gear before you promise anything to your own team.

## Try it

The full walkthrough, including the object model and the storage layout, lives in the [Kubernetes docs](/en/docs/kubernetes). If you already run Rediacc, update the CLI and start with a namespace fork. It takes a few seconds, and it is the same mentality all the way up.
