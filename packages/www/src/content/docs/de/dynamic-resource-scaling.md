---
title: Dynamische Ressourcenskalierung
description: Erstellen Sie eine Cloud-Architektur mit grenzenloser Flexibilität für KI-Training und dynamische Workloads.
category: Use Cases
order: 1
language: de
---

> **Ist Ihre Cloud-Architektur starr? Bauen Sie mit grenzenloser Flexibilität.**

**Hinweis:** Dies ist ein **Anwendungsbeispiel**, das zeigt, wie Rediacc dieses Problem lösen kann. Als Startup stellen diese Szenarien potenzielle Anwendungen und keine abgeschlossenen Fallstudien dar.

**Krisenszenario:** Die KI-Trainingszeiten wurden **zwei- bis dreimal verlängert**, was zu Projektverzögerungen führte. Während sie auf Ressourcen warteten, erlitten die Ingenieure erhebliche Produktivitätsverluste, was den Wettbewerbsvorteil des Unternehmens gefährdete.

## Das Problem

Die Softwareentwickler des Unternehmens haben Leistungsprobleme mit Servern vor Ort, die für das **Training von KI-Modellen** verwendet werden: 
* Während der **Bürozeiten** (08:00–17:00 Uhr) erreichen Serveranfragen eine Kapazität von 99 % 
* Training, das eine hohe Rechenleistung erfordert, führt dazu, dass die Hardware **nicht ausreicht**

**Nach Lösung suchen:** 
* Die Kosten für ein Server-Upgrade gelten aufgrund der **täglichen Nutzung von 6–7 Stunden** als nicht angemessen. 
* Obwohl eine Cloud-Migration in Betracht gezogen wird, stellen **Datenübertragungskosten** und **Synchronisierungsschwierigkeiten** Hindernisse dar

## Krisenauswirkungen

* KI-Schulungszeiten **verlängern sich um das 2-3-fache**, Projekte verzögern sich 
* Ingenieure erleiden **Produktivitätsverluste**, während sie auf Ressourcen warten 
* Das Unternehmen steht vor dem Risiko, **sukzessive seinen Wettbewerbsvorteil einzubüßen**

## Rediacc-Lösung

Systemingenieur Yüksel entwickelt **ein Hybridmodell** mit Rediacc:

![Hybrid Cloud Scaling](/img/hybrid-cloud-scaling.svg)

### 1. **Sofortige Cloud-Migration** 
* Während der Bürozeiten werden On-Premise-Dienste **mit allen Daten und Konfigurationen** in die Cloud geklont. 
* 100 TB Daten werden in 9 Minuten synchronisiert, indem dank Rediacc **nur die geänderten Teile** übertragen werden

### 2. **Dynamische Skalierung** 
* Server in der Cloud-Umgebung werden **so viel gemietet, wie für das KI-Training benötigt wird** 
* Die Verarbeitungsleistung kann je nach Bedarf **um das Zehnfache erhöht** werden

### 3. **Nachtsynchronisation** 
* Am Ende des Arbeitstages werden **alle Änderungen in der Cloud** **automatisch** in die lokale Umgebung übernommen 
* Nachts arbeitende Ingenieure können ihren Betrieb mit **aktuellen Daten** fortsetzen

## Ergebnis

**Kostenvorteil:** 
* Durch **die stündliche Miete von Cloud-Ressourcen** konnten die monatlichen Kosten um **60 %** gesenkt werden. 
* Die Notwendigkeit, lokale Server zu aktualisieren, wurde **eliminiert**

**Leistungssteigerung:** 
* Die KI-Trainingszeiten wurden von **8 Stunden auf 1,5 Stunden** reduziert. 
* Die Produktivität der Ingenieure stieg um **40 %**

**Flexibles Arbeiten:** 
* **Datenkonsistenz** zwischen Cloud- und On-Premise-Umgebungen wurde nahtlos sichergestellt 
* Teams in der Nachtschicht **hatten sofortigen Zugriff auf aktuelle Daten**