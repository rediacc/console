---
title: "rdc repo diff"
description: "Exibir um diff em estilo git, ao nível de arquivo, entre dois repositórios bifurcados copy-on-write, comparando suas imagens criptografadas no nível de bloco, sem descriptografia."
category: Reference
subcategory: advanced
order: 40
language: pt
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff` informa quais arquivos mudaram entre dois repositórios relacionados: uma bifurcação e seu repositório pai, ou quaisquer dois repositórios que compartilhem um ancestral copy-on-write. Passe `--name <fork>` para comparar uma bifurcação contra o pai que a configuração local registra para ela, ou adicione `--base <repo>` para comparar contra um repositório relacionado arbitrário, onde `--base` é o lado base (antigo) e `--name` é o lado alvo (novo). O comando é somente leitura e nunca descriptografa as imagens. Ele as compara no nível de bloco na máquina remota, portanto o custo acompanha o número de blocos alterados, não o tamanho do repositório: um repositório de 1 GB e um de 100 GB com as mesmas edições levam o mesmo tempo. Se todo o repositório mudou, a contagem de blocos escala com o tamanho e assim também o custo.

## Quando usar

Então: use `repo diff` antes de promover uma bifurcação. Um agente de IA ficou solto em uma cópia bifurcada da produção e você quer ver exatamente quais arquivos ele tocou antes de mesclar a mudança de volta: `repo diff --name <fork> -m <machine>` oferece essa lista de arquivos em segundos. Segundos. Após uma restauração de recuperação de desastres, faça diff do fork restaurado contra o snapshot que deveria reproduzir para confirmar que o conjunto de arquivos esperado voltou e nada mais divergiu. Para uma bifurcação de longa vida que funcionou ao lado de seu pai por semanas, o diff mostra divergência acumulada (edições de configuração, acumulação de log, migrações de esquema) sem montar e percorrer ambas as árvores manualmente.

Não use em repositórios não relacionados. Os dois lados devem compartilhar um ancestral copy-on-write, porque a comparação funciona no histórico de blocos compartilhado. Também não é uma ferramenta de diff binário: `--content` produz saída em nível de linha apenas para arquivos de texto, e binários informam `Binary files differ`.

## Referência de comando

### Sinopse

```bash
rdc repo diff --name <fork> -m <machine>            # diff a fork against its parent
rdc repo diff --name <fork> --base <repo> -m <machine>   # diff against an arbitrary related repo
```

### Opções

| Opção | Descrição | Padrão |
|--------|-------------|---------|
| `--name <name>` | Repositório a inspecionar (o alvo, lado novo). Obrigatório. | obrigatório |
| `--base <name>` | Repositório contra o qual fazer diff (a base, lado antigo). Padrão para o pai de `--name`, resolvido da configuração local. | pai de `--name` |
| (sem flag de formato) | Saída de status de nome: uma letra colorida `A`/`M`/`D`/`R` por arquivo alterado mais um resumo de uma linha. | ativado |
| `--name-only` | Um caminho alterado por linha, sem letra de status. Compatível com pipe. | desativado |
| `--stat` | Magnitude de alteração por arquivo (deltas de byte e bloco) com rodapé de totais. | desativado |
| `--content <path>` | Diff de texto unificado de um único arquivo. Somente texto; binários informam `Binary files differ`. | desativado |
| `--json` | Saída estruturada para agentes e scripts. | desativado |
| `--fast` | Pule a etapa de confirmação de hash de conteúdo e confie no filtro de blocos. Mais rápido, mas pode sobre-relatar arquivos como Modified. | desativado |
| `-m, --machine <name>` | Máquina alvo. Obrigatório. | obrigatório |
| `--debug` | Diagnósticos verbosos em stderr. | desativado |
| `--skip-router-restart` | Pule a etapa de reinicialização do roteador. | desativado |

## Exemplos

### Status de nome padrão contra o pai

Com apenas `--name`, a bifurcação é comparada contra o pai registrado na configuração local. Aqui a bifurcação `test-1gb:fork1` tem um arquivo modificado:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Fazendo diff contra uma base explícita

Passe `--base` para fazer diff contra um repositório relacionado arbitrário. `--base` é o lado base (antigo), `--name` é o lado alvo (novo):

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Magnitude de alteração com `--stat`

`--stat` adiciona o delta de byte e bloco por arquivo e um rodapé de totais:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### Apenas caminhos, canalizados para uma ferramenta

`--name-only` imprime um caminho por linha sem letra de status, pronto para alimentar outro comando:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### Diff de nível de linha de um arquivo

`--content` produz um diff unificado de um único arquivo de texto:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### Filtrando JSON com jq

`--json` emite o envelope estruturado em stdout, portanto é canalizado perfeitamente em `jq`:

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## Formatos de saída

### Status de nome (padrão)

Cada arquivo alterado recebe uma letra de status e seu caminho. `A` é adicionado, `M` modificado, `D` deletado, `R` renomeado (com o caminho antigo mostrado). Uma linha de resumo segue com a contagem por categoria.

### `--name-only`

Um caminho por linha, sem letra de status, sem resumo. Use quando um comando downstream quiser uma lista limpa de arquivos.

### `--stat`

Cada linha contém o delta de byte e bloco do arquivo. Um rodapé relata a contagem total de arquivos e total de bytes tocados. Isso mostra onde está o peso de uma alteração, não apenas quais arquivos se moveram.

### `--content <path>`

Um diff unificado padrão (cabeçalhos `---`/`+++`, chunks `@@`) para um arquivo de texto. Arquivos binários informam `Binary files differ` e não produzem chunks.

### `--json`

O resultado estruturado completo. Os dados vão para stdout; progresso e diagnósticos vão para stderr, portanto o JSON é canalizado perfeitamente em `jq` ou outro analisador mesmo enquanto o progresso está sendo impresso.

## Esquema JSON

A CLI envolve o resultado renet no envelope padrão (`success`, `command`, `data`, `errors`, `warnings`, `metrics`). O resultado do diff fica em `data` com campos snake_case:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

Cada objeto em `entries[]` descreve um caminho alterado:

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | Adicionado, Modificado, Deletado ou Renomeado. |
| `path` | string | Caminho no lado alvo (ou lado base para uma deleção). |
| `old_path` | string | Caminho anterior. Presente apenas em renomeações. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | Tipo de entrada. |
| `old_size` | number | Tamanho em bytes no lado base. |
| `size` | number | Tamanho em bytes no lado alvo. |
| `bytes_changed` | number | Bytes que diferem, arredondados para blocos inteiros. |
| `blocks_changed` | number | Número de blocos alterados. |
| `inode` | number | Número do inode, usado para detecção de renomeação. |
| `content_changed` | boolean | Se o conteúdo do arquivo (não apenas metadados) mudou. |
| `mode_changed` | boolean | Se o modo do arquivo mudou. `old_mode`/`new_mode` estão presentes quando verdadeiro. |
| `uid_changed` | boolean | Se o proprietário mudou. `old_uid`/`new_uid` estão presentes quando verdadeiro. |
| `gid_changed` | boolean | Se o grupo mudou. `old_gid`/`new_gid` estão presentes quando verdadeiro. |
| `old_target` / `new_target` | string | Alvos de symlink. Presentes para symlinks alterados. |

Para os campos do envelope e as regras de detecção automática que emitem JSON em ambientes não-TTY, veja a [Referência de Saída JSON](/pt/docs/ai-agents-json-output).

## Como funciona

Um repositório é um arquivo de imagem LUKS2 em um pool btrfs, e uma bifurcação é uma reflink de tempo constante dessa imagem. `repo diff` compara as duas imagens criptografadas no nível de bloco via FIEMAP, lendo apenas metadados do sistema de arquivos e nunca descriptografando nada. Ele desloca os offsets de ciphertext alterados pelo offset de dados LUKS para obter offsets de dispositivo ext4, depois mapeia esses offsets de volta para nomes de arquivos através do mapa de extensões ext4 de cada arquivo. Uma caminhada de identidade de inode final de ambas as montagens reconcilia o resultado em entradas Adicionado, Modificado, Deletado e Renomeado. Como o trabalho é limitado pela contagem de blocos alterados, o diff é independente do tamanho do repositório, e porque reutiliza uma montagem ao vivo no local, ele nunca perturba um repositório em execução. O mecanismo completo é descrito em [Git diff para imagens de disco criptografadas](/pt/blog/git-diff-for-encrypted-disk-images).

## Limitações

- **Apenas bifurcações relacionadas.** Ambos os lados devem compartilhar um ancestral copy-on-write. Não há comparação significativa em nível de bloco entre repositórios não relacionados.
- **A detecção de renomeação é baseada em inode.** Um arquivo é relatado como renomeado quando o mesmo inode aparece em um novo caminho. Uma exclusão e recriação (um novo inode) mostra como uma entrada Deletado mais Adicionado, não uma renomeação.
- **`--content` é apenas texto.** Produz chunks em nível de linha para arquivos de texto. Binários informam `Binary files differ`.
- **`--fast` pode sobre-relatar Modified.** Ele confia no filtro de blocos e pula a confirmação de hash de conteúdo, portanto um arquivo cujos blocos se moveram sem alterar conteúdo pode aparecer como Modified.
- **O tempo de caminhada de extensão escala com fragmentação, não com tamanho.** Um sistema de arquivos muito fragmentado tem mais extensões a mapear, o que prolonga a caminhada mesmo quando o volume de bytes de alterações é pequeno.

## Veja também

- [rdc repo fork](/pt/docs/repositories). Crie a bifurcação copy-on-write que este comando faz diff.
- [rdc repo status](/pt/docs/repositories). Estado atual de um único repositório.
- [rdc repo cat](/pt/docs/repositories). Leia um único arquivo fora de um repositório.
