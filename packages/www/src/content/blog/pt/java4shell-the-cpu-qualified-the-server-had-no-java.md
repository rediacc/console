---
title: "Java4Shell: o nosso CPU qualificava, o nosso servidor não tinha Java e os nossos templates ensinaram-nos sobre pinning"
description: "O CVE-2026-114938 exige um CPU com AVX-512 VBMI e um JDK afetado. O nosso servidor tinha o CPU, mas zero JVMs. O trabalho a sério estava nos templates de aplicações que distribuímos, onde uma tag fixada congelou um JDK de 2023."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - java
  - docker
  - case-study
featured: true
language: pt
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **Resumo.** O Java4Shell (CVE-2026-114938) é uma escrita fora dos limites no heap, no descodificador de Base64 compilado por JIT do OpenJDK. Só dispara em CPUs x86-64 com AVX-512 VBMI.
>
> - O CPU do nosso servidor de produção **tem as quatro flags exigidas**. Só pelo CPU, parecia exposto.
> - Uma sonda a **43 contentores**, ao host e aos repositórios parados encontrou **zero runtimes Java**. Uma execução de controlo da mesma sonda, à procura de `python3`, encontrou-o em todo o lado onde devia. Nada para corrigir no servidor.
> - Os templates de aplicações que distribuímos eram outra história. **Quatro** deles arrancam uma JVM. **Três** usam tags flutuantes e já tinham sido reconstruídos a montante com JDKs corrigidos a 20 de novembro.
> - **Um**, o Elasticsearch, estava fixado em `8.11.0`: uma imagem de novembro de 2023 com o JDK `21.0.1` incluído. A Elastic ainda não tem versão corrigida, por isso o template passa a arrancar o Elasticsearch com a flag de mitigação da própria Elastic, verificada num nó em execução.

## O que foi divulgado

A 17 de novembro, investigadores da Calif publicaram o **Java4Shell**, e a Oracle e o OpenJDK lançaram correções no mesmo dia. A falha está no descodificador de Base64 do HotSpot acelerado por hardware: o caminho AVX-512 VBMI trata mal os últimos caracteres e pode escrever para lá do fim de um buffer no heap. Um atacante remoto sem conta consegue transformar isso em corrupção de memória e, na aplicação certa, em execução de código. O artigo mostra cadeias pré-autenticação para vários produtos de servidor Java conhecidos.

Os detalhes que importam para a triagem:

- **Afetados:** OpenJDK 17.0.6 e posteriores, 21, 25 e 27, anteriores às builds corrigidas. O Java 8 e o Java 11 standard não são afetados.
- **Corrigidas:** 17.0.21.1, 21.0.13.1, 25.0.5.1 e 27.0.1.1 (as builds Temurin levam `+2`, ou `+4` no 27). Um runtime que reporte `17.0.21` sem o `.1` continua vulnerável.
- **Pré-condições:** um CPU x86-64 com AVX-512 VBMI, um JIT que já tenha compilado o descodificador e um caminho da aplicação que descodifique Base64 a partir de input não confiável. ARM não é afetado.
- **Pontuação:** 9,2 no CVSS 4.0, 8,1 no CVSS 3.1. Existe uma prova de conceito autónoma pública. Não havia exploração ativa reportada à data da escrita.
- **Mitigação:** arrancar a JVM com `-XX:-UseBASE64Intrinsics`. A outra opção publicada, `-XX:UseAVX=2`, também funciona em x86-64, mas faz uma JVM ARM recusar-se a arrancar.

A nossa [ronda de correções anterior](/pt/blog/patching-nginx2root-and-php-fork-first) terminou com um rollout de quatro aplicações começando por um fork. Esta terminou muito mais cedo, e o interessante é perceber porquê.

## Passo 1: o CPU qualifica?

A maioria dos CVEs tem uma pré-condição de software. Este tem também uma pré-condição de hardware, e é barata de verificar:

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

