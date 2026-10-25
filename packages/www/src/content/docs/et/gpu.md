---
title: "GPU"
description: "Hoidla juurdepääs GPU-le CDI seadmeloa kaudu: masina GPU-de loetlemine, seadmete andmine ja tagasivõtmine hoidla kaupa, kaardi ainukasutuseks reserveerimine ja töö WSL-is."
category: "Guides"
tags:
  - containers
  - operations
subcategory: workloads
order: 7
language: et
sourceHash: "5a113ad69c52c63d"
---

# GPU-d

Hoidla pääseb GPU juurde ainult **seadmeloa** kaudu. Masin avaldab oma GPU-d nimega seadmetena ja operaator annab hoidlale nimed, mida see tohib kasutada. Loata hoidla GPU-d ei saa ning [hargnemine](/et/docs/repositories) algab ilma loata ka siis, kui lähtehoidlal on luba olemas.

Nimed järgivad standardit Container Device Interface (CDI), millega Docker 25 ja uuemad kirjeldavad seadet ning kõike, mida konteiner selle kasutamiseks vajab. CDI nimi on kujul `<vendor>/<class>=<device>`, näiteks `nvidia.com/gpu=all`.

## Mis on CDI luba

Iga hoidla käitab oma Dockeri deemonit API värava taga, mis keelab kõik viisid riistvara konteinerile külge panna, mistõttu GPU-ni ei jõua `docker run` lippudega. Luba on ainus uks. See salvestab ühe hoidla jaoks täpse CDI nime ja värav laseb seejärel läbi konteineri päringu, mis nimetab just seda seadet ja ühtegi teist mitte.

- Load jõustuvad järgmisest Dockeri päringust, deemoni taaskäivitust pole vaja.
- Luba nimetab täpselt ühte seadet. Loa `nvidia.com/gpu=all` andmine lubab nime `nvidia.com/gpu=all`, kuid mitte nime `nvidia.com/gpu=0`. Hoidlale ühe kaardi andmiseks antakse selle kaardi nimi.
- Luba kontrollitakse kirjutamisel masina seadmespetsifikatsioonide vastu, seega valesti kirjutatud nimi lükatakse tagasi, mitte ei salvestata.
- Luba kuulub hoidlale, kelle jaoks see anti. Hargnemised ja koopiad vajavad oma luba.

## Masina seadistamine

`rdc machine setup <machine>` tuvastab masina GPU-d ja salvestab tulemuse faili `/etc/rediacc/gpu/inventory.json`. Kui masinas on NVIDIA GPU, paigaldab seadistus ka NVIDIA Container Toolkiti ja loob CDI spetsifikatsiooni asukohta `/etc/cdi/nvidia.yaml`. GPU-ta masin saab samuti inventuurifaili, milles on tühjad loendid.

Tööriistakomplekti paigaldust juhib `renet setup` valik `--install-nvidia-toolkit`:

| Väärtus | Käitumine |
|---|---|
| `auto` | Tööriistakomplekt paigaldatakse, kui masinas on NVIDIA GPU. See on vaikeväärtus. |
| `true` | Tööriistakomplekt paigaldatakse igal juhul. |
| `false` | Tööriistakomplekt jäetakse vahele ja NVIDIA spetsifikatsiooni ei looda. |

Seadistus ei konfigureeri ühtegi konteinerikeskkonda, sest lubatud on ainult `runc`. Tööriistakomplekti kasutatakse üksnes spetsifikatsiooni jaoks ja spetsifikatsioon luuakse igal seadistusel uuesti, et see järgiks draiveri muutusi.

Kaks seadmetüüpi pärinevad Rediaccilt endalt ega vaja tootja kasutajaruumi komponente, sest need vastendavad ainult seadmesõlmi:

