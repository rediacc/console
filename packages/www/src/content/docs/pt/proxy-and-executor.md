---
title: Proxy e Executor
description: Como os comandos do browser e de clientes leves são executados sem que o cliente alguma vez detenha chaves SSH ou endereços de máquinas
category: Concepts
tags:
  - security
  - networking
subcategory: architecture
order: 4
language: pt
sourceHash: "c7310ede42dd2da0"
sourceCommit: "cce23c4daecfe425f572f17d98ad6dd1f4bce5d7"
---

# Proxy e Executor

Normalmente, o `rdc` corre na sua máquina com a sua configuração e chaves SSH, e liga-se diretamente aos seus servidores. O modelo de proxy divide isto em duas partes: um cliente leve que não detém quaisquer segredos, e um **executor** que os detém e faz o trabalho. O botão Executar da [consola web](/pt/docs/web-console) e a flag `--proxy` da CLI são ambos clientes leves, e falam o mesmo protocolo.

## Intenção do comando, não comandos

Um cliente leve nunca detém uma chave SSH, um endereço de máquina ou uma configuração desencriptada. Quando quer executar algo, envia apenas a intenção do comando: um identificador para o comando (o seu caminho no contrato da CLI, por exemplo `repo up`) mais os parâmetros. O executor procura o comando nesse mesmo contrato, resolve-o para a função correspondente do lado do servidor, resolve a máquina de destino a partir da configuração desencriptada, e executa tudo através da sua própria ligação SSH. A saída é transmitida de volta ao cliente.

O executor é a própria CLI, iniciada como servidor com `rdc serve`. O mesmo binário que os operadores usam num portátil torna-se aquilo que executa comandos em seu nome. Tem duas colocações possíveis:

- **`--mode daemon`**: corre num host que controla, inscrito de forma headless como qualquer CLI (ver [Armazenamento de Configuração](/pt/docs/config-storage)), pelo que consegue derivar a chave de configuração por si próprio e não precisa de qualquer concessão por sessão. Este é o nível rigoroso: o SSH nunca sai da sua rede.
- **`--mode container`**: corre num container alojado para si, associado à sua organização. Começa sem qualquer chave e não pode fazer nada até um cliente lhe conceder uma para a sessão. Este é o nível de conveniência.

## A concessão da CEK

O armazenamento de configuração é zero-knowledge: o servidor armazena apenas blobs encriptados, e a chave de encriptação de conteúdo (CEK) só existe em claro num cliente que a tenha desbloqueado. Um executor em modo container tem, por isso, de *receber a chave por concessão*, e essa concessão não pode expô-la ao servidor entretanto.

O fluxo é o seguinte: um browser desbloqueado abre uma sessão com o executor, recebe a chave pública dessa sessão e sela a CEK para essa sessão usando X25519. O blob selado passa pelo servidor da conta, mas o servidor não o consegue abrir, pelo que a propriedade zero-knowledge se mantém de ponta a ponta. O executor desencripta a CEK apenas em RAM, com uma expiração por inatividade de 30 minutos; nada é alguma vez escrito em disco. Os pedidos de comando seguintes referem-se à sessão concedida através do cabeçalho `X-Config-Session`.

Um pormenor importante para efeitos de auditoria: a mesma identidade de utilizador atravessa as três etapas (abertura da sessão, concessão da chave, execução de comandos). O servidor da conta nunca reencaminha a sua própria credencial para o executor. Em cada etapa emite um token de curta duração atribuído ao utilizador real, e volta a verificar a pertença desse utilizador de cada vez. O executor verifica qualquer token que lhe seja apresentado antes de agir. Uma concessão feita por um utilizador não pode ser usada por outro.

A metade `state` de uma configuração (dados de runtime locais ao host) nunca viaja no blob de configuração, pelo que também nunca chega a um executor por esta via.

## O que pode correr através de um proxy

Nem todos os comandos fazem sentido remotamente. Cada comando no contrato tem uma flag `proxyCapable`, e o executor impõe-na do lado do servidor, independentemente de qualquer configuração de política:

- Os **comandos do plano de máquina, não interativos** (deploy, backup, status, logs, etc.) são compatíveis com proxy.
- Os **comandos do plano de configuração** não são: editam a configuração, o que neste percurso é tarefa do browser (a consola web encaminha-os antes para o seu próprio editor de configuração).
- Os **comandos interativos** (terminais, sessões VS Code) não são: não há um TTY neste canal.
- Os **comandos de transferência do lado do cliente** (`rdc repo sync`) não são: movem dados entre o sistema de ficheiros do *cliente* e uma máquina, e o executor não tem os ficheiros do cliente.

A consola web lê a mesma flag para decidir se um comando recebe ou não um botão Executar, mas o executor recusa comandos não compatíveis independentemente do que o cliente enviar.

## O executor fictício

