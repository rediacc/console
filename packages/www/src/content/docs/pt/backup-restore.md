---
title: "Backup e Restauro"
description: "Faça snapshot de repositórios encriptados para um armazenamento em chunks endereçado por conteúdo, onde só as células alteradas são enviadas e cada snapshot restaura diretamente. Ou mantenha uma cópia noutra máquina. Restaure em qualquer lugar, e automatize com estratégias nomeadas e temporizadores systemd."
category: "Guides"
order: 7
language: pt
sourceHash: "91f6072e230b059c"
sourceCommit: "79c84ad044d5730b6d0a20aaf7b21f21914b6bda"
---

# Backup e Restauro

O Rediacc faz backup de repositórios encriptados e restaura-os na mesma máquina ou numa diferente. Os backups são encriptados porque o repositório também o é: o que sai da máquina é o texto cifrado, e a sua credencial LUKS do repositório é necessária para restaurar.

Existem duas formas de fazer backup, e respondem a perguntas diferentes.

- **Snapshots para armazenamento em chunks** (`rdc backup snapshot`) mantêm um histórico pelo qual pode retroceder. Este é o caminho principal.
- **Uma cópia noutra máquina** (`rdc repo push`, `rdc repo pull`) mantém o repositório tal como está agora, em hardware que controla. Nenhuma conta na nuvem está envolvida.

São independentes. Um repositório com backup feito de uma forma não tem backup feito da outra.

## Como funcionam os snapshots

A imagem do repositório é cortada em células de tamanho fixo, sobre uma grelha fixa. Cada célula é ou um buraco, o que significa que nunca ali foi escrito nada, ou está guardada sob uma chave que **é** o SHA-256 do texto cifrado dessa célula.

É dessa única decisão que vêm todas as propriedades.

**Só as alterações reais custam alguma coisa.** O primeiro snapshot envia todas as células escritas. Cada execução seguinte pergunta ao sistema de ficheiros quais os extents que foram tocados, lê e faz hash apenas desses, e envia apenas as células que o armazenamento ainda não tem. Um repositório cujos dados mal se mexeram envia quase nada, e a execução demora minutos em vez de tanto tempo quanto a imagem for grande.

**Dados idênticos são guardados uma única vez.** Como a chave é o hash do conteúdo, dois snapshots que partilham uma célula partilham o objeto, e o mesmo acontece com um repositório e os seus [forks](/pt/docs/tutorial-forking): uma família de forks faz backup contra uma única linhagem em vez de duplicar o seu pai.

**Restaurar um snapshot antigo não é mais lento do que restaurar um recente.** Não há uma cadeia de incrementos a reproduzir. Restaurar resolve o snapshot numa lista completa de células e vai buscar essas células diretamente, pelo que o tempo de restauro acompanha o tamanho da imagem e a sua largura de banda, não há quanto tempo anda a fazer backups. Os buracos permanecem buracos, pelo que uma imagem esparsa restaura esparsa, e uma célula que aparece em vários lugares da imagem é descarregada uma única vez.

**Cada snapshot sustenta-se por si só.** Não há um "backup completo" que não pode perder, nem uma janela em que um incremento partido invalida os seguintes. Qualquer snapshot na lista é diretamente restaurável.

**A verificação é re-hashing, não confiança.** Uma vez que a chave é o hash do conteúdo, verificar um backup significa ir buscar células e fazer hash delas. `rdc backup verify` faz amostragem; `rdc backup verify --deep` refaz o hash de todas as células registadas.

**Uma execução interrompida não é desperdiçada.** O envio retoma sem reenviar células que já chegaram, e reiniciar um restauro parcial refaz o hash do que já está em disco e reutiliza-o em vez de o descarregar de novo.

### O que lhe custa

A quota é contada em **bytes físicos únicos armazenados**: o que está efetivamente retido após a deduplicação, não a soma do que os seus snapshots representam logicamente. Trinta snapshots de um repositório que muda lentamente custam próximo de um.
`rdc backup usage` mostra os bytes armazenados face à sua quota, que é um número por subscrição, começando em 10 GB num plano Community.

### O que os snapshots precisam

O envio de snapshots passa pelo servidor de conta, que autoriza cada execução contra a licença instalada do repositório e entrega à máquina uma autorização de curta duração para escrever. Portanto, este caminho precisa de um servidor de conta que a máquina consiga alcançar e de um repositório licenciado. Sem eles, o snapshot é recusado em vez de silenciosamente ignorado, e `rdc backup manifests`, `rdc backup usage` e `rdc backup retention` não têm nada para ler.

Isso inclui o `--dry-run`. A licença é lida antes de a execução decidir se está a planear ou a enviar, pelo que um dry run é uma pré-visualização do trabalho, não uma forma de experimentar o comando sem credenciais.

O envio e receção máquina a máquina não precisam de nenhum dos dois. São uma transferência direta entre duas máquinas já presentes na sua configuração.

### O que um snapshot não promete

- **Um snapshot cobre um repositório, não a sua máquina inteira de uma vez.** Cada repositório é capturado no seu próprio instante. Se dois repositórios dependerem um do outro, os seus snapshots não são um par coordenado.
- **Não é replicação contínua.** Um snapshot é um ponto que capturou, e pode perder tudo o que foi escrito desde o último. Quanto isso representa depende da frequência com que executa.
- **Os objetos armazenados são write-once, não WORM certificado.** As células são escritas com uma condição apenas de criação, a autorização que uma máquina recebe não pode apagar nada, e as eliminações acontecem do lado do servidor, sob política de retenção. Isso é uma barreira real contra uma máquina comprometida destruir os seus próprios backups. Não é uma certificação de conformidade, nem é auditado como tal.

