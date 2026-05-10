---
title: "SSH-Schlüsselkonfiguration"
description: "Konfigurieren Sie Ihren SSH-Schlüssel, damit rdc sich ohne Passwörter mit Ihren Servern verbinden kann."
category: "Tutorials"
subcategory: essentials
order: 2
language: de
sourceHash: "009a1bd345e93413"
---

# SSH-Schlüsselkonfiguration

`rdc` verbindet sich über SSH mit Ihren Servern, daher muss jeder Server Ihrem SSH-Schlüssel vertrauen. Insgesamt drei Schritte. Zwei sind einmalige Einrichtungsschritte, einer wiederholt sich für jeden neuen Server, den Sie hinzufügen.

## Tutorial ansehen

![Tutorial: SSH-Schlüsselkonfiguration](/assets/tutorials/tutorial-ssh-keys.cast)

## Die drei Schritte

![Generieren, kopieren, registrieren](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **Generieren** Sie einen SSH-Schlüssel auf Ihrem Laptop. Einmalig, für immer.
2. **Kopieren** Sie ihn auf Ihren Server. Wiederholen Sie diesen Schritt für jeden neuen Server.
3. **Registrieren** Sie den Schlüssel bei `rdc`. Einmalig, für immer.

## Schritt 1: Schlüssel generieren

Wenn Sie bereits einen Schlüssel haben, den Sie verwenden möchten, überspringen Sie diesen Schritt. Andernfalls:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` ist der moderne Standard: klein, schnell und gut unterstützt.

## Schritt 2: Schlüssel auf den Server kopieren

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

Ersetzen Sie `user` und `your-server-ip` durch den SSH-Benutzer und die IP-Adresse Ihres Servers. Sie werden ein letztes Mal nach Ihrem Serverpasswort gefragt. Danach ist keine Passwortauthentifizierung mehr erforderlich.

## Schritt 3: Schlüssel bei `rdc` registrieren

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

Das war es. Von nun an authentifiziert sich jeder `rdc`-Befehl mit diesem Schlüssel. Keine Passwörter mehr, keine interaktiven Abfragen mehr.

---

Weiter: [Ihren ersten Server hinzufügen](/de/docs/tutorial-add-server).