Em desenvolvimento, quando não está configurado nenhum executor real, o servidor da conta responde ele próprio aos pedidos de comando com streams fictícios e dados claramente falsos (nomes de recursos com o prefixo `mock-`). Isto torna toda a consola utilizável, incluindo formulários, streaming e renderização de resultados, sem necessidade de uma máquina ou de um desbloqueio. A execução real requer um executor real.

## Restringir de onde o executor se liga

O bucket `access` da configuração guarda os intervalos de origem IPv4 e IPv6 permitidos para as chaves SSH. Os intervalos podem ser definidos para toda a configuração, por chave e por máquina, de modo que uma máquina só aceite uma chave a partir dos endereços de onde o respetivo executor se liga.

- `rdc config access add <key> --public-key ... --hosted-executor` regista uma chave e associa os dois intervalos do executor alojado: `104.28.0.0/16` e `2a09:bac0::/29`. Ambos são intervalos de saída da Cloudflare observados, e não uma lista publicada pela Cloudflare, pelo que podem mudar.
- `rdc machine access set <machine> --key <key>` atribui uma chave a uma máquina; `--ipv4`, `--ipv6` e `--clear-ranges` ajustam os intervalos dessa máquina.
- `rdc machine access push <machine>` escreve as linhas de acesso na máquina, e `--dry-run` mostra o resultado sem alterar nada.
- `rdc machine access show <machine>` mostra as linhas de acesso em vigor.

`machine setup` volta a aplicar as linhas de acesso, pelo que uma máquina reconstruída recupera as suas restrições.

Um push que bloquearia a sessão SSH atual, porque o respetivo endereço fica fora dos intervalos da chave em uso, é recusado com `ACCESS_LOCKOUT` e nada é escrito. Um push é recusado com `ACCESS_FILE_CHANGED` quando o ficheiro mudou na máquina entretanto; nada foi aplicado, por isso o push pode ser repetido em segurança.

## Jobs, tickets e consulta periódica

Cada comando do plano de máquina é executado na máquina como um job: uma unidade systemd gerida pelo renet, com o estado e o registo de eventos guardados num spool na máquina. Uma ligação interrompida nunca pára o trabalho, e qualquer cliente pode retomar o job pelo seu identificador.

- **A janela de ligação.** O executor transmite os eventos de um job durante um máximo de 20 segundos, com uma linha de heartbeat a cada 10 segundos enquanto o fluxo está em silêncio. Um job que termina dentro da janela devolve o resultado no mesmo pedido. Um job mais longo devolve um resultado com `state: running` e o identificador do job, depois de uma linha `job` que traz a máquina e os jobs sobrepostos.
- **A consulta periódica.** O cliente pede então a `GET /v1/jobs/<id>/poll` os eventos posteriores à última linha vista, juntamente com o estado do job, e espaça os pedidos enquanto as respostas vierem vazias. `POST /v1/jobs/<id>/cancel` cancela o job. Ambas as rotas aplicam a mesma política do comando que iniciou o job, e a consulta que vê primeiro um estado terminal escreve o evento de auditoria uma única vez.
- **Os tickets.** Cada invocação escreve também um ticket na pasta de configuração da CLI (`jobs/<config>.jsonl`). `rdc job wait <id>` espera por um job e termina com o seu código de saída; `rdc job list`, `status`, `logs`, `cancel` e `gc` gerem o resto. Ctrl-C durante um acompanhamento desliga-se sem cancelar e sai com 130. Um acompanhamento cuja ligação não pôde ser restabelecida sai com 16 e mantém o ticket.
- **Os passos.** O trabalho que se segue a um job, como registar um resultado na configuração ou mostrar uma listagem, é um passo anotado no ticket e no spool. Um passo corre uma vez, no sítio que primeiro vê o job terminar: o próprio comando, `rdc job wait`, o aviso impresso pelo comando seguinte ou a consulta do executor. A reivindicação faz-se na máquina, pelo que dois observadores nunca executam o mesmo passo.
- **As sobreposições.** Um arranque que se sobrepõe a um job ativo no mesmo repositório ou na mesma máquina imprime um aviso com o comando que se liga ao job ativo. Quando a política de sobreposição recusa o arranque, o comando sai com 15 (`BUSY`), e a recusa indica os jobs sobrepostos em `overlaps`.
- **As exceções.** Os comandos interativos, as transferências do lado do cliente e os próprios comandos `job` não correm como jobs.
- **A retenção.** A máquina guarda um job de leitura terminado durante uma hora e qualquer outro job terminado durante sete dias, com um máximo de 2000 jobs terminados.

## Relacionados

- [Consola Web](/pt/docs/web-console), o cliente de browser construído sobre este modelo
- [Armazenamento de Configuração](/pt/docs/config-storage), o armazenamento zero-knowledge que protege a CEK