As quatro. A máquina corre um AMD EPYC 9354P, um CPU de servidor recente com suporte completo a AVX-512. Se a triagem tivesse parado aqui, a resposta seria "exposto, corrigir tudo o que for Java esta noite".

![As três pré-condições: o CPU qualifica, a verificação do JDK falha, por isso o caminho de input nunca é alcançado](/img/blog-java4shell-preconditions.svg)

## Passo 2: há algum Java para corrigir?

O CPU é apenas um elo da cadeia. O segundo elo é um JDK afetado, por isso a pergunta seguinte era simples: que contentores correm Java, afinal?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

Executámo-lo através de `rdc term connect <repo>@hostinger` para cada repositório da máquina. O `find` por `libjvm.so` apanha JVMs incluídas dentro da pasta de uma aplicação e fora do `PATH`, que é como o Elasticsearch, por exemplo, distribui o seu JDK.

O resultado foi vazio. Nenhum `java`, nenhum `libjvm.so`, em nenhum dos 43 contentores em execução.

Um resultado vazio de uma sonda não prova nada até a sonda ter mostrado que consegue encontrar alguma coisa. Por isso o mesmo loop correu outra vez, agora à procura de `python3`, que sabemos que existe nos contentores do ERPNext. Encontrou o Python 3.14 em todos eles. A sonda funciona; o servidor simplesmente não tem Java.

Verificaram-se mais dois sítios antes de fechar a questão. O próprio host não tinha Java nem `/usr/lib/jvm`. Os repositórios sem nada em execução não tinham imagens Java nos seus daemons Docker. Um deles guardava um checkout do nosso próprio monorepo, e os seus ficheiros compose mencionavam `cassandra:5.0` e `elasticsearch:8.11.0`. Isso apontava para o passo seguinte.

## Passo 3: os templates que distribuímos

A Rediacc distribui templates de aplicações prontos a usar: um `docker-compose.yaml` mais um Rediaccfile por aplicação. Um servidor que não é nosso pode fazer deploy deles. Por isso, uma imagem Java num template é exposição para todos os clientes com o CPU certo, mesmo quando o nosso servidor está limpo.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

Quatro templates arrancam uma JVM. Em dois deles a configuração da imagem no registry já indica o JDK. Nos outros dois não, por isso corremos cada imagem uma vez e perguntámos:

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| Template | Tag no template | JDK lá dentro hoje | Estado |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | corrigido a montante, reconstruído a 20 nov |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | corrigido a montante, reconstruído a 20 nov |
| Solr | `solr:9-slim` | 17.0.21.1+2 | corrigido a montante, reconstruído a 20 nov |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (incluído) | **vulnerável**, ainda sem versão corrigida da Elastic |

![Fixado contra flutuante: a imagem fixada do Elasticsearch manteve um JDK de 2023, as tags flutuantes foram reconstruídas com a correção](/img/blog-java4shell-pinned-vs-floating.svg)

## A lição do pinning, revista

O post anterior terminava com "fixar tags exatas". Esta ronda acrescenta uma nota de rodapé a essa regra.

Fixar é o certo para as aplicações que corremos e atualizamos de propósito. O pin torna visível a versão em execução, e uma tag flutuante pode apontar para uma correção enquanto o servidor continua a correr uma imagem antiga, porque o `docker compose up -d` não faz pull de uma imagem que já tem.

Para templates que as pessoas implantam de raiz, o cenário inverte-se. As três tags de major flutuantes (`5.0`, `5-community`, `9-slim`) apanharam o JDK corrigido três dias depois da correção, sem qualquer alteração do nosso lado. O único pin exato, `8.11.0`, congelou o Elasticsearch numa imagem construída em novembro de 2023, com um JDK que nenhuma reconstrução dessa tag vai corrigir.

Por isso a regra que mantemos tem duas metades. As aplicações de produção têm tags exatas e uma atualização deliberada. Os templates também têm pins, porque o Elasticsearch e o Kibana têm de correr a mesma versão, mas todos os pins de templates estão agora listados no nosso registo de pins, onde os gates de frescura assinalam um pin que fica para trás em vez de o deixar parado durante três anos.