| Tüüp | Seadmed | Allikas |
|---|---|---|
| `rediacc.io/dri` | Üks iga renderdussõlme kohta, näiteks `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | `gpu<N>` ühe AMD kaardi jaoks ja `all` | `/dev/kfd` pluss kaardi renderdussõlm |

NVIDIA seadmed tulevad tööriistakomplekti spetsifikatsioonist: `nvidia.com/gpu=all` ja üks nimi kaardi kohta. AMD arvutuseks on vaja ROCm-i kasutajaruumi konteineri pildis, sest seadistus ROCm-i ei paigalda.

## GPU-de loetlemine

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

Tabelis on iga GPU nimi, draiveri versioon ja mälu, platvorm (natiivne või WSL), inventuuri vanus ning iga CDI seadme nimi, mida saab anda. `-o json` väljastab inventuuri sellisena, nagu see masinas on salvestatud. Praegu kehtivad load loetakse masinast reaalajas.

## Andmine ja tagasivõtmine

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` on hoidla nimi, soovi korral koos masinaga, näiteks `gpu-a@wsl-gpu`. Mõlemat käsku võib korrata erinevate `--device` väärtustega. Pärast andmist käivitub selle hoidla konteiner koos seadmega:

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

Sama konteiner lükatakse tagasi hoidlas, millel luba pole, ja teade nimetab puuduva loa.

## Ainukasutusload

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

Ainukasutusluba reserveerib seadme ühele hoidlale. See lükatakse tagasi, kui sama nime hoiab mõni teine hoidla, ja kuni see kehtib, lükatakse tagasi selle nime andmine igale teisele hoidlale. Kontroll tehakse andmise hetkel, lukustuse all, mis katab kõik masina load.

Ainukasutusluba on reservatsioon, mitte ajastaja. Kaks konteinerit samas loaga hoidlas jagavad kaarti endiselt.

## Tagasilükatavad kirjapildid

Iga muu tee GPU-ni jääb keelatuks, olgu luba olemas või mitte. CDI vorm asendab neist igaühe.

| Keelatud | Kasuta selle asemel |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| `runtime: nvidia` Composes | `devices: [nvidia.com/gpu=all]` |
| `deploy.resources.reservations.devices` Composes | `devices: [nvidia.com/gpu=all]` |
| `gpus: all` Composes | `devices: [nvidia.com/gpu=all]` |
| Toored `/dev/dri` või `/dev/kfd` seadmed või bind kataloogi `/dev` all | `rediacc.io/dri=renderD128` või `rediacc.io/amd=gpu0` |
| Seadme cgroup-reeglid | Seadme CDI luba |

Compose'i teenus, mis kasutab antud seadet, näeb välja selline:

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

Rühma, näiteks `video` või `render`, lisamine `group_add` kaudu on lubatud, kuid ei anna midagi, sest rühm ei ava ligipääsu seadmele, mida hoidlale pole antud.

## WSL

WSL2-s pakub Windowsi draiver GPU-d läbi `/dev/dxg` ja teekide kataloogis `/usr/lib/wsl/lib`. Masin teatab oma platvormiks `wsl` ja seadistus loob NVIDIA spetsifikatsiooni WSL-i vormingus:

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

Draiver asub Windowsi poolel, seega võetakse seal tehtud uuendus arvesse järgmisel `rdc machine setup` käivitamisel. Andmise, loetlemise ja tagasivõtmise käsud töötavad samamoodi nagu natiivses masinas.

## Natiivne NVIDIA

Natiivses NVIDIA masinas loob tööriistakomplekti teenus `nvidia-cdi-refresh` spetsifikatsiooni uuesti pärast paigaldust, draiveri muutust ja käivitust. Seadistus suunab selle faili `/etc/cdi/nvidia.yaml`, ainsasse spetsifikatsioonikataloogi, mida hoidla Dockeri deemon loeb. Kui `nvidia-persistenced` töötab, tehakse selle sokkel hoidlate deemonitele nähtavaks, sest spetsifikatsioon ühendab selle konteineritesse.
