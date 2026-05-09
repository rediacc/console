---
title: "SSH võtme seadistamine"
description: "Seadista oma SSH võti, et rdc saaks serveritega ilma paroolideta ühenduda."
category: "Tutorials"
subcategory: essentials
order: 2
language: et
sourceHash: "009a1bd345e93413"
---

# SSH võtme seadistamine

`rdc` ühendub sinu serveritega üle SSH, seega peab iga server sinu SSH võtit usaldama. Kokku kolm sammu. Kaks neist on ühekordne seadistus ja üks kordub iga uue serveri lisamisel.

## Vaata juhendvideot

![Tutorial: SSH key configuration](/assets/tutorials/tutorial-ssh-keys.cast)

## Kolm sammu

![Generate, copy, register](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **Genereeri** SSH võti oma sülearvutis. Üks kord, igaveseks.
2. **Kopeeri** see serverisse. Korda iga uue serveri puhul.
3. **Registreeri** võti `rdc`-s. Üks kord, igaveseks.

## 1. samm: genereeri võti

Kui sul on juba võti, mida soovid kasutada, jäta see samm vahele. Vastasel juhul:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` on kaasaegne vaikimisi valik: väike, kiire ja laialt toetatud.

## 2. samm: kopeeri see serverisse

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

Asenda `user` ja `your-server-ip` oma serveri SSH kasutajanime ja IP-aadressiga. Sinult küsitakse serveri parooli viimast korda. Pärast seda ei ole parooliga autentimine enam vajalik.

## 3. samm: registreeri võti `rdc`-s

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

See ongi kõik. Edaspidi autentib iga `rdc` käsk selle võtmega. Rohkem paroole ega interaktiivseid päringuid.

---

Edasi: [Esimese serveri lisamine](/en/docs/tutorial-add-server).
