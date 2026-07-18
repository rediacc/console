---
title: "Kubernetes"
description: "Käita Kubernetest Rediacci repo mentaliteediga: forkida või liigutada töötav klaster, sealhulgas selle andmed, teise masinasse või andmekeskusesse lühikese ülemineku ajaga."
category: "Guides"
order: 6
language: et
sourceHash: "d36c468ae2350e25"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

# Kubernetes

Rediacc toob Kubernetese tootesse, loobumata repo mentaliteedist, millele ülejäänud platvorm on üles ehitatud. Eristav väide on otsene: sa saad **forkida või liigutada töötava klastri, sealhulgas selle andmed, teise masinasse või andmekeskusesse lühikese ülemineku ajaga**. See ei ole peata-ja-taasta ränne ega null-seisaku maagia. Töökoormused taaskäivituvad sihtkohas, üleminek mõõdetakse sekundites ja andmed liiguvad kaasa.

Kubernetest käitab [k3s](https://k3s.io/), sertifitseeritud Kubernetese distributsioon, mis on renetisse põimitud samamoodi nagu teised serveripoolsed binaarid.

## Objektimudel

Rediacc pöörab ümber tavapärase pildi "klaster ümbritseb kõike", nii et repo mentaliteet jääb kehtima:

- **Klaster on konteiner.** Masin majutab Docker-reposid (muutumatult) ja/või klastreid. Ühesõlmeline klaster ühel masinal säilitab loo "üks fail liigutab kogu süsteemi" klastri tasandil. Klastri olek (k3s-i andmekataloog: selle põimitud andmesalv ja containerd) elab andmesalve-toetatud copy-on-write pildifailides, üks sõlme kohta, kusjuures k3s-i `--data-dir` on seotud pildi ühenduspunkti sees.
- **Kubernetese repo on nimeruum.** `rdc repo create <repo> -m <name>` loob repo, mille käitusaegne kodu on Kubernetese nimeruum `<repo>` selle klastri sees.
- **Püsivad köited on eraldi copy-on-write üksused.** PV-d on RBD-pildid Cephis või väikesed andmesalve pildifailid renet-i kohaliku PV-provisioneerija kaudu kohalikul taustasüsteemil. Need pole kunagi kataloogid ühe läbipaistmatu klastripildi sees: sisemisel failisüsteemil pole reflinke, nii et sõltumatud repo-põhised fork'id vajavad sõltumatuid PV-pilte.

See eraldus on see, mis teeb mõlemad lubadused korraga füüsiliselt võimalikuks: **alati copy-on-write nimeruumi fork'id** (iga repo andmed kloonitakse sõltumatult) ja **terve klastri porditavus** (klastripildid pluss iga PV-pilt liiguvad koos).

| Kontseptsioon | Docker-repo | Kubernetese repo |
|---|---|---|
| Käitusaegne kodu | Isoleeritud Dockeri deemon | Nimeruum klastris |
| Süstitud env | `DOCKER_HOST` | `KUBECONFIG` |
| Juurutuse ümbris | `renet compose` | `renet kube` |
| Andmeühik | Üks LUKS-pilt | Klastripildid pluss PV-pildid |
| Fork-ühik | Repo pilt | Nimeruum pluss selle PV-kloonid |
| Terve koha kloon | (repo ongi koht) | `rdc cluster fork` / `rdc cluster migrate` |

## Klastri deklareerimine ja loomine

Klaster on nimega sõlmepesade kogum privaatvõrgus. Deklareeri see esmalt konfiguratsioonis, seejärel valmista ette.

```bash
# Deklareeri klaster pesadega (midagi pole veel ette valmistatud)
rdc config cluster add --name prod \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# Valmista ette pesa liikmed, käivita renet igaühel, paigalda komponendid (Ceph esimesena)
rdc cluster create --name prod
```

Pesa rollid on `ceph`, `k8s-server`, `k8s-agent` ja `hyperconverged` (selgesõnaline sisselülitamine, kuna Ceph mälueesmärgid ja kubeleti väljatõstmise lävendid konkureerivad mälu pärast). Iga pesa kannab riistvara asümmeetriat pesapõhiste suurus- ja kettaparameetritena: kettamahukad Ceph-sõlmed, protsessori/mälumahukad Kubernetese sõlmed.

Pesa liikmed materialiseeruvad `resources.machines`-i kujul `<cluster>-<pool>-<n>` koos tagasiviitega, nii et **iga olemasolev `-m`-käsk töötab nendega**: `rdc machine query`, `rdc term connect`, repo-käsud ja varundusstrateegiad näevad kõik klastri sõlmi tavaliste masinatena.

Pilvepakkujad valmistavad ette [OpenTofu](https://opentofu.org/) kaudu, järgides sama `ProviderMapping` registrit, mida kasutab `rdc machine provision`, laiendatuna privaatvõrgu plokiga (VLAN või VPC, määratav MTU, privaatse NIC-i nimetamine). Kohalik KVM on alati saadaolev testitee `rdc ops` kaudu.

```bash
# Klastrite kontrollimine
rdc cluster status                 # loetle kõik klastrid
rdc cluster status --name prod     # ühe klastri täielik konfiguratsioon

# Pesa kasvatamine või kahandamine (lisab/eemaldab masinaid, ühendab/tühjendab sõlmi)
rdc cluster scale --name prod --pool k8s --count 5

# Komponentide paigaldamine juba ette valmistatud liikmetele
rdc cluster install --name prod

# Ette valmistatud liikmete lammutamine ja klastri eemaldamine konfiguratsioonist
rdc cluster destroy --name prod
```

### Kubeconfig hankimine

Kubeconfig'i ei salvestata kunagi sinu konfiguratsioonifailis (see on suur ja roteerub). See tuuakse nõudmisel SSH kaudu ja puhverdatakse kohalikult õigustega `0600`, järgides sama külgoleku mustrit nagu OpenTofu tööalad ja sertifikaadipuhver.

```bash
rdc cluster kubeconfig --name prod
# Väljastab: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Kubernetese repositooriumid

Sihtlipp otsustab käitusaja. Tüübi lippu pole.

```bash
# Docker-repo (muutumatult): isoleeritud Dockeri deemon masinal
rdc repo create --name shop -m server-1 --size 10G

# Kubernetese repo: nimeruum "shop" pluss selle salvestus, klastri sees
rdc repo create --name shop --cluster prod --size 10G
```

Repo-verbid on ainus pind repo-põhise töö jaoks. Sihtkoha lahendamise lehtri kaudu muutub peaaegu kogu repo-käskude komplekt klastriteadlikuks: `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status` ja `log` võtavad kõik vastu `--cluster`. Klastri sihtkoht lahendub selle juhtsõlmeks pluss repo nimeruumile kinnitatud KUBECONFIG-kontekstiks, analoogselt masina lahendamisega `DOCKER_HOST`-iks pluss töökataloogiks.

```bash
rdc repo sync upload --cluster prod -r shop --local ./config
rdc cluster kubeconfig --name prod           # ekspordi KUBECONFIG, seejärel kasuta otse kubectl-i
```

Klastri sõlmed materialiseeruvad samuti `resources.machines`-is, nii et saad SSH-ga ühenduda konkreetse sõlmega tavalise `rdc term connect <cluster>-<pool>-<n>` abil.

### Kahe käitusajaga Rediaccfile

Porditavus Dockeri ja Kubernetese vahel toetub kokkuleppele, mitte automaatsele manifesti teisendamisele. Repo, mis pakub nii `renet compose` teed kui ka `renet kube` teed samade `up()`- ja `down()`-funktsioonide all, migreerub vabalt mõlemas suunas, kuna andmekataloogi kokkulepped on identsed. renet süstib `DOCKER_HOST`-i masina sihtkoha korral ja `KUBECONFIG`-i klastri sihtkoha korral; `up()` loeb, kumb on seatud, ja suunab vastavalt.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Kubernetese käitusaeg
  else
    renet compose -- up -d             # Dockeri käitusaeg
  fi
}
```

Repo, millel puudub sihtkäitusaeg, saab selge keeldumise **pärast** andmeülekande etappi: pildid liiguvad ja juurutamise samm ütleb sulle, et repo ei deklareeri Kubernetese (ega Dockeri) teed, selle asemel et olekut rikkuda.

## Repositooriumi forkimine

`rdc repo fork` Kubernetese repol kopeerib alati andmed, alati koheselt. Lippu `--full` ega variante pole.

```bash
rdc repo fork --parent shop --tag joseph --cluster prod
```

See loob nimeruumi `shop-joseph` samas klastris, kloonib iga köite copy-on-write viisil (RBD-kloon Cephis, reflink PV-pildifailidest kohalikul taustasüsteemil) ja juurutab töökoormused sinna. Fork'i URL on koheselt elus vanema metamärgi sertifikaadi all, nii et uut sertifikaati ega DNS-kirjet ei väljastata.

Sihtkoha eskaleerimine:

- `--to-cluster <name>` forkib teise olemasolevasse klastrisse. Sama Ceph-taustasüsteem: RBD-kloon jääb copy-on-write'iks. Erinev taustasüsteem: push-masinavärk liigutab pildid.
- `--provider <p>` valmistab esmalt ette uue klastri, pesaspetsifikatsioonidega, mis vaikimisi peegeldavad lähteklastri kuju (lipud tühistavad selle).

KVM testlaboris mõõdetuna lõpetab nimeruumi fork umbes ühe kuni viie sekundiga, vanema töökoormus puutumatuna ja kaks nimeruumi lahknevad sõltumatult.

## Terve klastri forkimine või liigutamine

Terve klastri toimingud elavad `rdc cluster` grupis, kuna need toimivad erineval objektil (kogu koht koos kõigi selle repodega) ega saa väljenduda käsuna, mis võtab ühe repo nime. See on lipulaeva lugu.

```bash
# Kloonida terve klaster, sealhulgas selle repode andmed, uude klastrisse
rdc cluster fork --name prod --tag staging

# Liigutada terve klaster, sealhulgas selle repode andmed, teise masinasse või andmekeskusesse
rdc cluster migrate --name prod --to server-2
```

Mõlemad koordineerivad klastripiltide pluss iga repo PV-pildi copy-on-write kopeerimist, seejärel kirjutavad ümber sõlme identiteedi, nii et kloon või ümberpaigutatud klaster tõuseb tervelt oma uutel aadressidel. Kuna k3s salvestab juhttasandi oleku oma põimitud andmesalves, on klastripilt ise hetktõmmis: järjepidevuse järjekord on esmalt juhttasand, seejärel PV-d, seejärel agendid.

Ausad numbrid, mõõdetud otsast lõpuni KVM testlaboris:

| Toiming | Mida see teeb | Mõõdetud |
|---|---|---|
| Nimeruumi fork | Ühe repo nimeruumi pluss PV-de kloonimine kohapeal | ~1 kuni 5 s |
| Ühe pildi RBD-fork | Ceph-toega PV-klooni copy-on-write kopeerimine | ~5 s |
| Terve 2-sõlmelise klastri fork | Tühjendamine, juhttasandi ja agendi reflinkimine, identiteedi ümberkirjutamine uutele IP-dele, vanem puutumatuna | ~46 s |
| Masinatevaheline klastri ränne | Kuum eelkoopia pluss peata-ja-taaskäivita üleminek | ~16 s üleminek |

Vaikekäitumine on **krahhikindel ja viitetervikluse säilitav**: sama semantika mis toite väljalülitamise-sisselülitamise tsüklil, mida töökoormused ka näevad. Rakenduse-tasandi järjepidevad hetktõmmised on saadaval, kui töökoormuse failisüsteemid külmutatakse kopeerimise ajal. Seda ei esitleta tahtlikult null-seisakuna. Keegi teine ei paku üldse "forkida töötav klaster koos selle andmetega"; aus raamistus on lühike, mõõdetud üleminek, mitte turundusabsoluut.

## Salvestus: ceph-csi ja püsivad köited

Cephi valmistab ette renet-i cephadm-voog `ceph`-pesal, **väljaspool** ühtegi Kubernetese klastrit, ja klastrid tarbivad seda renet-mallitud ceph-csi manifestide kaudu. Iga klastri eksemplar (ja iga fork) saab oma RBD/RADOS-nimeruumi, mis on üürnikupõhise isoleerimise primitiiv. Salvestus asub kõigi klastrite all, nii et see toetab ka lihtsaid Docker-reposid ja andmesalve taustasüsteemi, ning klastri fork kloonib RBD-pilte Kubernetese all, selle asemel et forkida oma salvestuse taustasüsteemi.

Kohalikul taustasüsteemil (ilma Cephita) toetab renet-i kohalik PV-provisioneerija iga PV-d väikese copy-on-write pildifailiga andmesalves, mis kloonitakse reflinkiga fork'i ajal. Vaata [Serveri viide](/et/docs/server-reference) kettapõhise paigutuse ja renet-käskude jaoks.

## Distributsiooni valimine

Distro on abstraktsioon väikese, tegeliku liidesega (install, join, kubeconfig, healthcheck, upgrade ja nii edasi):

- **k3s** on vaikimisi ja ainus põimitud distributsioon. See on Apache-2.0, CNCF-sertifitseeritud, üksainus ümberpaigutatav binaar ning nii selle kaasasolev Traefik kui ka ServiceLB on keelatud Rediacci puhverserveri kasuks. Selle `--data-dir` seotakse käivitamisel, mis on täpselt see, mida klastri fork ja migrate vajavad, kui pilditee ühenduspunkti tee muutub. k3s on märgitud `repoEmbeddable`.
- **external** on oma-kubeconfig-kaasa. Ainult `getKubeconfig` ja `healthcheck` teevad tegelikku tööd; elutsükli verbid tagastavad esmaklassilised "ei kohaldu" tulemused vigade asemel.
- **RKE2** on planeeritud kolmas taustasüsteem FIPS/CIS klientidele, ei ole selle väljalaske osa.

Klastri fork ja migrate keelduvad töötamast mitte-`repoEmbeddable` distributsioonil selge veaga oleku rikkumise asemel, kuna klastri oleku põimimine andmesalve piltidesse nõuab andmekataloogi, mis seotakse käivitamisel.

## Register

Kaks erinevat pildiprobleemi, kaks tööriista:

- **Ülesvoolu valu** (Docker Hubi kiiruspiirid, keelatud tõmbamised, võrguühenduseta): põimitud [zot](https://zotregistry.dev/) pull-through puhver töötab juhtpesal `sync.onDemand`-iga mitme ülesvoolu vastu (docker.io, ghcr.io, quay.io). See on renetisse põimitud samamoodi nagu teised binaarid ja asendab ops-testregistri, nii et iga käivitus kasutab seda.
- **Klastrisisene levitamine**: k3s-i põimitud registripeegel laseb sõlmedel jagada juba tõmmatud pilte omavahel.

Ühendus on läbipaistev ja taaskäivitust mittevajav containerd `certs.d/hosts.toml` ja k3s-i `registries.yaml` kaudu. Repo-põhine containerd-hoidla klastripildi sees jääb tõe allikaks, mida fork'id ja migratsioonid liigutavad; register on puhver interneti ees, mitte kunagi olek.

## Võrgundus ja URL-id

Kubernetese repode URL-id järgivad lamedat skeemi, kus nimeruumi identiteet on volditud kõige vasakpoolsemasse silti ja klaster on stabiilne teine silt:

```
{service}--{repo}.{cluster}.{machine}.{base}          Kubernetese repo (nimeruum = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    fork (nimeruum = repo-tag)
```

Iga nimeruum ja iga fork pärib vanema metamärgi sertifikaadi ja DNS-kirje, nii et fork'i URL-id on koheselt elus ja uued sertifikaadid väljastatakse ainult siis, kui luuakse uus klaster või repo. Marsruuter avastab Kubernetese teenused, küsitledes klastrit `rediacc.*`-annoteeritud Service'ide osas, mis on Kubernetese analoog Dockeri siltide lugemisele. Vaata [Võrgundus](/et/docs/networking) marsruutimise mudeli jaoks ja [Arhitektuur](/et/docs/architecture) salvestuse taustasüsteemide jaoks.

## Autorlus

Rediacc kannab mitmeid kolmandate osapoolte binaare (k3s, zot ja teised, mida renet põimib). Prindi nende versioonid, SPDX litsentsi identifikaatorid ja lähtearhiivi URL-id igal ajal:

```bash
rdc credits
rdc credits --licenses    # täielik THIRD_PARTY_LICENSES tekst, mis on lisatud väljalasetega
```
