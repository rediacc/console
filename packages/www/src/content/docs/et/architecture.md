---
title: Arhitektuur
description: >-
  Kuidas Rediacc töötab: kahe tööriista arhitektuur, adapteri tuvastamine, turvamudelja
  konfiguratsioonistuktuur.
category: Concepts
order: 0
language: et
---

# Arhitektuur

Sellel lehel selgitatakse, kuidas Rediacc kapoti all töötab: kahe tööriista arhitektuur, adapteri tuvastamine, turvamudelning konfiguratsioonistuktuur.

## Täispinu ülevaade

Liiklus voolab internetist läbi pöördproksi isoleeritud Dockeri daemonitesse, millest igaüks on tagatud krüpteeritud salvestusega:

![Täispinu arhitektuur](/img/arch-full-stack.svg)

Iga repositoorium saab oma Dockeri daemoni, loopback-IP-alamvõrgu (/26 = 64 IP-d) ja LUKS-krüpteeritud BTRFS-köite. Marsruudi server avastab töötavad konteinerid kõigist daemonitest ja edastab marsruutimiskonfiguratsiooni Traefik'ile.

## Kahe tööriista arhitektuur

Rediacc kasutab kaht binaari, mis töötavad koos SSH kaudu:

![Kahe tööriista arhitektuur](/img/arch-two-tool.svg)

- **rdc** töötab sinu tööjaamal (macOS, Linux või Windows). See loeb sinu kohalikku konfiguratsiooni, ühendub kaugmasinatega SSH kaudu ja kutsub välja renet'i käsud.
- **renet** töötab kaugserveris root-õigustega. See haldab LUKS-krüpteeritud kettapilte, isoleeritud Dockeri daemaneid, teenuste orkestreerimist ja pöördproksi konfiguratsiooni.

Iga käsk, mille sa kohalikult kirjutad, tõlgitakse SSH-kutseks, mis täidab renet'i kaugmasinas. Sul pole kunagi vaja käsitsi SSH kaudu serveritesse sisse logida.

Operaatorikeskseks rusikareeglitest vaata [rdc vs renet](/et/docs/rdc-vs-renet). Samuti saad kasutada `rdc ops` kohaliku VM-klastri käivitamiseks testimiseks, vaata [Eksperimentaalsed VM-id](/et/docs/experimental-vms).

## Konfiguratsioon

Kogu CLI olek salvestatakse `~/.config/rediacc/` alla tasasel JSON-konfiguratsioonifailides.

### Kohalik adapter (vaikimisi)

Vaikimisi isehostatava kasutuse jaoks. Kogu olek elab tööjaamal konfiguratsioonifailis (nt `~/.config/rediacc/rediacc.json`).

- Otsesed SSH-ühendused masinatega
- Väliseid teenuseid ei nõuta
- Ühe kasutaja, ühe tööjaama kasutus
- Vaikimisi konfiguratsioon luuakse automaatselt CLI esimesel kasutamisel. Nimetatud konfiguratsioonid luuakse käsuga `rdc config init --name <name>`

### Pilveadapter (eksperimentaalne)

Aktiveeritakse automaatselt, kui konfiguratsioon sisaldab välju `apiUrl` ja `token`. Kasutab Rediacc API-t olekuhalduseks ja meeskondliku koostöö jaoks.

- Olek salvestatud pilve API-sse
- Mitmekasutajaga meeskonnad rollipõhise juurdepääsuga
- Veebikonsoole visuaalseks haldamiseks
- Seadistatakse käsuga `rdc auth login`

> **Märkus:** Pilveadapteri käsud on eksperimentaalsed. Luba need, seades `REDIACC_EXPERIMENTAL=1`.

Mõlemad adapterid kasutavad samu CLI käsud. Adapter mõjutab ainult seda, kus olek salvestatakse ja kuidas autentimine toimib.

## Kasutaja rediacc

Kui käivitad `rdc config machine setup`, loob renet kaugserverisse süsteemikasutaja nimega `rediacc`:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (ei saa SSH kaudu sisse logida)
- **Eesmärk**: Omab repositooriumi faile ja käivitab Rediaccfile'i funktsioone

Kasutajale `rediacc` ei pääse otse SSH kaudu ligi. Selle asemel ühendub rdc SSH-kasutajana, mille sa seadistad (nt `deploy`), ja renet täidab repositooriumi toiminguid käsuga `sudo -u rediacc /bin/sh -c '...'`. See tähendab:

1. Sinu SSH-kasutajal on vaja `sudo` õigusi
2. Kõik repositooriumi andmed kuuluvad kasutajale `rediacc`, mitte sinu SSH-kasutajale
3. Rediaccfile'i funktsioonid (`up()`, `down()`) käivitatakse kasutajana `rediacc`

See eraldamine tagab, et repositooriumi andmetel on ühtne omandiõigus olenemata sellest, milline SSH-kasutaja seda haldab.

