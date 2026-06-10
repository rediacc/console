---
title: "Autostart e Recuperação"
description: "Como funciona o autostart, o reconciliador periódico que recupera repositórios que caem após o arranque, e como inspeccionar o estado de recuperação."
category: "Guides"
order: 5
language: pt
sourceHash: "05d8d5234e0901f6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Autostart e Recuperação

Os repositórios com autostart ativado levantam-se automaticamente no arranque. Se um cair depois, o reconciliador periódico traz-o de volta. Sem avisos. Sem reinício manual.

Para saber como activar ou desactivar o autostart num repositório, consulte [Serviços: Autostart no Arranque](/pt/docs/services#autostart-on-boot).

## Como funciona o autostart

Quando activa o autostart para um repositório, o Rediacc gera um keyfile LUKS aleatório de 256 bytes e adiciona-o ao slot 1 LUKS do volume encriptado. O keyfile fica guardado em:

```
{datastore}/.credentials/keys/{guid}.key
```

Isto permite à máquina montar o repositório sem pedir a frase-passe. O slot 0 LUKS (a sua frase-passe) não é alterado.

O slot do keyfile utiliza o KDF rápido PBKDF2: um keyfile aleatório de 256 bytes é a sua própria margem de segurança, pelo que um KDF resistente a memória apenas acrescentaria latência na montagem sem acrescentar protecção. As montagens concluem em bem menos de um segundo. Repositórios criados antes desta optimização ainda pagam uma derivação Argon2id de vários segundos por montagem; converta-os no local (repositório desmontado) com o comando de operador `renet repository kdf-migrate --name <guid>` na máquina. O slot 0 mantém Argon2id — a escolha certa para uma frase-passe humana.

No arranque, um serviço systemd one-shot chamado `rediacc-autostart.service` lê a lista de repositórios com autostart activado, monta cada um usando o respectivo keyfile, inicia o daemon Docker por repositório e executa o hook `up()` do Rediaccfile. No encerramento, o serviço executa `down()`, pára o Docker e fecha os volumes LUKS.

> **Nota de segurança:** O keyfile fornece acesso a nível de root ao repositório sem a frase-passe. Qualquer pessoa com acesso root ao servidor pode montar repositórios com autostart activado. Avalie isto em função do seu modelo de ameaça antes de activar o autostart em repositórios sensíveis.

## O hiato de recuperação

O autostart no arranque corre exactamente uma vez por arranque. O watchdog do router, que corre continuamente após isso, apenas reinicia *contentores dentro de um repositório já em execução com um daemon Docker activo*. Não consegue remontar um volume LUKS nem reiniciar um daemon Docker por rede que tenha parado.

Isto significa que se o volume LUKS de um repositório for desmontado ou o seu daemon Docker parar depois de o servidor ter arrancado, nem o serviço de arranque nem o watchdog o irão recuperar. Antes de existir o reconciliador, um repositório neste estado ficava parado até um operador intervir.

## Reconciliador periódico

O temporizador systemd `rediacc-autostart-reconcile.timer` dispara aproximadamente a cada 3 minutos e executa `renet repository reconcile`. Para cada repositório com autostart activado, o reconciliador verifica três coisas:

1. O volume LUKS está montado?
2. O daemon Docker por rede está a correr?
3. Os serviços do repositório estão activos?

Se alguma verificação falhar, o reconciliador recupera o repositório usando o seu keyfile: monta o volume, inicia o daemon Docker e executa `up()`. Não é necessária qualquer frase-passe.

Os repositórios que estão saudáveis, actualmente em uso por uma execução de backup cold, ou dentro da sua janela de back-off são ignorados.

### Back-off e marcadores de falha persistentes

Um repositório que não consegue recuperar não tenta imediatamente em cada tick. O reconciliador usa back-off exponencial:

| Número de falhas | Espera antes da próxima tentativa |
|------------------|-----------------------------------|
| 1 | 1 minuto |
| 2 | 2 minutos |
| 3 | 5 minutos |
| 4 | 15 minutos |
| 5+ | 30 minutos, depois 60 minutos |

Após 5 falhas consecutivas, o reconciliador escreve um ficheiro marcador durável em:

```
/var/lib/rediacc/reconcile/failed/{guid}
```

Este ficheiro sobrevive à rotação de logs. A sua presença significa que o repositório requer atenção do operador. O reconciliador regista a falha a nível de erro e deixa de tentar a recuperação automática para esse repositório até o marcador ser removido.

Causas comuns de falha de recuperação persistente:

- **Licença do repositório não confiável ou expirada**: a verificação de licença corre antes de `up()`.
- **Keyfile em falta**: se o keyfile em `{datastore}/.credentials/keys/{guid}.key` foi eliminado, o reconciliador não consegue montar o volume sem uma frase-passe.
- **Rediaccfile com erros**: um erro de sintaxe ou um hook `up()` que termina sempre com código não-zero.

### Relação com o watchdog do router

O reconciliador e o watchdog do router lidam com diferentes níveis de falha e são concebidos para se complementarem:

| Camada | O que trata |
|--------|-------------|
| **Watchdog do router** | Reinícios a nível de contentor dentro de um repositório em execução, montado, com um daemon Docker activo |
| **Reconciliador (`rediacc-autostart-reconcile.timer`)** | Recuperação a nível de repositório: remontagem LUKS, reinício do daemon Docker, re-execução de `up()` |

Se um único contentor falhar dentro de um repositório saudável, o watchdog trata disso. Se o daemon do repositório inteiro parar, o reconciliador trata disso.

## Inspeccionar o estado de recuperação

### Estado do temporizador e do serviço

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### Logs do reconciliador

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### Marcadores de falha persistentes

Liste os repositórios com marcadores de falha duráveis:

```bash
ls /var/lib/rediacc/reconcile/failed/
```

Cada nome de ficheiro é um GUID de repositório. Use `rdc config repository list` para mapear GUIDs a nomes de repositório.

Para remover um marcador depois de ter resolvido o problema subjacente, elimine o ficheiro:

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

O reconciliador tentará a recuperação novamente no próximo tick do temporizador.

## Páginas relacionadas

- [Serviços: Autostart no Arranque](/pt/docs/services#autostart-on-boot): activar e desactivar o autostart, gestão do keyfile
- [Backup e Restauro](/pt/docs/backup-restore): interacção do backup cold com serviços em execução
