---
title: "Java4Shell: Our CPU Qualified, Our Server Had No Java, and Our Templates Taught Us About Pinning"
description: "CVE-2026-114938 needs an AVX-512 VBMI CPU and an affected JDK. Our server had the CPU but zero JVMs. The real work was in the app templates we ship, where one pinned tag had frozen a 2023 JDK."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - java
  - docker
  - case-study
featured: true
language: en
---

> **TL;DR.** Java4Shell (CVE-2026-114938) is a heap out-of-bounds write in the JIT-compiled Base64 decoder of OpenJDK. It only fires on x86-64 CPUs with AVX-512 VBMI.
>
> - Our production server's CPU **has all four required flags**. On a CPU check alone, it looked exposed.
> - A probe of **43 containers**, the host and the stopped repositories found **zero Java runtimes**. A control run of the same probe, looking for `python3`, found it everywhere it should. Nothing to patch on the server.
> - The app templates we ship were a different story. **Four** of them start a JVM. **Three** use floating tags and were already rebuilt upstream with patched JDKs on 20 November.
> - **One**, Elasticsearch, was pinned to `8.11.0`: an image from November 2023 with bundled JDK `21.0.1`. Elastic has no fixed release yet, so the template now starts Elasticsearch with Elastic's own mitigation flag, verified on a running node.

## What was disclosed

On 17 November, researchers at Calif published **Java4Shell**, and Oracle and OpenJDK shipped fixes the same day. The bug sits in the hardware-accelerated Base64 decoder of HotSpot: the AVX-512 VBMI path mishandles the last few characters and can write past the end of a heap buffer. A remote attacker with no account can turn that into memory corruption and, in the right application, into code execution. The write-up shows pre-auth chains for several well-known Java server products.

The details that matter for triage:

- **Affected:** OpenJDK 17.0.6 and later, 21, 25 and 27, before the fix builds. Standard Java 8 and Java 11 are not affected.
- **Fixed:** 17.0.21.1, 21.0.13.1, 25.0.5.1 and 27.0.1.1 (Temurin builds carry `+2`, or `+4` for 27). A runtime that reports `17.0.21` without the `.1` is still vulnerable.
- **Preconditions:** an x86-64 CPU with AVX-512 VBMI, a JIT that has already compiled the decoder, and an app path that decodes Base64 from untrusted input. ARM is not affected.
- **Score:** 9.2 under CVSS 4.0, 8.1 under CVSS 3.1. A standalone proof of concept is public. No exploitation in the wild had been reported at the time of writing.
- **Mitigation:** start the JVM with `-XX:-UseBASE64Intrinsics`. The other published option, `-XX:UseAVX=2`, also works on x86-64 but makes an ARM JVM refuse to start.

Our [previous patch run](/en/blog/patching-nginx2root-and-php-fork-first) ended with a fork-first rollout of four apps. This one ended much earlier, and the interesting part is why.

## Step 1: does the CPU qualify?

Most CVEs have a software precondition. This one has a hardware precondition too, and it is cheap to check:

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

All four. The machine runs an AMD EPYC 9354P, a recent server CPU with full AVX-512 support. If the triage had stopped here, the answer would have been "exposed, patch everything Java tonight".

![The three preconditions: the CPU qualifies, the JDK check fails, so the input path is never reached](/img/blog-java4shell-preconditions.svg)

## Step 2: is there any Java to patch?

The CPU is only one link in the chain. The second link is an affected JDK, so the next question was simple: which containers run Java at all?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

We ran this through `rdc term connect <repo>@hostinger` for every repository on the machine. The `find` for `libjvm.so` catches JVMs that are bundled inside an app folder and not on the `PATH`, which is how Elasticsearch, for example, ships its JDK.

The result was empty. No `java`, no `libjvm.so`, in any of the 43 running containers.

An empty result from a probe proves nothing until the probe has shown it can find something. So the same loop ran again, this time looking for `python3`, which we know lives in the ERPNext containers. It found Python 3.14 in every one of them. The probe works; the server simply has no Java.

Two more places got checked before closing the question. The host itself had no Java and no `/usr/lib/jvm`. The repositories with nothing running had no Java images on their Docker daemons. One of them held a checkout of our own monorepo, and its compose files mentioned `cassandra:5.0` and `elasticsearch:8.11.0`. That pointed at the next step.

## Step 3: the templates we ship

Rediacc ships ready-made app templates: a `docker-compose.yaml` plus a Rediaccfile per app. A server we do not run can deploy them. So a Java image in a template is exposure for every customer with the right CPU, even when our own server is clean.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

