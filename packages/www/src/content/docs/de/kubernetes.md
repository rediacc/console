---
title: "Kubernetes"
description: "Kubernetes mit der Rediacc-Repo-Mentalität betreiben: einen laufenden Cluster forken oder verschieben, einschließlich seiner Daten, auf eine andere Maschine oder ein Rechenzentrum mit kurzem Cutover."
category: "Guides"
tags:
  - containers
  - migration
subcategory: workloads
order: 6
language: de
sourceHash: "22eef465dfd46ccf"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

# Kubernetes

Rediacc bringt Kubernetes ins Produkt, ohne die Repo-Mentalität aufzugeben, auf der der Rest der Plattform aufbaut. Das differenzierende Versprechen ist direkt: Sie können **einen laufenden Cluster forken oder verschieben, einschließlich seiner Daten, auf eine andere Maschine oder ein Rechenzentrum mit kurzem Cutover**. Das ist keine Stop-and-Restore-Migration und keine Zero-Downtime-Magie. Die Workloads starten am Ziel neu, der Cutover wird in Sekunden gemessen, und die Daten reisen mit.

Kubernetes wird von [k3s](https://k3s.io/) angetrieben, einer zertifizierten Kubernetes-Distribution, die in renet eingebettet ist, genau wie die anderen serverseitigen Binaries.

## Das Objektmodell

Rediacc kehrt das übliche Bild "Cluster umhüllt alles" um, damit die Repo-Mentalität weiterhin gilt:

- **Ein Cluster ist der Container.** Eine Maschine hostet Docker-Repos (unverändert) und/oder Cluster. Ein Single-Node-Cluster auf einer Maschine bewahrt die Geschichte "eine Datei bewegt das ganze System" auf Cluster-Ebene. Cluster-Zustand (das k3s-Datenverzeichnis: sein eingebetteter Datastore und containerd) liegt in Datastore-gestützten Copy-on-Write-Image-Dateien, eine pro Knoten, wobei das k3s-`--data-dir` innerhalb des Image-Mounts gebunden ist.
- **Ein Kubernetes-Repo ist ein Namespace.** `rdc repo create <repo> -m <name>` erstellt ein Repo, dessen Laufzeit-Zuhause der Kubernetes-Namespace `<repo>` innerhalb dieses Clusters ist.
- **Persistent Volumes sind separate Copy-on-Write-Einheiten.** PVs sind RBD-Images auf Ceph oder kleine Datastore-Image-Dateien über einen lokalen renet-PV-Provisioner auf dem lokalen Backend. Sie sind niemals Verzeichnisse innerhalb eines opaken Cluster-Images: Das innere Dateisystem hat keine Reflinks, sodass unabhängige Pro-Repo-Forks unabhängige PV-Images erfordern.

Diese Trennung ist es, die beide Versprechen gleichzeitig physisch möglich macht: **immer copy-on-write Namespace-Forks** (die Daten jedes Repos klonen unabhängig) und **Ganze-Cluster-Portabilität** (die Cluster-Images plus jedes PV-Image bewegen sich zusammen).

| Konzept | Docker-Repo | Kubernetes-Repo |
|---|---|---|
| Laufzeit-Zuhause | Isolierter Docker-Daemon | Namespace in einem Cluster |
| Injizierte Env | `DOCKER_HOST` | `KUBECONFIG` |
| Deploy-Wrapper | `renet compose` | `renet kube` |
| Dateneinheit | Ein LUKS-Image | Cluster-Images plus Pro-PV-Images |
| Fork-Einheit | Das Repo-Image | Der Namespace plus seine PV-Clones |
| Ganzer-Ort-Klon | (Repo ist der Ort) | `rdc cluster fork` / `rdc cluster migrate` |

## Einen Cluster deklarieren und erstellen

Ein Cluster ist ein benannter Satz von Node-Pools auf einem privaten Netzwerk. Deklarieren Sie ihn zuerst in der Konfiguration, dann provisionieren Sie ihn.

```bash
# Einen Cluster mit Pools deklarieren (noch nichts wird provisioniert)
rdc cluster create prod --declare-only \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# Die Pool-Mitglieder provisionieren, renet auf jedem bootstrappen, Komponenten installieren (Ceph zuerst)
rdc cluster create prod
```

Pool-Rollen sind `ceph`, `k8s-server`, `k8s-agent` und `hyperconverged` (explizites Opt-in, da Ceph-Speicherziele und Kubelet-Eviction-Schwellwerte um RAM konkurrieren). Jeder Pool trägt die Hardware-Asymmetrie als Pro-Pool-Größen- und Festplattenparameter: festplattenlastige Ceph-Knoten, CPU/RAM-lastige Kubernetes-Knoten.

Pool-Mitglieder materialisieren sich in `resources.machines` als `<cluster>-<pool>-<n>` mit einer Rückreferenz, sodass **jeder bestehende `-m`-Befehl auf ihnen funktioniert**: `rdc machine status`, `rdc term connect`, Repo-Befehle und Backup-Strategien sehen Cluster-Knoten alle als gewöhnliche Maschinen.

Cloud-Provider provisionieren über [OpenTofu](https://opentofu.org/), dabei folgen sie derselben `ProviderMapping`-Registry, die `rdc machine provision` verwendet, erweitert um einen Private-Network-Block (VLAN oder VPC, die zu setzende MTU, die private NIC-Benennung). Lokales KVM ist der immer verfügbare Testpfad über `rdc ops`.

```bash
# Cluster inspizieren
rdc cluster status                 # alle Cluster auflisten
rdc cluster status prod     # vollständige Konfiguration für einen Cluster

# Einen Pool vergrößern oder verkleinern (fügt Maschinen hinzu/entfernt sie, joint/drained Knoten)
rdc cluster scale prod --pool k8s --count 5


# Provisionierte Mitglieder abbauen und den Cluster aus der Konfiguration entfernen
rdc cluster destroy prod
```

### Eine Kubeconfig erhalten

Die Kubeconfig wird niemals in Ihrer Konfigurationsdatei gespeichert (sie ist groß und rotiert). Sie wird bei Bedarf über SSH abgerufen und lokal mit `0600`-Berechtigungen gecacht, nach demselben Seiten-Zustand-Muster wie OpenTofu-Arbeitsverzeichnisse und der Zertifikats-Cache.

```bash
rdc cluster kubeconfig prod
# Gibt aus: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Kubernetes-Repositories

Das Ziel-Flag entscheidet über die Laufzeit. Es gibt kein Typ-Flag.

```bash
# Docker-Repo (unverändert): ein isolierter Docker-Daemon auf einer Maschine
rdc repo create shop -m server-1 --size 10G

# Kubernetes-Repo: Namespace "shop" plus sein Storage, innerhalb eines Clusters
rdc repo create shop --datastore prod --size 10G
```

Repo-Verben sind die einzige Oberfläche für Repo-gebundene Arbeit. Durch den Ziel-Auflösungs-Trichter wird annähernd der gesamte Repo-Befehlssatz Cluster-fähig: `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status` und `log` akzeptieren alle `--cluster`. Ein Cluster-Ziel löst sich auf zu seinem Control-Knoten plus dem auf den Namespace des Repos gepinnten KUBECONFIG-Kontext, das Analogon zur Auflösung einer Maschine zu `DOCKER_HOST` plus einem Arbeitsverzeichnis.

```bash
rdc repo sync upload shop --local ./config
rdc cluster kubeconfig prod           # KUBECONFIG exportieren, dann kubectl direkt verwenden
```

Cluster-Knoten materialisieren sich auch in `resources.machines`, sodass Sie sich mit dem gewöhnlichen `rdc term connect <cluster>-<pool>-<n>` per SSH mit einem bestimmten Knoten verbinden können.

### Dual-Runtime-Rediaccfile

Portabilität zwischen Docker und Kubernetes beruht auf einer Konvention, nicht auf automatischer Manifest-Konvertierung. Ein Repo, das sowohl einen `renet compose`-Pfad als auch einen `renet kube`-Pfad unter denselben `up()`- und `down()`-Funktionen bereitstellt, migriert frei in beide Richtungen, weil die Datenverzeichnis-Konventionen identisch sind. renet injiziert `DOCKER_HOST` bei einem Maschinen-Ziel und `KUBECONFIG` bei einem Cluster-Ziel; `up()` liest, welches gesetzt ist, und leitet entsprechend weiter.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Kubernetes-Laufzeit
  else
    renet compose -- up -d             # Docker-Laufzeit
  fi
}
```

Ein Repo, dem die Ziel-Laufzeit fehlt, erhält eine klare Ablehnung **nach** der Datenübertragungsphase: Die Images bewegen sich, und der Deploy-Schritt teilt Ihnen mit, dass das Repo keinen Kubernetes- (oder Docker-)Pfad deklariert, statt den Zustand zu beschädigen.

## Ein Repository forken

`rdc repo fork` auf einem Kubernetes-Repo kopiert immer Daten, immer sofort. Es gibt kein `--full`-Flag und keine Varianten.

```bash
rdc repo fork shop --tag joseph
```

Das erstellt den Namespace `shop-joseph` im selben Cluster, klont jedes Volume copy-on-write (ein RBD-Clone auf Ceph, ein Reflink der PV-Image-Dateien auf dem lokalen Backend) und deployt die Workloads dort. Die Fork-URL ist sofort live unter dem Wildcard-Zertifikat des Elternteils, sodass kein neues Zertifikat oder DNS-Eintrag ausgestellt wird.

Ziel-Eskalation:

- `--to-cluster <name>` forkt in einen anderen bestehenden Cluster. Gleiches Ceph-Backend: der RBD-Clone bleibt copy-on-write. Unterschiedliches Backend: die Push-Mechanik bewegt die Images.
- `--provider <p>` provisioniert zuerst einen neuen Cluster, mit Pool-Spezifikationen, die standardmäßig die Form des Quell-Clusters spiegeln (Flags überschreiben das).

Im KVM-Testlabor gemessen, schließt ein Namespace-Fork in etwa ein bis fünf Sekunden ab, wobei der Eltern-Workload unberührt bleibt und die beiden Namespaces unabhängig auseinanderlaufen.

## Einen ganzen Cluster forken oder verschieben

Ganze-Cluster-Operationen liegen in der `rdc cluster`-Gruppe, weil sie auf einem anderen Objekt agieren (dem ganzen Ort mit all seinen Repos) und nicht durch einen Befehl ausgedrückt werden können, der einen einzelnen Repo-Namen entgegennimmt. Das ist die Flaggschiff-Geschichte.

```bash
# Einen ganzen Cluster klonen, einschließlich der Daten seiner Repos, in einen neuen Cluster
rdc cluster fork prod --to spare --tag staging

# Einen ganzen Cluster verschieben, einschließlich der Daten seiner Repos, auf eine andere Maschine oder ein Rechenzentrum
rdc cluster migrate prod --to spare
```

Beide koordinieren ein Copy-on-Write der Cluster-Images plus jedes Repo-PV-Images, dann schreiben sie die Knoten-Identität neu, sodass der Klon oder der verschobene Cluster gesund auf seinen neuen Adressen hochkommt. Da k3s den Control-Plane-Zustand in seinem eingebetteten Datastore speichert, ist das Cluster-Image selbst der Snapshot: die Konsistenzreihenfolge ist zuerst Control Plane, dann PVs, dann Agents.

Die ehrlichen Zahlen, Ende-zu-Ende im KVM-Testlabor gemessen:

| Operation | Was sie tut | Gemessen |
|---|---|---|
| Namespace-Fork | Den Namespace eines Repos plus PVs an Ort und Stelle klonen | ~1 bis 5 s |
| Single-Image-RBD-Fork | Einen Ceph-gestützten PV-Clone copy-on-write kopieren | ~5 s |
| Ganzer 2-Knoten-Cluster-Fork | Drainen, Control Plane und Agent reflinken, Identität auf neue IPs neu schreiben, Elternteil unberührt | ~46 s |
| Maschinenübergreifende Cluster-Migration | Heißes Pre-Copy plus der Stop-and-Restart-Cutover | ~16 s Cutover |

Der Standard ist **crash-konsistent und referenziell intakt**: dieselbe Semantik wie ein Stromausfall-Zyklus, was die Workloads auch sehen. Anwendungskonsistente Snapshots sind verfügbar, wenn die Dateisysteme des Workloads während der Kopie eingefroren werden. Dies wird bewusst **nicht** als Zero-Downtime dargestellt. Niemand sonst bietet überhaupt "einen laufenden Cluster forken, einschließlich seiner Daten" an; die ehrliche Darstellung ist ein kurzer, gemessener Cutover statt eines Marketing-Absoluten.

## Storage: ceph-csi und Persistent Volumes

Ceph wird vom cephadm-Flow von renet auf dem `ceph`-Pool provisioniert, **außerhalb** jedes Kubernetes-Clusters, und Cluster nutzen es über renet-templatete ceph-csi-Manifeste. Jede Cluster-Instanz (und jeder Fork) erhält seinen eigenen RBD/RADOS-Namespace, was die Pro-Mandanten-Isolierungsprimitive ist. Storage liegt unter allen Clustern, sodass es auch einfache Docker-Repos und das Datastore-Backend unterstützt, und ein Cluster-Fork klont RBD-Images unterhalb von Kubernetes, statt sein eigenes Storage-Backend zu forken.

Auf dem lokalen Backend (ohne Ceph) unterstützt ein lokaler renet-PV-Provisioner jedes PV mit einer kleinen Copy-on-Write-Image-Datei im Datastore, reflink-geklont bei Fork. Siehe [Server-Referenz](/de/docs/server-reference) für das On-Disk-Layout und die renet-Befehle.

## Eine Distribution wählen

Die Distro ist eine Abstraktion mit einer kleinen, echten Schnittstelle (install, join, kubeconfig, healthcheck, upgrade und so weiter):

- **k3s** ist der Standard und die einzige eingebettete Distribution. Sie ist Apache-2.0, CNCF-zertifiziert, ein einziges verlagerbares Binary, und sowohl ihr gebündeltes Traefik als auch ServiceLB sind zugunsten des Rediacc-Proxys deaktiviert. Ihr `--data-dir` bindet beim Start, was genau das ist, was Cluster-Fork und -Migrate benötigen, wenn sich der Image-Mount-Pfad ändert. k3s ist als `repoEmbeddable` markiert.
- **external** ist Bring-your-own-Kubeconfig. Nur `getKubeconfig` und `healthcheck` leisten echte Arbeit; die Lebenszyklus-Verben liefern erstklassige "nicht zutreffend"-Ergebnisse statt Fehler.
- **RKE2** ist das geplante dritte Backend für FIPS/CIS-Kunden, nicht Teil dieses Releases.

Cluster-Fork und -Migrate verweigern die Ausführung auf einer nicht-`repoEmbeddable`-Distribution mit einem klaren Fehler statt einer Zustandsbeschädigung, weil das Einbetten von Cluster-Zustand in Datastore-Images ein Datenverzeichnis erfordert, das beim Start bindet.

## Registry

Zwei unterschiedliche Image-Probleme, zwei Werkzeuge:

- **Upstream-Schmerz** (Docker-Hub-Rate-Limits, abgelehnte Pulls, offline): ein eingebetteter [zot](https://zotregistry.dev/)-Pull-Through-Cache läuft auf dem Control-Pool mit `sync.onDemand` gegen mehrere Upstreams (docker.io, ghcr.io, quay.io). Er ist in renet eingebettet, genau wie die anderen Binaries, und er ersetzt die Ops-Test-Registry, sodass jeder Lauf ihn ausübt.
- **Intra-Cluster-Verteilung**: Die eingebettete Registry-Mirror von k3s lässt Knoten bereits gepullte Images Peer-to-Peer teilen.

Die Verdrahtung ist transparent und ohne Neustart über die `certs.d/hosts.toml` von containerd und die `registries.yaml` von k3s. Der Pro-Repo-containerd-Store innerhalb des Cluster-Images bleibt die Wahrheitsquelle, die Forks und Migrationen bewegen; die Registry ist ein Cache vor dem Internet, niemals Zustand.

## Netzwerk und URLs

Kubernetes-Repo-URLs folgen dem flachen Schema, wobei die Namespace-Identität in das am weitesten links stehende Label gefaltet wird und der Cluster das stabile zweite Label ist:

```
{service}--{repo}.{cluster}.{machine}.{base}          Kubernetes-Repo (Namespace = Repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    Fork (Namespace = repo-tag)
```

Jeder Namespace und jeder Fork erbt das Wildcard-Zertifikat und den DNS-Eintrag des Elternteils, sodass Fork-URLs sofort live sind und neue Zertifikate nur ausgestellt werden, wenn ein neuer Cluster oder ein neues Repo erstellt wird. Der Router entdeckt Kubernetes-Services, indem er den Cluster nach `rediacc.*`-annotierten Services abfragt, das Kubernetes-Analogon zum Lesen von Docker-Labels. Siehe [Netzwerk](/de/docs/networking) für das Routing-Modell und [Architektur](/de/docs/architecture) für die Storage-Backends.

## Attribution

Rediacc überträgt mehrere Drittanbieter-Binaries (k3s, zot und die anderen, die renet einbettet). Drucken Sie deren Versionen, SPDX-Lizenzkennungen und Quellarchiv-URLs jederzeit:

```bash
rdc credits
rdc credits --licenses    # vollständiger THIRD_PARTY_LICENSES-Text, der mit Releases gebündelt wird
```
