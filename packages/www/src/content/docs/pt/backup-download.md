---
title: "Download de backup"
description: "Copia a imagem encriptada de um repositório para um diretório local ou uma unidade externa, atualiza-a no local nas execuções seguintes ou reconstrói-a diretamente a partir do armazenamento de backup, sem qualquer máquina."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: pt
sourceHash: "c52e6a0471befc30"
---

# Download de backup

`rdc backup download` mantém uma cópia da imagem encriptada de um repositório num diretório local ou numa unidade externa. A cópia é o mesmo texto cifrado que está na máquina, pelo que nada é desencriptado pelo caminho. A credencial que a abre fica na configuração, o que faz da inscrição no [config storage](/pt/docs/config-storage) a forma de a manter segura. Sem a credencial, a imagem não pode ser aberta.

Há duas origens. Uma máquina em execução é a predefinida. O armazenamento de backup é a outra, selecionada com `--store`.

## Download a partir de uma máquina

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to` indica um diretório existente e com permissão de escrita. Nunca é criado, por isso a unidade deve ser montada antes. A imagem fica em `<machine>/<name>.<tag>.img`, com um ficheiro `.state.json` ao lado.

Cada execução tira um snapshot novo do repositório, mantido apenas enquanto a transferência dura, envia as diferenças com rsync e compara um sha256 do resultado com o snapshot da máquina.

| Flag | Efeito |
|------|--------|
| `--all -m <machine>` | Copiar todos os repositórios grand colocados na máquina |
| `--include-forks` | Com `--all`, copiar também os forks |
| `--bwlimit <rate>` | Limitar a largura de banda de rede, por exemplo `100Mbps` ou `12.5M` |
| `--checkpoint` | Fazer checkpoint e congelar o repositório antes do snapshot (backup a quente) |
| `--retries <n>` | Novas tentativas dentro da execução após uma falha de rede (predefinição 3) |
| `--skip-verify` | Saltar a comparação sha256; o checksum do próprio rsync continua a correr |
| `--skip-space-check` | Avisar em vez de recusar quando o destino pode não ter espaço livre |

### Atualizar a cópia

Uma segunda execução atualiza a imagem existente no local através do delta do rsync. Uma execução semanal envia apenas o que mudou, e o destino precisa de espaço para uma cópia da imagem, não para duas. Antes de uma execução começar, o espaço livre é verificado face ao tamanho da imagem, e `--skip-space-check` transforma uma recusa num aviso.

### Execuções interrompidas e retoma

O ficheiro de estado regista `status`. O valor é `incomplete` desde antes de o primeiro byte ser escrito até uma execução ser verificada, e uma imagem `incomplete` não é utilizável. Ctrl-C, uma ligação perdida ou um processo terminado à força deixam-na assim. Voltar a executar o mesmo comando retoma, e só as diferenças são enviadas. O comando termina com código 0 quando o estado passa a `complete`.

### Requisitos

A transferência precisa de rsync 3.1.3 ou posterior neste computador e não tem alternativa por SFTP. As distribuições Linux incluem-no. No macOS, `brew install rsync` substitui o openrsync fornecido de origem, que não consegue executar a transferência. No Windows, instala-se o MSYS2 com o pacote rsync, ou usa-se a aplicação de ambiente de trabalho.

### Unidades externas

O sistema de ficheiros do destino decide o que cabe.

- **FAT32** não consegue guardar um ficheiro com mais de 4 GiB, e o comando recusa a execução.
- **exFAT** sem suporte para ficheiros esparsos guarda a imagem com o seu tamanho aparente completo, pelo que a verificação de espaço livre conta esse tamanho.
- Um **snapshot copy-on-write** tirado localmente do destino (btrfs, ZFS, APFS) mantém versões anteriores da imagem. Cada atualização no local custa então os blocos alterados além dos antigos.

## Download a partir do armazenamento de backup

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store` reconstrói a imagem diretamente a partir do armazenamento de chunks, sem qualquer máquina envolvida. O token em `REDIACC_TOKEN` precisa dos scopes `backup:read` e `backup:restore`. Um login da CLI nunca inclui `backup:restore`, por isso o token cria-se na página API Tokens do portal. Tem de pertencer a uma equipa e ter sido criado por um proprietário ou administrador atual da organização.

`--store` aceita exatamente um nome de repositório. Não aceita `-m`, `--checkpoint`, `--all`, `--include-forks`, `--bwlimit`, `--retries`, `--skip-verify` nem `--skip-space-check`: a obtenção a partir do armazenamento tem a sua própria retoma e verifica cada chunk.

A imagem é escrita em `<dir>/<name>.<tag>.img`. Uma obtenção interrompida mantém a cópia parcial, e o mesmo comando retoma a partir dela.

### Escolher um snapshot com `--at`

Por predefinição, obtém-se o snapshot mais recente. `--at <time|snapshot>` seleciona outro, seja uma hora em ISO 8601 ou um id de snapshot. Aplica-se apenas com `--store`.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

Numa plataforma que não seja Linux, a imagem obtida está encriptada e não pode ser aberta localmente. Envia-se para uma máquina Linux com `rdc backup upload`.

## Enviar uma cópia de volta

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload` envia uma imagem descarregada para uma máquina e regista-a como um novo repositório. A transferência retoma após uma interrupção, e a máquina verifica o sha256 e o cabeçalho LUKS antes de colocar a imagem. O ficheiro de estado ao lado da imagem fornece a credencial. Quando esse ficheiro se perde, `--from-repo <name>` indica o repositório que a fornece.

| Flag | Efeito |
|------|--------|
| `--as <name>` | Nome do novo repositório (predefinição: o nome da imagem) |
| `--datastore <name>` | Colocar a imagem num datastore indicado pelo nome |
| `--from-repo <name>` | Fornecer a credencial e a linhagem quando o ficheiro de estado é inutilizável |
| `--bwlimit <rate>`, `--retries <n>` | Iguais aos do download |
| `--up` | Iniciar o repositório depois de registado |
| `--skip-verify` | Saltar a comparação com o sha256 registado no download |

## Snapshots de transferência obsoletos

Uma transferência terminada à força pode deixar o seu snapshot na máquina. `rdc machine status` conta os snapshots de transferência obsoletos no resumo do pool, e `rdc machine prune <machine> --dry-run` lista-os. Executar `rdc machine prune <machine>` remove-os.

Ver [Backup e Restauro](/pt/docs/backup-restore) para os snapshots para o armazenamento de chunks.