### O caminho de armazenamento rclone desapareceu

`rdc repo push --to <storage>` e afins costumavam copiar um ficheiro de backup inteiro para um fornecedor na nuvem que registava você mesmo. Agora recusam um destino de armazenamento e indicam o substituto. A transferência máquina a máquina nunca passou por rclone e não é afetada. Se ainda precisar de ler um arquivo escrito dessa forma, veja [Ler um Arquivo Escrito Antes da Retirada](#ler-um-arquivo-escrito-antes-da-retirada).

### Comandos de armazenamento em chunks

```bash
# Enviar um snapshot. A primeira execução semeia, as seguintes enviam só as células alteradas.
rdc backup snapshot my-app

# Planear sem enviar: reporta o que seria movido.
rdc backup snapshot my-app --dry-run

# Parar os contentores, congelar, reiniciar, depois enviar.
rdc backup snapshot my-app --cold

# Desconfiar da âncora local e reenviar o inventário completo.
# Isto reenvia tudo e volta a debitar a quota; use apenas quando
# a âncora é conhecidamente má.
rdc backup snapshot my-app --reseed

# Verificar o inventário armazenado e a sua quota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

| Opção | Descrição |
|--------|-------------|
| `<repo-ref>` (posicional) | Repositório a fazer snapshot |
| `--dry-run` | Apenas planeamento: sem envio. Reporta o que seria movido |
| `--cold` | Parar os contentores, congelar, reiniciar, depois enviar. Não pode ser combinado com `--dry-run` |
| `--reseed` | Desconfiar da âncora local e enviar um inventário completo. Reenvia tudo e volta a debitar a quota |
| `--debug` | Ativar saída detalhada |

## Snapshots a Frio (`--cold`)

Um snapshot a frio para um repositório antes de o congelar, pelo que a imagem armazenada é consistente com a aplicação em vez de apenas consistente com uma falha. Corre na própria máquina:

```bash
# Todos os repositórios no datastore predefinido.
sudo renet backup snapshot --cold

# Apenas os repositórios que indicar. --repo recebe um GUID de repositório e repete-se.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` não pode ser combinado com `--dry-run`. Um dry run que para contentores não é dry, e um que não para não é cold, pelo que o renet recusa a combinação em vez de escolher um significado por si.

### O que uma execução a frio faz

Para cada repositório selecionado, por esta ordem:

1. Parar os seus contentores.
2. Sincronizar com o disco o ponto de montagem do repositório e o datastore.
3. Confirmar que os contentores realmente pararam.
4. Fazer um reflink copy-on-write da imagem do repositório.
5. Reiniciar os contentores.

Só depois é que o envio começa, com todos os repositórios já novamente ativos.

A interrupção é o congelamento, não a transferência. Um reflink é apenas metadados, pelo que demora o mesmo tempo quer o repositório tenha 1 GB ou 100 GB. Um envio não funciona assim: cresce com os bytes que mudaram, e um primeiro snapshot envia todo o inventário não vazio. Manter os contentores parados até o envio terminar prenderia a interrupção ao tamanho dos dados, o que, numa primeira semente, significa horas em vez de milissegundos.

Cada repositório selecionado é parado dentro de uma única janela, em vez de um de cada vez. Isso custa uma interrupção ligeiramente mais longa por repositório, e compra um único ponto de consistência para todo o conjunto.

Um repositório sem contentores em execução já está silencioso. É capturado sem qualquer interrupção, e isso é um resultado normal, não uma falha.

### O que a interrupção custa

Medido numa máquina real, a interrupção total foi de **222 ms**:

| Fase | Medido | O que acontece |
|-------|----------|--------------|
| `cold_down` | 64 ms | Os contentores param |
| `cold_sync` | 26 ms | Os pontos de montagem do repositório e o datastore são sincronizados com o disco |
| `cold_verify` | 31 ms | Confirma-se que os contentores pararam |
| `cold_stage` | 0 ms | Reflink da imagem do repositório |
| `cold_up` | 99 ms | Os contentores voltam a arrancar |

Reiniciar os contentores domina, e o staging é efetivamente grátis: o reflink não regista à resolução do milissegundo. Leia esse zero junto com os registos por repositório, e não isoladamente. Uma execução que recusou todos os repositórios também reporta `cold_stage=0ms`, e só os registos dizem qual dos dois casos está a ver.

A decomposição é a prova, não decoração. Nenhuma destas cinco fases lê ou envia dados do repositório, pelo que nenhuma delas cresce à medida que o backup cresce. A única parte que cresce, o envio, corre depois de a interrupção já ter terminado.

O renet imprime os mesmos valores quando a execução termina, para que possa medir as suas próprias máquinas em vez de confiar nas nossas:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

O registo JSON de cada repositório guarda a mesma interrupção e fases, pelo que um leitor posterior consegue distinguir um snapshot a frio de um a quente sem adivinhar pela cronologia.

### Quando escolher frio

Quente é a predefinição e a escolha certa para a maioria dos repositórios. Um snapshot quente é consistente com uma falha, o que é o estado em que um repositório ficaria depois de um corte de energia, e não custa qualquer tempo de inatividade. A maioria das bases de dados e filas recupera desse estado por si própria.

Escolha frio para dados que não podem ser capturados em segurança enquanto estão a ser escritos. Uma base de dados com o seu próprio write-ahead log e estado em memória é o caso óbvio. Está a trocar uma interrupção curta e medida por um snapshot que a aplicação consegue abrir sem ter de recuperar primeiro.

### O que uma execução a frio recusa

Recusar é a funcionalidade. Um backup rotulado como frio que nunca aquietou nada é uma mentira que só descobriria na altura de restaurar, pelo que o renet nunca despromove silenciosamente uma execução fria para quente:

- **Contentores que não pararam.** Depois da paragem, o renet pergunta ao socket Docker do próprio repositório se ainda há algo em execução. Se houver, esse repositório é recusado em vez de capturado. A verificação falha em segurança: se o socket não puder ser alcançado ou a lista de contentores não puder ser lida, o aquietamento conta como não verificado, e não verificado é recusado.
- **Uma licença que não pode ser lida.** As licenças são verificadas antes da interrupção, não depois, porque um repositório cuja licença não pode ser lida nunca poderia ter enviado nada. Esse repositório é ignorado sem ser parado. Se nenhum dos repositórios selecionados tiver uma licença legível, toda a execução é recusada antes de qualquer contentor ser derrubado.
- **Uma segunda execução a frio no mesmo datastore.** O bloqueio cobre o datastore, e um bloqueio ocupado é recusado de imediato, sem nada ter sido parado. Duas execuções sobrepostas iriam cada uma parar contentores que a outra acredita possuir, e a segunda reiniciaria repositórios que a primeira ainda estava a congelar. Saltar a execução e esperar pela próxima é melhor do que isso.

Se uma execução for interrompida enquanto os contentores estão parados, por um `systemctl stop` ou um reinício, o renet volta a arrancá-los antes de terminar. A recuperação na máquina é o último recurso: deteta um backup a frio cujo dono desapareceu e volta a levantar esses repositórios.

## Enviar um Backup para Outra Máquina

Copiar um repositório para uma segunda máquina via SSH:

```bash
rdc repo push my-app --to server-1
```

`--to <machine>` resolve o destino a partir da sua configuração, e `--to-machine <machine>` diz o mesmo explicitamente. Um nome de armazenamento é recusado: esse caminho está retirado.

A imagem encriptada é copiada com o **MESMO GUID**, pelo que isto é um backup ou uma migração, não um fork. Para obter uma cópia independente, faça primeiro `rdc repo fork` e envie o fork.

O primeiro envio transporta a imagem inteira. Cada envio seguinte envia apenas os blocos alterados contra uma imagem base imutável mantida em ambas as máquinas, sem flags a definir. `--delta-base <guid>` nomeia essa base você mesmo, se precisar.

A cópia enviada fica no destino como um artefacto de backup, e não como um repositório em execução. Transforme-a num com `rdc backup restore`:

```bash
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

Para um backup pontual, use o armazenamento em chunks: `rdc backup snapshot my-app`
envia apenas as células que mudaram, e `rdc backup restore my-app --at <snapshot>`
traz qualquer uma delas de volta.

| Opção | Descrição |
|--------|-------------|
| `<ref>` (posicional) | Referência do repositório a enviar |
| `--to <remote>` | Máquina ou cluster de destino |
| `--to-machine <machine>` | Máquina de destino, indicada explicitamente |
| `--provision <provider>` | Provisiona a máquina de destino através deste fornecedor na nuvem, se não existir |
| `--checkpoint` | Cria um checkpoint CRIU antes de enviar (para contentores com a etiqueta `rediacc.checkpoint=true`). O destino restaura automaticamente em `repo up` |
| `--force` | Substitui um backup existente |
| `--bwlimit <limit>` | Limite de largura de banda para a transferência rsync (ex.: `10M`, `500K`) |
| `--delta-base <guid>` | Transfere apenas os blocos alterados contra este GUID de base imutável. Omita para uma base automática, sem intervenção |
| `--strategy <strategy>` | Estratégia de delta de blocos ao usar uma base delta: `auto`, `physical`, ou `shared` |
| `--debug` | Ativar saída detalhada |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

## Receber um Backup de Outra Máquina

Trazer de volta um repositório da máquina que o guarda:

```bash
rdc repo pull my-app --from server-1
```

Adicione `--up` para montar e implementar no mesmo comando. Para restaurar a partir do armazenamento em chunks, use `rdc backup restore my-app --at <snapshot-id>`.

O pull recusa-se a substituir um repositório que esteja atualmente **montado**. Desmonte-o primeiro, faça o pull, e depois volte a levantá-lo com `rdc repo up`. Repositórios baseados em diretório são a exceção: sincronizam no lugar enquanto montados.

| Opção | Descrição |
|--------|-------------|
| `<ref>` (posicional) | Referência do repositório a receber |
| `--from <remote>` | Máquina ou cluster de origem |
| `--from-machine <machine>` | Máquina de origem, indicada explicitamente |
| `--force` | Substitui um backup local existente |
| `--up` | Monta e implementa o repositório após o pull |
| `--bwlimit <limit>` | Limite de largura de banda para a transferência rsync (ex.: `10M`, `500K`) |
| `--delta-base <guid>` | Recebe apenas os blocos alterados contra este GUID de base imutável |
| `--strategy <strategy>` | Estratégia de delta de blocos ao usar uma base delta: `auto`, `physical`, ou `shared` |
| `--debug` | Ativar saída detalhada |
| `--skip-router-restart` | Ignorar o reinício do servidor de rotas após a operação |

## Listar Backups

Listar os snapshots no armazenamento em chunks:

```bash
rdc backup manifests my-app
```

Cada linha é um ponto no tempo armazenado:

| Coluna | Significado |
|---|---|
| `Repo` | Nome do repositório resolvido a partir da sua configuração local (recorre ao GUID para repositórios que não estejam na configuração) |
| `Snapshot` | O id do snapshot. É o que `rdc backup restore --at` recebe |
| `Created` | Hora UTC em que o snapshot foi feito |
| `Total` | Tamanho da imagem do repositório que este snapshot representa |
| `Added` | Bytes que este snapshot efetivamente enviou para além dos anteriores |
| `Chunks` | Quantas células adicionou |

Para ver o que um `rdc repo push --to <machine>` deixou no destino, pergunte a essa máquina o que ela tem:

```bash
rdc repo list --machine server-1
```

A cópia enviada aparece com o seu próprio nome. Uma segunda linha com um GUID em bruto ao lado dela é a base delta retida, que é o que torna o próximo envio para essa máquina incremental em vez de uma transferência completa.

`rdc backup list --machine <machine>` lê as pastas `hot/` e `cold/` nas quais as execuções agendadas escrevem, pelo que é a ferramenta errada para uma cópia que um push ali colocou, e não lhe mostrará nada.

| Coluna | Significado |
|---|---|
| `Mode` | `hot` ou `cold`. Em que pasta de backup agendado esta entrada vive |
| `Name` | Nome do repositório resolvido a partir da sua configuração local (recorre ao GUID para repositórios que não estejam na configuração) |
| `GUID` | O GUID do repositório em disco |
| `Size` | Tamanho legível por humanos do ficheiro de backup |
| `Modified` | Timestamp UTC do ficheiro na máquina |

Listar um back-end de armazenamento está retirado juntamente com o ramo rclone; o comando recusa e indica estes dois substitutos.

## Retenção

O servidor impõe uma política de retenção por repositório sobre o armazenamento em chunks, pelo que snapshots antigos são podados sem que apague nada à mão. Sem nenhuma política declarada, todos os snapshots são mantidos.

```bash
# O que está a ser imposto neste momento.
rdc backup retention my-app

# Manter uma janela deslizante: 7 diários, 4 semanais, 6 mensais.
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Voltar a manter tudo.
rdc backup retention clear my-app
```

| Opção | Descrição |
|--------|-------------|
| `--keep-last <n>` | Manter este número dos snapshots mais recentes |
| `--keep-hourly <n>` | Manter o snapshot mais recente de cada uma destas horas |
| `--keep-daily <n>` | Manter o snapshot mais recente de cada um destes dias |
| `--keep-weekly <n>` | Manter o snapshot mais recente de cada uma destas semanas |
| `--keep-monthly <n>` | Manter o snapshot mais recente de cada um destes meses |
| `--keep-yearly <n>` | Manter o snapshot mais recente de cada um destes anos |

Indique pelo menos uma regra. `set` sem regras é recusado em vez de ser tratado como "não manter nada", porque limpar uma política é para isso que serve o `clear`.

## Restaurar

`rdc backup restore` transforma um backup num repositório vivo, e é o mesmo verbo para ambos os caminhos. O que muda é o que aponta para ele.

```bash
# Um ponto no tempo a partir do armazenamento em chunks.
rdc backup restore my-app --as my-app-yesterday --at <snapshot-id> --up

# Um artefacto que um push deixou numa máquina.
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

`--at` recebe um id de snapshot de `rdc backup manifests`, ou uma hora RFC 3339 como `2026-08-14T12:00:00Z`, que se resolve para o snapshot mais recente feito nesse momento ou antes dele. Uma hora sem nenhum snapshot nesse momento ou antes é recusada em vez de arredondada para a frente.

Restaurar sob um novo nome com `--as` não substitui nada, pelo que um exercício de restauro é seguro de executar contra uma máquina em produção. Restaurar sobre um nome que já existe é recusado.

| Opção | Descrição |
|--------|-------------|
| `<artifact-ref>` (posicional) | O que restaurar. `repo` para um snapshot do armazenamento em chunks, `repo@place` para um artefacto numa máquina |
| `--as <name>` | Nome para o repositório restaurado (por defeito, o nome do artefacto) |
| `-m, --machine <machine>` | Máquina para onde restaurar |
| `--datastore <name>` | Restaura para este datastore nomeado, cuja máquina associada o aloja |
| `--at <time>` | Restaura um ponto no tempo: um id de snapshot ou uma hora RFC 3339 |
| `--up` | Implementa o repositório restaurado após a transferência |
| `--health-window <seconds>` | Quanto tempo observar o repositório implementado quanto à sua saúde |
| `--health-timeout <seconds>` | Quanto tempo esperar até ficar saudável |
| `-y, --yes` | Salta a confirmação |
| `--debug` | Ativar saída detalhada |

Restaurar um repositório precisa da sua credencial LUKS, que vive na sua configuração. Se tiver o config storage ativado, essa credencial volta com a sua configuração numa máquina nova. Se não tiver, guarde uma cópia da configuração nalgum lugar que a falha da máquina não leve consigo.

### Prove o restauro em cada máquina

Uma máquina que nunca fez a ida e volta completa não tem backup, por muito saudáveis que os seus envios pareçam. Envios e restauros falham por razões diferentes, e o segundo tipo só aparece quando o experimenta.

Faça isto uma vez por máquina, antes de confiar nos backups:

1. Faça um snapshot: `rdc backup snapshot my-app`.
2. Confirme que ficou registado: `rdc backup manifests my-app`.
3. Restaure-o sob um nome descartável: `rdc backup restore my-app --as my-app-drill --at <snapshot-id>`.
4. Compare o repositório restaurado com a origem, depois apague a cópia de exercício com `rdc repo delete my-app-drill --yes`.

Nada nesta sequência toca no repositório em produção, pelo que é seguro fazê-la numa máquina que está a servir tráfego. Se está a migrar de um esquema de backup mais antigo, mantenha-o em funcionamento até isto ter passado nessa máquina pelo menos uma vez. Dois caminhos de backup custam armazenamento; um caminho não comprovado custa os dados.

## Sincronizar Um Repositório de Cada Vez

O push e o pull atuam sobre um único repositório, referenciado por ref (`name`, `name:tag`, ou `name@machine`). Não existe uma forma de "todos os repositórios de uma vez": execute o comando uma vez por repositório.

Uma ref que nomeia um fork e uma máquina funciona da mesma forma que um nome simples:

```bash
rdc repo push shop:nightly@server-1 --to server-2
rdc repo pull shop:nightly@server-1 --from server-2
```

As listas completas de opções estão em [Enviar um Backup para Outra
Máquina](#enviar-um-backup-para-outra-máquina) e [Receber um Backup de Outra
Máquina](#receber-um-backup-de-outra-máquina).

## Backups Agendados

O Rediacc usa estratégias de backup nomeadas. Cada estratégia define um horário, modo de backup, limite de largura de banda opcional, e filtros de ficheiros. Vincula nomes de estratégias a máquinas para controlar quais backups correm onde.

### Modos de Backup

| Modo | Comportamento | Interrupção |
|------|----------|--------------|
| `hot` | Imagem do repositório congelada enquanto os serviços continuam a correr (consistente com uma falha) | Nenhuma |
| `cold` | Serviços parados, snapshot feito, serviços reiniciados, snapshot enviado (consistente com a aplicação) | Janela de paragem+arranque por repositório, paralelizada entre repositórios. Veja "Estimar a Interrupção de Backups a Frio" abaixo. |

Use `hot` para serviços que toleram snapshots consistentes com uma falha. Use `cold` quando precisar de consistência garantida e puder aceitar um breve reinício.

### Semântica do Backup a Frio

Um backup a frio corre em três fases por repositório incluído: **parar → snapshot → arrancar**. Saiba onde terminam as garantias e apanhará falhas parciais cedo.

**O que o backup a frio garante:**

- Antes do snapshot, todo contentor em execução em cada repositório incluído é parado de forma graciosa através do hook `down()` do seu Rediaccfile, e o daemon Docker por repositório é aquietado. O snapshot é, portanto, consistente com a aplicação, não apenas consistente com uma falha.
- O conjunto de IDs de contentores que estavam em execução antes do snapshot é persistido num sidecar em `/var/run/rediacc/cold-backup-<guid>.running.json`. Esta é a fonte de verdade sobre "o que deve estar de novo em execução quando terminarmos."
- Depois do snapshot, o hook `up()` do Rediaccfile do repositório é invocado para restaurar toda a stack compose.
- Um sidecar de estado por execução em `/var/run/rediacc/cold-backup-<guid>.status.json` regista a fase, o resultado, e qualquer erro de cada tentativa.

**O que o backup a frio NÃO garante:**

- O `up()` é feito com o melhor esforço. Pode falhar por razões fora do controlo do backup a frio (uma condição `depends_on: service_healthy` ainda em espera, um erro de sintaxe no ficheiro compose, uma falha de rede transitória ao obter uma imagem). Quando falha, o backup a frio regista o erro a nível de erro, escreve o sidecar de estado, e passa ao próximo repositório.
- Quando o `up()` falha, entra em ação um **reinício direto de recurso**: o sidecar em execução é lido e cada ID de contentor registado é reiniciado via API direta do Docker (sem compose). Isto volta a pôr os serviços de pé mesmo que o fluxo compose tenha um problema, embora sem voltar a correr nenhum hook do Rediaccfile.
- Se mesmo o recurso falhar para alguns IDs de contentor (por exemplo, o próprio daemon Docker está em baixo), o sidecar é **deixado no lugar** para que o watchdog do router possa continuar a tentar em cada tick.

**Recuperação pelo watchdog:** em cada tick, o watchdog verifica se existe um sidecar em execução. Qualquer ID de contentor ali listado que esteja atualmente parado é reiniciado, *independentemente da `restart_policy` guardada do contentor*. Isto significa que serviços com `restart: on-failure` (que o Docker NÃO reiniciaria depois de uma paragem limpa) voltam mesmo assim depois de um backup a frio. Assim que todo contentor listado está em execução, o sidecar é apagado.

**Como deteta falhas:**

- `rdc machine status <machine> --containers` mostra o estado em execução. Compare com o conjunto esperado.
- `/var/run/rediacc/cold-backup-<guid>.status.json` na máquina. Inspecione via `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` com um `startedAt` desatualizado significa que o último backup não terminou de forma limpa.
- Os logs da execução de backup do renet (`journalctl -u renet-*` ou a invocação direta de `rdc backup schedule`) emitem uma linha de resumo final da forma `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Um `failed_repos` não vazio é o alvo para grep.

### Estimar a Interrupção de Backups a Frio

Cada repositório fica em baixo apenas durante a sua própria janela `down()` + `up()`. Numa máquina aquecida, tipicamente:

| Forma do repositório | Paragem+arranque típico |
|------------|--------------------|
| Pequeno (1-2 contentores, sem BD) | 5-15 s |
| Médio (app web + cache) | 20-45 s |
| Pesado (BD + filas + email) | 60-120 s |

O passo de congelamento é um reflink copy-on-write da imagem do repositório. É apenas metadados, pelo que demora o mesmo tempo quer o repositório tenha 1 GB ou 100 GB, e numa execução medida não registou à resolução do milissegundo. Um repositório não fica parado por causa do congelamento de outros repositórios. O envio corre então contra a cópia congelada, enquanto todo repositório já está de volta ao ar.

**O tempo total de relógio de parede para toda a execução** é governado por quantos repositórios reiniciam em simultâneo. O renet deriva isto a partir da máquina anfitriã:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Exemplos:

| Anfitrião | Repositórios | Concorrência | Reinício em relógio de parede |
|------|-------|-------------|--------------------|
| VM de 4 CPU | 5 repositórios, média de 30 s cada | 2 | ~75 s |
| Servidor de 16 CPU | 10 repositórios, média de 40 s cada | 8 | ~80 s |
| Nó de frota de 64 CPU | 50 repositórios, média de 40 s cada | 8 | ~4 min |

**Substituir via variável de ambiente:** defina `REDIACC_COLD_BACKUP_CONCURRENCY=N` no ambiente do serviço de backup (um drop-in do systemd é a via habitual) para fixar um valor específico. `=1` força reinícios estritamente sequenciais, útil ao depurar um crashloop no hook `up()` de um repositório.

Se correr um repositório sensível à latência (app web pública, email), a sua interrupção é limitada pela sua própria paragem+arranque (tipicamente 30-90 s), não pela duração de toda a execução. Os repositórios são agendados em slots de concorrência pela ordem em que foram descobertos; não há fila de prioridade. Dê aos repositórios pesados a sua própria estratégia com âmbito em `--include` se precisar de agendamento mais fino.

### Backups de Longa Duração e Horários Sobrepostos

Um backup a frio que demore mais do que o seu próprio intervalo de agendamento (por exemplo, uma primeira semente de um repositório de 500 GB numa ligação modesta pode legitimamente precisar de mais de 24 h, período durante o qual o temporizador noturno dispara de novo) não coloca em fila nem lança uma segunda execução. A unidade `Type=oneshot` do systemd é uma instância única: quando o temporizador dispara e o serviço já está `activating`, o systemd funde o arranque no trabalho existente. Nenhum processo novo arranca, nenhuma execução fica em fila para depois.

Concretamente, uma execução que começa segunda-feira às 03:00 UTC e termina quinta-feira ao meio-dia:

| Dia | Disparo às 03:00 UTC | Resultado |
|------|---------------|--------|
| Segunda | Primeiro disparo | Execução começa |
| Terça | Segundo disparo | Descartado silenciosamente (execução anterior ainda ativa) |
| Quarta | Terceiro disparo | Descartado silenciosamente (execução anterior ainda ativa) |
| Quinta | Execução termina ao meio-dia | Sem recuperação; a próxima execução é sexta às 03:00 UTC |

A diretiva `Persistent=true` do temporizador **não** resgata estes disparos. `Persistent=true` reproduz disparos que foram perdidos porque o próprio temporizador estava inativo (sistema desligado, temporizador desativado). Disparos descartados porque o serviço estava ocupado desaparecem.

Esta predefinição é deliberada. Correr dois backups a frio em paralelo contra o mesmo datastore entraria em conflito no caminho de congelamento, no envio, e nos sidecars por repositório em `/var/run/rediacc/cold-backup-<guid>.status.json`. Esperar atrás de uma instância em execução é melhor do que atacar os mesmos dados a partir de duas direções. O bloqueio do datastore impõe isto: uma segunda execução a frio encontra o bloqueio ocupado e é recusada de imediato, sem nada ter sido parado.

**Implicação para a monitorização.** Um backup pendurado (por exemplo, um envio encravado num buraco negro de rede) descarta silenciosamente todos os disparos seguintes do temporizador. O agendador não emite qualquer alarme. Observe `systemctl show <unit> -p ActiveEnterTimestamp`: se o serviço estiver `activating` há mais tempo do que a duração esperada da sua execução (por exemplo, mais de 48 h num temporizador noturno), investigue.

**Se precisar que todo disparo agendado corra**, mude o temporizador de `OnCalendar=<cron>` para `OnUnitInactiveSec=<intervalo>`. Isso dispara N horas depois de a execução anterior terminar, em vez de num horário fixo de relógio de parede, pelo que execuções longas não causam quebras. Apenas empurram a próxima execução mais tarde. O compromisso é a deriva do horário: o seu noturno das 03:00 passa a ser "24 h depois de o último ter terminado."

### Snapshots, Interrupções, e Espaço na Pool

Cada push trabalha a partir de um snapshot momentâneo do datastore, pelo que os dados enviados são consistentes mesmo enquanto os repositórios continuam a escrever. Enquanto o backup corre, esse snapshot continua a referenciar todo bloco que partilha com repositórios em produção: eliminações e [trims](/pt/docs/repositories#recuperar-espaço-trim) libertam menos espaço na pool até o ciclo terminar e o snapshot ser apagado. O [relatório de saúde do armazenamento](/pt/docs/monitoring#saúde-do-armazenamento) mostra quanto espaço os snapshots de backup estão atualmente a reter.

Interrupções são seguras. Parar o serviço (ou reiniciar a máquina) faz o backup abortar a sua transferência e apagar o seu snapshot antes de terminar; a próxima execução agendada retoma de onde ficou, porque as células já armazenadas não são reenviadas. Se o processo for morto de forma demasiado brusca para limpar (perda de energia), o snapshot órfão é detetado e removido automaticamente pelo mantenedor de armazenamento em minutos.

### Definir uma Estratégia

A configuração predefinida é uma divisão em duas estratégias: um fluxo quente rápido e horário que captura todo repositório, e um fluxo frio semanal mais lento que aquieta os contentores para snapshots consistentes com a aplicação. Ambos escrevem no mesmo armazenamento em chunks, e blocos partilhados são armazenados uma vez, não por fluxo.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

`--destination <name>` nomeia o destino dentro da estratégia; é uma etiqueta que escolhe, e descreve o armazenamento em chunks. `--include` lista os repositórios a fazer backup, e repeti-lo acrescenta mais. Omita-o e a estratégia cobre todo repositório no datastore. Os nomes correspondem ao nome do repositório na configuração local (sem `:tag`).

`--exclude` é recusado para um destino em chunks em vez de ser silenciosamente ignorado, porque o `backup snapshot` subjacente seleciona repositórios nomeando-os e não tem exclusão própria. Respeitá-lo significaria fazer backup de repositórios que pediu para deixar de fora. Defina o âmbito de uma estratégia com `--include` em vez disso, para que o que uma execução agendada cobre fique escrito em vez de inferido.

| Opção | Descrição |
|--------|-------------|
| `<strategy>` (posicional) | Nome da estratégia (usado para vincular a máquinas) |
| `--destination <name>` | Nome do destino dentro da estratégia. Por defeito, o armazenamento em chunks |
| `--storage <name>` | Adere ao tipo de destino rclone retirado. Um agendamento que o use não pode ser implementado |
| `--cron <expression>` | Expressão cron (ex.: `"0 2 * * *"` para diariamente às 2h) |
| `--mode <hot\|cold>` | Modo de backup |
| `--bwlimit <limit>` | Limite de largura de banda para envios (ex.: `10M`) |
| `--include <repos>` | Repositórios que esta estratégia cobre (repetível) |
| `--exclude <repos>` | Repositórios a saltar (repetível). Recusado num destino em chunks |
| `--folder <path>` | Subpasta dentro de um bucket rclone. Recusado num destino em chunks |
| `--enable` / `--disable` | Ativa ou desativa a estratégia |

### Ver Estratégias

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Remover uma Estratégia

```bash
rdc backup strategy remove weekly-cold
```

### Vincular Estratégias a uma Máquina

Uma estratégia sem vínculo a nenhuma máquina nunca é implementada. Vincule uma ou mais a uma máquina:

```bash
rdc backup strategy bind hourly-hot --machine hostinger
rdc backup strategy bind weekly-cold --machine hostinger
rdc backup strategy unbind weekly-cold --machine hostinger
```

O vínculo é registado na sua configuração como uma lista na máquina, que é o que `rdc backup schedule` lê para decidir quais unidades implementar:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **O vínculo é apenas na configuração local.** Definir uma estratégia e vinculá-la a uma máquina não toca na máquina. Execute `rdc backup schedule -m <machine>` (veja [Implementar Agendamento numa Máquina](#implementar-agendamento-numa-máquina)) para implementar os temporizadores systemd, e volte a executá-lo depois de qualquer alteração de estratégia ou vínculo.

## Escolher Entre Quente e Frio, e Filtragem por Repositório

### Quente vs frio de relance

| | Quente | Frio |
|---|-----|------|
| **Consistência** | Consistente com falha (imagem congelada em execução) | Consistente com a aplicação (parar → congelar → arrancar) |
| **Interrupção** | Nenhuma | Janela de paragem+arranque por repositório (tipicamente 5-120 s) |
| **Frequência adequada** | Alta (ex.: horária) | Baixa (ex.: diária ou semanal) |
| **Uso típico** | Rede de segurança frequente | Backup agendado com consistência garantida |

**Quente** é a predefinição certa para execuções de alta frequência. Os serviços continuam a correr enquanto o snapshot é feito, pelo que não há interrupção para as suas apps. O snapshot é consistente com falha: equivalente ao que obteria depois de um desligamento abrupto. Para a maioria das bases de dados modernas e filas de mensagens, isso está bem.

**Frio** é adequado quando precisa de um snapshot garantidamente consistente com a aplicação e pode aceitar um breve reinício por repositório. Os serviços são parados antes do snapshot e reiniciados antes de o envio começar, pelo que um envio lento ou falhado nunca prolonga a janela de interrupção. Veja [Semântica do Backup a Frio](#semântica-do-backup-a-frio) para o modelo completo de garantias.

Ambos os modos escrevem no mesmo armazenamento em chunks, e o modo diz respeito a como o repositório é tratado enquanto a imagem está congelada, não a onde os dados ficam. Um repositório coberto tanto por um agendamento quente horário como por um frio semanal armazena os blocos que partilham uma vez, não duas.

### Definir o Âmbito de Repositórios por Estratégia

Uma estratégia sem `--include` cobre todo repositório no datastore. Repetir `--include` estreita-a aos repositórios que nomear, correspondidos com o nome do repositório na configuração local (sem `:tag`).

```bash
# Estratégia quente: fazer backup de tudo a cada hora
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Estratégia fria: semanal, e apenas os repositórios que precisam de ser aquietados
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

### Quando Manter um Repositório Fora da Estratégia Quente Frequente

Nomeie os repositórios que quer na execução de alta frequência, em vez de a deixar levar tudo, quando:

- Um repositório é grande e **totalmente regenerável** a partir de dados de origem já presentes no volume, pelo que todo backup horário gasta largura de banda sem acrescentar valor de recuperação.
- A execução de backup ultrapassaria o seu próprio intervalo de agendamento à velocidade de envio disponível.

**Exemplo.** Um repositório `analytics-demo` guarda aproximadamente 114 GB de tabelas Postgres derivadas que podem ser reconstruídas a partir de dumps CSV em bruto guardados dentro do mesmo volume. Com um limite de envio de 6 MB/s, um primeiro snapshot desse repositório demora mais de 5 horas. Correr isso a cada hora significa que cada execução ainda está em curso quando a seguinte dispara, pelo que todo disparo subsequente é descartado silenciosamente (veja [Backups de Longa Duração e Horários Sobrepostos](#backups-de-longa-duração-e-horários-sobrepostos)). Listar os outros repositórios em `hourly-hot` e deixar `analytics-demo` para `weekly-cold` significa que tem backup uma vez por semana em vez de nunca.

> **Se os dados forem puramente regeneráveis**, considere se sequer precisa de fazer backup deles. Uma alternativa é fazer backup apenas dos inputs de origem em bruto (os dumps CSV, neste exemplo) e saltar completamente a cópia derivada. Um backup a frio semanal dos inputs de origem é muito mais pequeno e totalmente suficiente para recuperação.

Um repositório que ambas as estratégias cobrem obtém snapshots horários consistentes com falha e um semanal consistente com a aplicação. `rdc backup manifests <repo>` mostra-os juntos, e os blocos que partilham são armazenados uma vez.

## Operações de Backup

### Implementar Agendamento numa Máquina

Envia as estratégias vinculadas para uma máquina como temporizadores systemd:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

A implementação é um reconciliador de estado. Lê os ficheiros de unidade atuais e o estado do systemd na máquina, compara com o que a configuração produziria (SHA-256 por ficheiro), e só toca nas unidades cujo conteúdo realmente mudou. Voltar a executar sem alterações de configuração é um no-op: sem escritas, sem `daemon-reload`, sem agitação de temporizadores.

`--dry-run` imprime o plano para cada estratégia (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) sem tocar na máquina. Combine com `--debug` para também imprimir os corpos das unidades geradas, com credenciais ocultadas. Uma unidade de armazenamento em chunks não carrega nenhuma à partida: a máquina autentica-se com a sua própria licença de repositório assinada e o servidor devolve uma autorização de curta duração, pelo que nada sensível é escrito no ficheiro de unidade.

Se um backup estiver atualmente em execução para uma estratégia que está prestes a atualizar ou remover, a implementação falha rapidamente com uma sugestão para o cancelar ou passar `--force`. Com `--force`, a invocação em execução mantém a sua unidade em memória e a nova configuração aplica-se no próximo tick do temporizador, pelo que o backup em execução nunca é morto.

`--reset-failed` é opt-in. Quando passado, limpa o estado failed do systemd nos serviços tocados após uma implementação bem-sucedida. Desligado por defeito, para que sinais de falha anteriores continuem visíveis para alertas.

### Executar um Backup Agora

Dispara um backup imediatamente sem esperar pelo temporizador. Funciona mesmo que nenhum temporizador tenha sido implementado, usando `systemd-run` para execução ad-hoc:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Ver Estado do Backup

Mostra o estado atual dos temporizadores de backup e os resultados dos trabalhos recentes:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Cancelar um Backup em Execução

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Migração de Repositório

Mover um repositório de uma máquina para outra:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Opção | Descrição |
|--------|-------------|
| `<ref>` (posicional) | Referência do repositório a migrar; o seu `@machine` nomeia a origem |
| `--to <place>` | Máquina ou cluster de destino |
| `--provision <provider>` | Auto-provisiona a máquina de destino através deste fornecedor na nuvem (ex.: `hetzner`, `linode`) |
| `--checkpoint` | Cria um checkpoint CRIU antes de migrar, para que a memória do processo também se mova |
| `--delta-base <guid>` | GUID de base imutável para o delta de cutover. Por defeito, a base da primeira fase |
| `--strategy <strategy>` | Estratégia de delta de blocos para o cutover: `auto`, `physical`, ou `shared` |
| `--skip-dns` | Ignora a atualização de registos DNS após a migração |
| `--keep-source` | Mantém as imagens de origem após uma mudança bem-sucedida |
| `--bwlimit <limit>` | Limite de largura de banda para a transferência (ex.: `50M`) |

A migração transfere os dados encriptados do repositório via rsync em duas fases: uma transferência em massa enquanto o repositório continua em execução, depois uma breve paragem para o delta. A migração **move** o repositório, pelo que as imagens de origem são apagadas assim que a mudança tem sucesso. Passe `--keep-source` para as reter. Esta é a diferença entre `repo migrate` e `repo push`: o push deixa a origem em execução e intacta.

## Ler um Arquivo Escrito Antes da Retirada

`rdc storage` é o que resta do ramo rclone, e é apenas de leitura. Já não pode ser um destino de backup, mas ainda consegue aceder a um arquivo escrito para um.

```bash
# Registar um remote que já tenha configurado para rclone.
rdc storage import rclone.conf
rdc storage list

# Ver o que lá está. Isto corre o rclone no seu PATH.
rdc storage browse my-storage
```

`import` lê um ficheiro de configuração rclone e regista os remotes na sua configuração; os tipos suportados são S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob e Swift.

**`browse` exige `rclone` no seu PATH.** Corre o rclone instalado na máquina onde está a escrever; já não há uma cópia embutida. Sem um, avisa-o disso mesmo e não faz mais nada.

Enviar para, receber de, listar e restaurar um back-end de armazenamento estão retirados; cada um recusa e indica o comando que o substitui.

## Boas Práticas

- Agende snapshots frios diários para cópias consistentes com a aplicação de dados críticos
- Use snapshots quentes para execuções de alta frequência onde é exigida inatividade zero
- Teste restauros periodicamente. `rdc backup restore --as <new-name>` não substitui nada, pelo que um exercício é seguro numa máquina em produção
- Defina uma política de retenção em vez de podar à mão, para que a janela que mantém fique escrita
- Mantenha uma cópia máquina a máquina além dos snapshots se quiser uma cópia em hardware que controla
- Mantenha as credenciais seguras; os backups são encriptados mas a credencial LUKS é necessária para restaurar