## Dockeri isoleerimine

Iga repositoorium saab oma isoleeritud Dockeri daemoni. Kui repositoorium ühendatakse, käivitab renet pühendatud `dockerd` protsessi unikaalse pistikupesaga:

![Dockeri isoleerimine](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Näiteks repositoorium, mille võrgu ID on `2816`, kasutab:
```
/var/run/rediacc/docker-2816.sock
```

See tähendab:
- Erinevate repositooriumide konteinerid ei näe üksteist
- Igal repositooriumil on oma pildivahemälu, võrgud ja köited
- Hosti Dockeri daemon (kui see on olemas) on täielikult eraldatud

Rediaccfile'i funktsioonidel on automaatselt `DOCKER_HOST` seatud õigele pistikupesale.

Kui AI agent siseneb repositooriumisse käsuga `rdc term connect -r <repo>`, kehtib sama isoleerimine: seanss töötab väheste õigustega kasutajana `rediacc` (UID 7111), eraldiseisvas ühenduspunkt-nimeruumis, kusjuures `DOCKER_HOST` on piiratud selle ühe repo daemoni pistikupesaga. Fork-esmane töövoog ühendab selle käitusaegse isoleerimise CoW-kloonimise primitiiviga: agent tegutseb ülesandekohase fork'i peal, mitte grand (tootmis) repositooriumides. Täieliku liivakastimudeli, ülekatte semantika ja arendaja vastutuse piiri väliste teenuste volituste osas vaata [AI agendi ohutus ja turvamehhanismid](/et/docs/ai-agents-safety).

### Daemoni teekava paigutus

Dockeri andmed ja konfiguratsioon salvestatakse repositooriumi ühenduspunkti sisse, hoides iga daemoni täielikult isoleerituna hostist ja teistest repositooriumidest.

**Repo-kohane paigutus:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Dockeri andmejuur
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Dockeri konfiguratsioon
```

**Iseseisev paigutus** (daemonid, mis pole repositooriumi ühenduspunktiga seotud):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**Jagatud käitusaegne tee** (muutumatu):
```
/run/rediacc/docker-{N}.sock
```

See ühtne paigutus kõrvaldab kirjutuskaitstud/kirjutatavate ühenduspunktide konfliktid, mis tekkisid siis, kui daemoni teed olid jaotatud hosti failisüsteemi ja krüpteeritud köite vahel. Nii repo-kohased kui ka iseseisvad daemonid järgivad sama kataloogistruktuuri, nii et tööriistad ja diagnostika töötavad mõlemal juhul identselt.

## LUKS-krüpteerimine

Repositooriumid on LUKS-krüpteeritud kettapildid, mis on salvestatud serveri andmesalvestile (vaikimisi: `/mnt/rediacc`). Iga repositoorium:

1. Omab juhuslikult genereeritud krüpteerimisvõtmelauset ("volitust")
2. Salvestatakse failina: `{datastore}/repos/{guid}.img`
3. Ühendatakse `cryptsetup` kaudu, kui sellele pääsetakse ligi

Volitus salvestatakse sinu konfiguratsioonifailis, kuid **mitte kunagi** serveris. Ilma volituseta ei saa repositooriumi andmeid lugeda. Kui automaatne käivitamine on lubatud, salvestatakse serverisse teisene LUKS-võtmefail, et võimaldada automaatset ühendamist käivitumisel.

## Konfiguratsioonistuktuur

Iga konfiguratsioon on JSON-fail, mis on salvestatud `~/.config/rediacc/` alla. Vaikimisi konfiguratsioon on `rediacc.json`; nimetatud konfiguratsioonid kasutavad nime failinimena (nt `production.json`). Väljad on grupeeritud eesmärgi järgi: `resources` hoiab juurutusi, `credentials` hoiab saladusi, `account` hoiab pilve vaikeväärtusi, `infra` hoiab TLS/DNS seadeid ja `encryption` hoiab välja-kohast puhkeoleku olekut. Tippnivoo `schemaVersion: 2` diskriminaator kinnitab edasisuunalise ühilduvuse.

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
    "machines": {
      "prod-1": {
        "ip": "203.0.113.50",
        "user": "deploy",
        "port": 22,
        "datastore": "/mnt/rediacc",
        "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
      }
    },
    "storages": {
      "backblaze": {
        "provider": "b2",
        "vaultContent": { "...": "..." }
      }
    },
    "repositories": {
      "webapp": {
        "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "credential": "base64-encoded-random-passphrase",
        "networkId": 2816
      }
    }
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**Põhigrupid:**

| Grupp | Sisu |
|---|---|
| `schemaVersion` | Diskriminaator (praegu `2`). Laadijad lükkavad tundmatud versioonid tagasi. |
| `id` / `version` | Muutumatu UUID + monotoonne loendur; kasutatakse optimistliku lukustamise jaoks kaugel konfiguratsioonisalves. |
| `defaults.*` | Mitte-tundlikud käitusaegse vaikeväärtused (`machine`, `language`, `pruneGraceDays`, `universalUser`, `nextNetworkId`). |
| `credentials.ssh` | Sisseehitatud SSH-võtmepaar + `knownHosts`. Asendab pärandit `ssh.privateKeyPath` (enam pole failiteede kaudsust; sisu lahendatakse laadimisajal ja salvestatakse sisse). |
| `credentials.cfDnsApiToken` | Cloudflare DNS-01 ACME token. |
| `credentials.masterPasswordVerifier` | Esineb ainult siis, kui `encryption.mode === "master-password"`. |
| `resources.machines.*` | SSH-ühenduse üksikasjad masina kohta. |
| `resources.storages.*` | rclone-ühilduv välisvaru varukoopiate volitused. |
| `resources.repositories.*` | Repo-kohane GUID + LUKS-volitus + SSH-võti liivakastis isoleeritud agendi juurdepääsuks. |
| `infra.acmeCertCache.*` | Vahemällu talletatud Traefik acme.json, gzip+base64, domeeni järgi võtmestatud. |
| `encryption.mode` | `"plaintext"` (vaikimisi) või `"master-password"`. |
| `encryption.encryptedFields` | Krüpteeritud puhul: pointeri järgi AES-GCM-ploki kaart (`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`). Üks avamise viip seansi kohta dekrüpteerib välju lugemisel. |
| `remote` | Esineb ainult siis, kui konfiguratsioon on sünkroonitud krüpteeritud konfiguratsioonisalvega; vaata [Krüpteeritud konfiguratsioonisalv](/et/docs/config-storage). |

**Redigeeri turvaliselt CLI-ga, mitte `vim`-iga:**

```bash
# Pointeri-aadressiga ühe välja redigeerimised (teadmisväravaga tundlike teede jaoks)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# Täisredaktor redakteeritud JSONC projektsiooniga (ainult inimestele)
rdc config edit

# Kirjutuskaitstud JSONC dump, ohutu skriptide ja agentide jaoks
rdc config edit --dump

# Vaata iga muudatust + keeldumist + paljastamist auditi logis
rdc config audit log --since 24h
rdc config audit verify
```

> See fail sisaldab tundlikke andmeid (SSH-privaatvõtmed, LUKS-volitused, Cloudflare tokenid). See salvestatakse õigustega `0600` (ainult omanik saab lugeda ja kirjutada). Ära jaga seda ega lisa versioonihaldusesse. Kui mõni `rdc` käsk seda loeb, [redakteeritakse](/et/docs/ai-agents-safety) tundlikud väljad vaikimisi: lihttekst ilmub ainult koos `--reveal`-iga interaktiivsel inimese TTY-l.

### Ümbrik v2 ja serveripoolne jõustamine

Kui konfiguratsioon sünkroonitakse [krüpteeritud konfiguratsioonisalvega](/et/docs/config-storage), mähib CLI iga tundliku välja välja-kohasesse HMAC-sidemesse ja kannab need kohustused lihtteksti ümbrikku. Server näeb ainult kuueteistkümnendarvude kokkuvõtteid: mitte kunagi väärtusi: kuid saab jõustada teadmisväravaid igal kirjutusel:

- **Eeltingimuse kontroll**: `PUT /configs/<id>` puhul esitab klient kokkuvõtted, mida ta väidab teadvat muudetavate teede kohta. Server võrdleb salvestatud ümbriku kohustistega. Lahknevus: `409 precondition_failed` koos `mismatchedPaths`. Null-teadmine: server ei näe kunagi lihtteksti.
- **Anti-allagradeerimine**: uus ümbrik peab siduma iga tundliku tee, mida eelmine ümbrik sidus. Agent ei saa teed kohustistest eemaldada tulevase eeltingimuse vältimiseks.
- **Ümbriku versiooni kinnitamine**: server lükkab tagasi ümbrikud, millel puudub `envelopeVersion: 2`, koos `400 unsupported_envelope_version`. Kahekordset vastuvõtmise akent pole.
- **Välja-kohane krüpteerimine puhkeolekus** (CLI-poolne): kui `encryption.mode === "master-password"`, muutub iga saladus individuaalseks AES-GCM-plokiks, mis on võtmestatud peaparooliga. Lugemisel ei käivita see viipa, välja arvatud siis, kui käsk tegelikult puudutab saladust (nii jääb `rdc machine list` viipadeta).

Kohustuse võti (FCK) tuletatakse klientide poolel CEK-ist via `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")` konfiguratsioonipõhise soolaga. `fckSalt` pööramine tühistab kõik eelmised kohustused, sundides täielikku ümberarvutamist: kasulik CEK pööramisel.
