---
title: "Destinos de backup"
description: "Envie cada estratégia de backup para mais de um armazém, restaure a partir do armazém que tem o melhor snapshot e leia uma linha de estado por destino."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: pt
sourceHash: "10ded4035f1e9641"
sourceCommit: "7264926d04c36ba68ec76946fc14565405acd340"
---

# Destinos de backup

Uma estratégia de backup pode escrever em mais de um armazém. Cada destino é um ponto de recuperação independente: tem o seu próprio snapshot, o seu próprio commit e a sua própria linha de estado, pelo que um armazém que falha não estraga outro.

Todos os armazéns pertencem a uma conta. Uma config, uma licença e uma fatura cobrem-nos a todos. Uma máquina com sessão iniciada em duas contas continua a ser recusada, porque vários destinos significam vários armazéns dentro de uma conta.

## Armazéns

Um armazém é um bucket onde o servidor de contas escreve em nome da máquina. Toda a subscrição tem um desde o primeiro dia, chamado `home`: o armazém alojado que os comandos de backup sempre usaram. Um destino que não indica armazém escreve em `home`.

Podem registar-se mais dois tipos.

| Tipo | O que é | O que o registo exige |
|------|---------|-----------------------|
| `hosted-r2` | Uma segunda região alojada, escolhida entre as que a implementação oferece | Um id e a região. Sem credenciais |
| `customer-s3` | Um bucket gerido pelo cliente, em S3, RustFS ou qualquer serviço compatível com S3 | Um id, o endpoint HTTPS, o bucket, a região de assinatura (por omissão `us-east-1`), um endpoint público opcional e um par de chaves de acesso |

Uma máquina nunca guarda as chaves de um bucket de cliente. As chaves ficam seladas no servidor de contas, e a máquina recebe URLs pré-assinados de curta duração para o único armazém que a sua sessão indica.

### Registar um armazém

O registo é uma chamada à API da conta, não um comando `rdc`. `POST /backups/stores` regista um armazém, `GET /backups/stores` lista os registados e `DELETE /backups/stores/<id>` retira um. Registar, rodar e retirar exigem um token de API com o scope `backup:manage`, criado por um proprietário ou administrador atual da organização, e cada operação fica auditada. Listar exige `backup:read`.

O servidor verifica um armazém antes de o aceitar.

- **Sonda de conformidade.** O servidor executa as mesmas verificações que um armazém alojado supera. Um armazém que não impõe checksums é recusado no registo, em vez de ser descoberto no primeiro backup.
- **Sonda de eliminação.** A sonda também tenta eliminar. Quando o armazém recusa, é registado com a limpeza desativada (ver abaixo).
- **Regras de endpoint.** Apenas HTTPS, porta 443 e nenhum endpoint numa rede interna.
- **Limite de armazéns.** O número de armazéns por subscrição depende do plano, incluindo `home` e sem contar os armazéns retirados.

| Plano | Armazéns |
|-------|----------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

Registar um id que já existe apenas roda as suas credenciais, e a sonda corre de novo. Um armazém cujas credenciais deixam de funcionar fica marcado como suspenso pela primeira concessão recusada. `GET /backups/stores` mostra o endpoint, o bucket e os últimos caracteres do id da chave, nunca um segredo.

Um armazém não pode ser retirado enquanto um destino ativo ainda o indicar, e `home` não pode ser retirado.

## Indicar o armazém de um destino

Um destino indica o seu armazém com `--target`, usado em conjunto com `--destination`:

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| Opção | Descrição |
|-------|-----------|
| `--destination <name>` | O destino a criar ou alterar |
| `--target <storeId>` | Id do armazém registado onde o destino escreve (por omissão `home`). Exige `--destination` |

Dois destinos ativos da mesma estratégia não podem indicar o mesmo armazém, e um armazém que não está registado é recusado com a lista dos ids registados.

Cada execução agendada cria um snapshot por destino ativo, pela ordem em que os destinos foram declarados, cada um com o seu próprio limite de largura de banda. Cada snapshot é um reflink copy-on-write novo, pelo que cada um é um ponto no tempo consistente por si só. Um destino que falha não faz saltar o seguinte. A unidade continua a terminar com código diferente de zero quando algum destino falhou, para que o systemd e a verificação de execuções em falta vejam a falha.

## Restaurar a partir de um armazém

`rdc backup restore`, `rdc backup restore --path`, `rdc backup browse --at` e `rdc backup download --store` aceitam `--from <storeId>`:

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

Sem `--from`, a CLI pergunta ao servidor de contas quais os armazéns que guardam a linhagem do repositório, ordenados com o armazém cujo snapshot mais recente passou a última verificação em primeiro lugar, e tenta-os por essa ordem. Um armazém sem snapshots é ignorado. Se a classificação não puder ser lida, o restauro usa `home` e assinala-o.

Sem `--from`, `backup restore`, `restore --path`, `browse --at` e `download --store` começam pelo primeiro armazém dessa classificação e passam ao seguinte quando a falha é do armazém: um erro do servidor, uma concessão ou sessão recusada, ou um endpoint que não responde. Cada um indica que armazém o serviu. Nenhum recorre a outro armazém por uma falha do próprio snapshot. Um snapshot em falta, expirado ou corrompido tem o mesmo aspeto em todos os armazéns, pelo que o erro é mostrado. Um comando com `--from` lê apenas esse armazém e nunca recorre a outro.

Um id de snapshot indicado sem `--from` é procurado em todos os armazéns da linhagem.

## Estado por destino

`rdc backup status` imprime uma linha por destino junto à tabela de agendamento:

| Coluna | Significado |
|--------|-------------|
| Store | O id do armazém onde o destino escreve |
| Last run | Quando terminou a última execução para esse armazém |
| Result | O resultado dessa execução |
| Newest snapshot | O snapshot mais recente que o armazém guarda |
| Verify | O resultado da última verificação do armazém |
| Clean-up | `enabled`, ou desativada com o motivo |

Um armazém sobre o qual a conta não consegue reportar mostra `-` nas suas colunas. A verificação de execuções em falta é feita por armazém, pelo que um armazém que deixou de receber backups dispara o seu próprio alarme enquanto os outros ficam a verde.

## O que conta para a quota

Os armazéns alojados, `home` e qualquer segunda região, são medidos em bytes únicos guardados fisicamente, e os seus bytes contam para a mesma quota do plano. `rdc backup usage` mostra-os.

Os bytes de um bucket de cliente não são guardados pela Rediacc e não contam para a quota. Os metadados que a conta mantém para ele (linhas de manifesto, execuções de verificação e objetos de índice) são medidos como os de um armazém alojado.

## Armazéns com a limpeza desativada

Um armazém cuja eliminação é recusada mantém todos os objetos. A retenção e a recolha de lixo nunca eliminam nada nele. Quando um snapshot expira, a varredura marca-o como expirado na conta, deixa de o oferecer para restauro e deixa os seus objetos no bucket.

`rdc backup status` e o resumo de saúde dos backups indicam o armazém como limpeza desativada. O bucket continua a crescer até serem adicionadas credenciais de eliminação, registando de novo o mesmo id com chaves que possam eliminar.
