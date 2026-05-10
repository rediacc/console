---
title: "Instalação"
description: "Instale o CLI rdc no seu computador portátil com um único comando e verifique com rdc doctor."
category: "Tutorials"
subcategory: essentials
order: 1
language: pt
sourceHash: "99d4ca1a4f89278e"
---

# Instalação

Instalar o `rdc` são três passos: abra a página de instalação, escolha o seu sistema operativo e cole o comando no seu terminal. Normalmente demora um ou dois minutos no total.

## Ver o tutorial

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## Os três passos

![Three steps overview](/img/tutorials/tutorial-installation/slide-1.svg)

1. Abra a [página de instalação](/pt/install).
2. Escolha o seu sistema operativo.
3. Copie o comando de instalação e cole-o no seu terminal.

## Instalar na sua plataforma

A página de instalação gera o comando certo para si, mas aqui estão os comandos canónicos de uma linha.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> O prefixo `time` é um truque da shell que mostra quanto tempo um comando demorou. Usamo-lo ao longo desta série para que possa ver a velocidade real de cada passo. É opcional -- ignore-o se não quiser.

## Verificar a instalação

Assim que o script terminar, verifique se tudo o que o `rdc` precisa está presente:

```bash
time rdc doctor
```

O `rdc doctor` percorre o Node, o SSH e as restantes dependências do `rdc` e reporta quaisquer lacunas.

## Porquê o `rdc` vive no seu computador portátil

![rdc on your laptop, renet on the server](/img/tutorials/tutorial-installation/slide-2.svg)

O `rdc` é o CLI no seu computador portátil. O servidor executa um componente separado chamado `renet`, que o `rdc` provisiona e controla via SSH. Nunca precisa de fazer SSH para um servidor manualmente -- o `rdc` faz isso por si.

Vamos configurar isso corretamente nos próximos dois tutoriais.

---

Próximo: [Configuração de Chave SSH](/pt/docs/tutorial-ssh-keys).
