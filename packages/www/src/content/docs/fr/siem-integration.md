---
title: "Intégration SIEM"
description: "Acheminer les événements d'audit de Rediacc vers Splunk, OpenSearch, Sentinel ou tout SIEM compatible OpenTelemetry"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: fr
sourceHash: "69ec0d3d122d13df"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Intégration SIEM

Chaque opération au niveau machine émise par la CLI Rediacc est consignée dans la table `event_log` du serveur de compte et émise simultanément sous forme d'enregistrement de journal OpenTelemetry. Les opérateurs acheminent ces enregistrements vers un SIEM (Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch, etc.) en pointant le serveur de compte vers un OpenTelemetry Collector qui exporte vers le SIEM de leur choix.

Cette page explique comment le mettre en place. Le schéma des événements d'audit et le déploiement de référence du collector se trouvent dans le monorepo public, sous [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## Ce qui est journalisé

Chaque entrée écrite dans la table `event_log` du serveur de compte, qu'il s'agisse d'événements au niveau du compte (authentification, stockage de configuration, licence) ou d'événements CLI au niveau machine (`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …), est répliquée vers le pipeline de journaux OTLP.

Le vocabulaire des types d'événements est une union discriminée fermée, définie dans [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts). L'ajout d'un nouveau type d'événement exige une modification du code et est contrôlé par la CI ; les auteurs de règles SIEM peuvent donc compter sur la stabilité du vocabulaire.

Chaque enregistrement de journal porte des attributs sémantiques OpenTelemetry :

| Attribut | Signification |
|---|---|
| `event.domain` | Valeur fixe `rediacc.audit` : filtrer dessus pour ignorer les journaux sans rapport |
| `event.name` | Le type d'événement canonique (par ex. `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | Utilisateur à l'origine de l'opération |
| `organization.id`, `team.id` | Périmètre organisation/équipe |
| `cloud.account.id` | ID client Stripe |
| `subscription.id` | Abonnement de licence |
| `audit.data.*` | Charge utile de l'opération, aplatie |

## Mise en place

### 1. Déployer le collector

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

Par défaut, le collector écoute sur `:4318` (OTLP/HTTP) et écrit sur sa propre sortie standard via l'exporter `debug`, ce qui permet de vérifier le pipeline avant de l'acheminer vers une destination coûteuse.

### 2. Pointer le serveur de compte vers le collector

Dans l'environnement du serveur de comptes (les secrets du Worker, ou l'environnement du processus d'un serveur sur site) :

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Redémarrer le serveur de compte. Les événements d'audit commencent à affluer vers le collector immédiatement.

### 3. Configurer l'exporter SIEM

Modifier `compose/otel-collector/config.yaml`. Le fichier est livré avec quatre exemples d'exporters commentés :

- **OpenSearch / Elasticsearch** : exporter `opensearch`, nécessite l'extension `basicauth/opensearch`.
- **Splunk HEC** : exporter `splunk_hec`, nécessite un jeton HEC et un index.
- **AWS CloudWatch Logs** : exporter `awscloudwatchlogs`, nécessite des identifiants IAM dans l'environnement du collector.
- **Microsoft Sentinel** : via l'exporter `azuremonitor` avec une chaîne de connexion App Insights.

Décommenter un seul exemple, le substituer à `debug` dans la liste `exporters:` du pipeline `logs:`, puis redémarrer le collector.

Tout [exporter contrib de l'OTel Collector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter) qui accepte des journaux fonctionne : le pipeline d'audit produit des enregistrements de journal OTLP standard.

## Contenu de détection

Les événements d'audit sont conçus pour la rédaction de règles [Sigma](https://sigmahq.io). Les règles Sigma sont indépendantes des éditeurs et se convertissent via `sigma-cli` en requêtes natives pour OpenSearch, Splunk, Sentinel et d'autres.

Exemple de règle (échec de `repo.fork` par un utilisateur inattendu) :

```yaml
title: Unexpected Rediacc repo fork
detection:
  selection:
    event.domain: rediacc.audit
    event.name: cli.repo.fork
    audit.data.success: false
  condition: selection
level: medium
```

## Posture de conformité

Le pipeline d'audit est le socle des exigences de journalisation d'audit mentionnées dans la documentation de conformité de Rediacc :

- **RGPD Art. 30** : registre des activités de traitement
- **SOC 2 CC6.1 / CC7.2** : journalisation des accès et surveillance
- **HIPAA 45 CFR 164.312(b)** : contrôles d'audit
- **PCI DSS Req 10** : suivre et surveiller tous les accès
- **NIS2 Art. 21** : les événements d'audit alimentent la gestion des incidents ; la chronologie d'incident, les horloges et les rapports par étapes sont des fonctionnalités distinctes
- **DORA Art. 10** : les événements d'audit alimentent la détection ; les détecteurs d'anomalies s'exécutent sur la machine et sur le serveur à partir des enregistrements de flux forensics, pas sur ce pipeline

## Fiabilité

L'émission OTLP est de type « fire-and-forget » : une panne du collector ne bloquera ni ne fera jamais échouer une requête API Rediacc, et chaque événement reste persisté dans la table `event_log` du serveur de compte quoi qu'il arrive. Combiné au traitement par lots et aux nouvelles tentatives du collector, cela permet de déployer le pipeline en amont de n'importe quel SIEM en toute sécurité.