## Passo 4: a mitigação, provada num nó real

A Elastic anunciou que a correção chega como atualização do JDK incluído nas próximas versões 8.19.26, 9.4.10, 9.5.7 e 9.6.0. Até existir uma delas, a orientação oficial é a flag da JVM. No template, isso é mais uma palavra em `ES_JAVA_OPTS`:

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![O que a flag muda: o JIT mantém o descodificador Java simples em vez do intrinsic AVX-512](/img/blog-java4shell-intrinsic-flag.svg)

Uma flag num ficheiro compose é só uma afirmação até a JVM a confirmar. Verificámos duas vezes. Primeiro, o próprio JDK incluído, com e sem a flag:

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

Depois, um cluster real de um só nó arrancado com as opções do template. Ficou verde, e a sua própria API listou a flag entre os argumentos da JVM:

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## O que correu mal

**A verificação do CPU quase decidiu a resposta.** É a pré-condição mais visível, custa um comando e dizia "exposto". Só a segunda verificação, à procura de uma JVM a sério, transformou uma emergência a meio da noite numa alteração de template.

**Uma suite de testes correu onde não devia.** Para validar a edição do template, corremos a suite de ciclo de vida do pacote de templates numa workstation. Essa suite destina-se a um repositório Rediacc licenciado, não a um host Docker simples, e gastou mais de dez minutos a arrancar outros templates. Mostrou também que um template sem relação com isto escrevia o seu segredo gerado na própria pasta de código-fonte, um ficheiro que ninguém quer num commit. Esse template passa a escrever o segredo fora da árvore de código-fonte, e a suite recusa arrancar sem o repositório de que precisa.

**Não havia nada para fazer fork.** O nosso passo de segurança habitual, um fork do repositório de produção antes de qualquer alteração, não tinha alvo desta vez. A alteração vivia num ficheiro de template no git, por isso a rede de segurança foi um commit revisável e um teste de arranque real, não um snapshot.

## As escolhas e porquê

| Opção que tínhamos | O que escolhemos | Porquê |
|---|---|---|
| Tratar a verificação do CPU como a resposta | Procurar uma JVM a sério | O CPU dizia exposto; sem JVM não havia nada para explorar. |
| Confiar numa sonda vazia | Correr um controlo que tem de encontrar algo | Um resultado vazio de uma sonda avariada é igual ao de um servidor limpo. |
| Ler a versão do JDK no registry | Correr cada imagem uma vez | Duas das quatro imagens não registam a versão do JDK na configuração. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | Mais estreita: desliga uma rotina, não todas as acelerações AVX-512, e uma JVM ARM continua a arrancar. |
| Subir o Elasticsearch já para o 8.19 mais recente | Manter o 8.11.0, adicionar a flag, subir quando a versão corrigida sair | As versões mais recentes hoje ainda incluem um JDK afetado, e o Kibana tem de mudar no mesmo passo. |
| Pins exatos em todo o lado | Pins exatos mais um gate de frescura em cada pin de template | Um pin sem alarme congelou um JDK de 2023; o gate mantém o pin e acrescenta o alarme. |

## A checklist que mantemos

1. Verificar todas as pré-condições, não só a primeira que coincide.
2. Procurar o próprio runtime (`java`, `libjvm.so`), não só o nome de um produto.
3. Provar cada sonda vazia com um controlo.
4. Varrer o que distribuímos, não só o que corremos.
5. Ler a versão dentro da imagem; correr a imagem quando a configuração é omissa.
6. Preferir a mitigação mais estreita e confirmá-la no processo em execução.
7. Acompanhar a versão corrigida do fornecedor e remover a mitigação quando ela chegar.

Tal como na ronda anterior, um agente de IA (Claude Code) fez o trabalho através do `rdc`, com acesso à produção concedido pelo operador antes do início da sessão. Desta vez a produção não mudou de todo: cada passo no servidor foi uma leitura, e a única correção foi para um template, via git, com um teste real por trás.