Four templates start a JVM. For two of them the image config in the registry already names the JDK. For the other two it does not, so we ran each image once and asked:

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| Template | Tag in the template | JDK inside today | Status |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | fixed upstream, rebuilt 20 Nov |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | fixed upstream, rebuilt 20 Nov |
| Solr | `solr:9-slim` | 17.0.21.1+2 | fixed upstream, rebuilt 20 Nov |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (bundled) | **vulnerable**, no fixed Elastic release yet |

![Pinned versus floating: the pinned Elasticsearch image kept a 2023 JDK, the floating tags were rebuilt with the fix](/img/blog-java4shell-pinned-vs-floating.svg)

## The pinning lesson, revised

The previous post ended with "pin exact tags". This run adds a footnote to that rule.

Pinning is right for apps we run and upgrade on purpose. The pin makes the running version visible, and a floating tag can point at a fix while the server keeps running an old image, because `docker compose up -d` does not pull an image it already has.

For templates that people deploy fresh, the picture flips. The three floating major tags (`5.0`, `5-community`, `9-slim`) picked up the patched JDK three days after the fix, with no change on our side. The one exact pin, `8.11.0`, froze Elasticsearch on an image built in November 2023, with a JDK that no rebuild of that tag is going to fix.

So the rule we keep has two halves. Production apps get exact tags and a deliberate upgrade. Templates get pins too, because Elasticsearch and Kibana must run the same version, but every template pin is now listed in our pin registry, where the freshness gates flag a pin that falls behind instead of letting it sit for three years.

## Step 4: the mitigation, proven on a real node

Elastic has announced that the fix ships as a bundled JDK update in the upcoming 8.19.26, 9.4.10, 9.5.7 and 9.6.0 releases. Until one of those exists, the official guidance is the JVM flag. In the template, that is one more word in `ES_JAVA_OPTS`:

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![What the flag changes: the JIT keeps the plain Java decoder instead of the AVX-512 intrinsic](/img/blog-java4shell-intrinsic-flag.svg)

A flag in a compose file is only a claim until the JVM confirms it. We checked twice. First, the bundled JDK itself, with and without the flag:

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

Then a real single-node cluster started with the template's options. It came up green, and its own API listed the flag among the JVM arguments:

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## What went wrong

**The CPU check almost decided the answer.** It is the most visible precondition, it takes one command, and it said "exposed". Only the second check, for an actual JVM, turned a midnight emergency into a template change.

**A test suite ran where it should not.** To check the template edit, we ran the template package's lifecycle suite on a workstation. That suite is meant for a licensed Rediacc repository, not a bare Docker host, and it spent over ten minutes starting other templates. It also showed that one unrelated template wrote its generated secret into its own source folder, a file nobody would want in a commit. That template now writes the secret outside the source tree, and the suite refuses to start without the repository it needs.

**There was nothing to fork.** Our usual safety step, a fork of the production repository before any change, had no target this time. The change lived in a template file in git, so the safety net was a reviewable commit and a live boot test, not a snapshot.

## The choices, and why

| Option we had | What we chose | Why |
|---|---|---|
| Treat the CPU check as the answer | Probe for an actual JVM | The CPU said exposed; no JVM meant nothing to exploit. |
| Trust an empty probe | Run a control that must find something | An empty result from a broken probe looks the same as a clean server. |
| Read the JDK version from the registry | Run each image once | Two of the four images do not record the JDK version in their config. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | Narrower: it turns off one routine, not every AVX-512 speedup, and an ARM JVM still starts. |
| Bump Elasticsearch to the newest 8.19 now | Keep 8.11.0, add the flag, bump when the fixed release ships | The newest releases out today still bundle an affected JDK, and Kibana has to move in the same step. |
| Exact pins everywhere | Exact pins plus a freshness gate on every template pin | A pin with no alarm froze a 2023 JDK; the gate keeps the pin and adds the alarm. |

## The checklist we keep

1. Check every precondition, not only the first one that matches.
2. Look for the runtime itself (`java`, `libjvm.so`), not only for a product name.
3. Prove every empty probe with a control.
4. Sweep what we ship, not only what we run.
5. Read the version inside the image; run the image when the config is silent.
6. Prefer the narrowest mitigation, and confirm it in the running process.
7. Track the vendor's fixed release and remove the mitigation once it lands.

As in the previous run, an AI agent (Claude Code) did the work through `rdc`, with production access granted by the operator before the session started. This time production never changed at all: every step on the server was a read, and the one fix went into a template, through git, with a live test behind it.
