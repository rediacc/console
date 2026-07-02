---
title: 'git diff para Imagens de Disco Encriptadas: Comparar Forks Sem os Desencriptar'
description: >-
  O rdc repo diff compara imagens encriptadas ao nível dos blocos e reporta
  A/M/D/R. Nenhuma chave é tocada. O custo acompanha os blocos alterados, não o
  tamanho do repositório.
author: Rediacc
publishedDate: 2026-05-28T00:00:00.000Z
category: guide
tags:
  - luks
  - btrfs
  - ext4
  - fiemap
  - cli
featured: false
language: pt
sourceHash: 1b08ca130594e2e4
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
---

> **Resumo.** `rdc repo diff` mostra a diferença ao nível de ficheiros entre dois repositórios em fork na gramática do `git status --short` (A/M/D/R), e nunca desencripta nenhum deles.
>
> - Compara os dois ficheiros de imagem LUKS ao nível dos blocos com o ioctl FIEMAP, que lê apenas metadados do mapa de extents. Não é carregada nenhuma chave, não é lido nenhum texto em claro.
> - O aes-xts preserva o tamanho e encripta cada sector de 512 bytes de forma independente, pelo que um sector em claro alterado é um sector em criptograma alterado no mesmo offset (deslocado pelo offset de dados LUKS de 16 MiB). Subtraia o offset, mapeie os intervalos de dispositivo para nomes de ficheiro através do mapa de extents ext4, e obtém uma lista de ficheiros.
> - O custo acompanha o número de blocos alterados, não o tamanho do repositório. Um fork de 1 GB e um fork de 100 GB são comparados nos mesmos milissegundos, porque a comparação é apenas de metadados.

Assim, um fork no Rediacc é um `cp --reflink=always` da imagem LUKS de um repositório. Instantâneo, e não depende do tamanho. Um repositório de 100 GB faz fork tão rapidamente como um de 1 GB. Sei que parece marketing, mas é simplesmente assim que os reflinks funcionam: o btrfs copia o mapa de extents e partilha os blocos por baixo. Apoiamo-nos muito nisto. Os forks são a sandbox de testes, o branch descartável, a cópia de staging que se descarta quando termina.

O que não tínhamos era uma resposta barata para a pergunta óbvia que se segue: o que é que este fork realmente alterou. A rota óbvia: montar o fork, desbloquear o contentor LUKS, percorrer o ext4 interior, calcular o hash de cada ficheiro contra o pai. Isso escala com o tamanho do repositório tanto em leituras como em desencriptação. Precisa das chaves no caminho do diff. E desperdiça a única coisa que a camada de armazenamento já sabe de graça: quais os blocos que divergiram. O `rdc repo diff` toma o outro caminho. Escala com os blocos alterados. Não carrega chaves. Obtém a lista de ficheiros comparando as duas imagens encriptadas.

## A pilha que está a comparar

Deixe-me ser preciso sobre o que significam "dois repositórios" em disco. Todo o truque depende disso. De baixo para cima: um SSD, o armazenamento do host, um pool btrfs. Por cima, um ficheiro de imagem LUKS2 por repositório. Desbloqueie-o e obtém um dispositivo dm-crypt. Dentro desse vive o sistema de ficheiros ext4 que os contentores utilizam. Um repositório é um ficheiro no pool btrfs.

Um fork é um reflink desse ficheiro. Logo após o fork, os dois ficheiros de imagem são byte-a-byte idênticos. Partilham todos os blocos físicos. O pai e o fork não são duas cópias dos dados. São dois mapas de extents que apontam para os mesmos blocos. Quando escreve dentro do fork, a camada de armazenamento aloca um bloco novo para a região alterada. Apenas o mapa de extents desse fork é reescrito. Os blocos do pai ficam intactos.

Portanto, "comparar dois repositórios" reduz-se a "comparar dois ficheiros que partilham a maioria dos seus extents." O kernel já consegue responder a isso. Ninguém precisa de ler um único byte de qualquer dos ficheiros.

## FIEMAP: perguntar ao kernel o que mudou sem o ler

O ioctl FIEMAP devolve o mapa de extents de um ficheiro: uma lista de tuplos (offset lógico, offset físico, comprimento). Cada tuplo diz onde vive uma parte do ficheiro em disco. São metadados puros do sistema de ficheiros. Não lê dados de ficheiros. Para uma imagem encriptada não precisa de nenhuma chave. O criptograma são apenas bytes que o kernel nunca tem de interpretar.

Compare os dois mapas de extents. Qualquer intervalo lógico onde ambos os forks apontam para o mesmo bloco físico é partilhado. Partilhado significa idêntico, porque é literalmente o mesmo bloco no dispositivo. Os intervalos onde o fork tem o seu próprio bloco privado são as escritas. Esses são os blocos alterados. Obtivemo-los dos metadados que a camada de armazenamento mantém de qualquer forma.

É aqui que vem a história do custo. A comparação FIEMAP lê registos de extents, não dados. O seu trabalho escala com quantos extents mudaram, não com o tamanho do repositório. O fork de 1 GB e o de 100 GB devolvem a mesma lista curta de extents privados. Mesmos milissegundos, se alteraram os mesmos ficheiros. Ressalva honesta: o tempo de percurso de extents escala com a fragmentação da imagem, não com o tamanho. Uma imagem copy-on-write sob escritas aleatórias intensas acumula extents. O percurso completo com `filefrag` demorou 3,19 segundos na imagem de produção mais fragmentada que medi. Veja o artigo sobre benchmark de fragmentação. Esse é o teto do lado dos metadados. É uma análise em segundo plano, não uma leitura de dados.

## De um bloco alterado a um nome de ficheiro, através de duas camadas encriptadas

Uma lista de intervalos de bytes alterados na imagem encriptada ainda não é útil. Os intervalos são posições no criptograma. Os nomes que quer vivem duas camadas acima, no ext4 interior. A ponte entre eles é aritmética de endereços, não desencriptação.

O LUKS encripta com aes-xts. Preserva o tamanho e encripta cada sector de 512 bytes por conta própria. Um sector em claro alterado produz um sector em criptograma alterado no mesmo offset. O único deslocamento é o offset de dados LUKS. São os 16 MiB de cabeçalho e slots de chave antes do payload encriptado. Subtraia esse offset de cada intervalo de imagem alterado. Agora tem o intervalo correspondente no dispositivo dm-crypt. Esse é o dispositivo de bloco onde vive o ext4 interior. Não foi usada nenhuma chave. É uma subtração.

Agora mapeie os intervalos do dispositivo para ficheiros. O ext4 também mantém um mapa de extents por inode. Mesma estrutura (lógico, físico, comprimento). Acede-se a ele através do FIEMAP no sistema de ficheiros interior montado. Percorra os inodes uma vez para construir um índice bloco-para-ficheiro. Depois procure cada intervalo de dispositivo alterado nesse índice. Um intervalo que se sobreponha aos extents de dados do inode 1234 pertence ao caminho desse inode. Esse caminho é o ficheiro que mudou.

Deixe-me declarar claramente o que isto nunca faz. Nunca deriva texto em claro da imagem alterada. Lê estrutura de sistema de ficheiros em offsets conhecidos. Faz isto tanto no lado encriptado como no lado desencriptado. Depois junta os dois por endereço. O filtro de blocos diz quais as regiões do dispositivo que se moveram. O mapa de extents ext4 diz qual o ficheiro que detém cada região. Nenhum dos passos inspeciona o conteúdo de um bloco alterado para decidir que mudou.

## Adições, eliminações e renomeações: o percurso de identidade de inode

As modificações resultam diretamente da comparação de blocos. As adições, eliminações e renomeações precisam de mais uma observação. O reflink dá-a de graça: um fork preserva números de inode. Criar um reflink de toda a imagem clona o sistema de ficheiros interior byte a byte antes de qualquer divergência. Portanto, um inode que existia no pai tem o mesmo número no fork.

Isso torna a identidade uma comparação de conjuntos. Um inode em ambos os lados com um caminho diferente é uma renomeação. Um inode apenas no novo lado é uma adição. Um inode apenas no lado antigo é uma eliminação. Uma renomeação é confirmada pela sobreposição de extents do dispositivo. Os blocos de dados do ficheiro renomeado estão nos mesmos offsets do dispositivo em ambos os forks. Os dois forks partilham um sistema de coordenadas. Essa sobreposição também descarta um número de inode sendo reutilizado para dados não relacionados. Uma renomeação pura aparece então com os blocos de dados do ficheiro inalterados. Apenas a entrada de diretório se moveu.

Aqui está a forma padrão de estado de nomes, a mesma gramática A/M/D/R que já se lê do `git status --short`:

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Um ficheiro modificado num repositório de 1 GB. Reportado a partir de uma comparação de blocos que não leu dados de ficheiro. Nada foi desbloqueado.

O modo padrão faz mais uma coisa para correção. O filtro de blocos é um superconjunto. Um extent btrfs pode cobrir mais bytes do que os que realmente mudaram. Por isso, uma escrita num ficheiro pode sinalizar um vizinho que partilha um extent. Para evitar reportar um ficheiro que não mudou, o padrão confirma cada candidato sinalizado por bloco. Calcula o hash apenas desse ficheiro em ambos os lados. Calcula o hash dos candidatos, não do repositório. Portanto, o custo de confirmação ainda acompanha o conjunto de alterações. `--fast` confia no filtro de blocos e salta a confirmação. Use-o quando quer a resposta rapidamente e tolera um falso positivo ocasional.

## Porque é que um agente de IA precisa disto

A razão pela qual este comando existe é o fluxo de trabalho de agente. Passei a observar agentes a fazer fork da produção, executar alterações, e depois não ter forma limpa de reportar o que realmente tocaram. Um agente de IA pode fazer fork da produção instantaneamente. Executa uma alteração arriscada dentro do fork isolado. Depois precisa de saber exatamente o que tocou antes de promover qualquer coisa de volta. O fork é o branch. O diff é a revisão.

O agente não lê o estado de nomes, lê `--json`:

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

O output estruturado dá ao agente um conjunto de alterações preciso. Quais os caminhos que modificou, criou, eliminou. Com `--stat`, o tamanho da alteração por ficheiro em bytes e blocos. Um agente que vê o seu diff antes de promover é um que pode deixar perto da produção. O raio de ação é inspecionável, não afirmado. Outros modos servem o mesmo ciclo de revisão. `--name-only` para uma lista simples de caminhos. `--content <path>` para um diff unificado em texto de um ficheiro (apenas texto; um ficheiro binário reporta `Binary files differ`). `--stat` quando o agente precisa de saber o que mudou e quanto.

## Porque é que os testes de DR precisam disto

A mesma primitiva responde a uma pergunta de DR que costumava ser difícil de fazer sem risco. Fork da produção. Restaure um backup para o fork. Compare o fork contra a produção. O diff diz se o restauro reproduziu o conjunto de ficheiros esperado. Faz isto sem desligar a produção. E nunca desencripta nada no caminho do diff.

Isso é um ensaio que pode executar num agendamento. O restauro aterra num fork isolado. O diff reporta o delta na gramática do git. Um ensaio limpo: o conjunto alterado corresponde ao que o backup deveria conter. Está a validar a recuperação contra a produção em direto. A cópia não custa nada a fazer e nada a descartar.

## Limitações honestas

O diff de conteúdo é apenas para texto. `--content` produz um diff unificado para ficheiros de texto. Para tudo o resto reporta `Binary files differ`, tal como o git faz. Um diff orientado a linhas de um blob encriptado e depois comprimido é ruído.

Compara forks relacionados, não repositórios arbitrários. Todo o mecanismo assenta num sistema de coordenadas partilhado. Extents partilhados provam igualdade. Números de inode preservados ancoram a identidade. Um offset de dados comum liga tudo. Dois repositórios que nunca foram colocados em fork a partir de um ancestral comum não partilham nada disso. Não há diff barato entre eles. Isso é uma funcionalidade, não um erro. Da mesma forma que um `git diff` entre duas histórias não relacionadas não é significativo.

A deteção de renomeações é baseada em inode. É exata para as renomeações que um sistema de ficheiros regista efetivamente como renomeações. Uma eliminação seguida de criação de conteúdo idêntico com um novo nome? Duas operações na tabela de inodes. Por isso reporta como uma eliminação e uma adição, não uma renomeação. A heurística de similaridade de conteúdo do git chamaria isso uma renomeação. O percurso de inode não. Essa é a resposta correta sobre o que o sistema de ficheiros fez. Mesmo que não seja a resposta sobre o que um humano pretendia.

E o percurso de metadados escala com a fragmentação. Numa imagem muito fragmentada a enumeração de extents demora segundos, não milissegundos. Ainda é independente do tamanho do repositório. Ainda está livre de qualquer leitura de dados. Mas não é literalmente instantâneo nas imagens mais fragmentadas.

## A conclusão

O `rdc repo diff` coloca a ergonomia do controlo de versões em infraestrutura encriptada e em funcionamento. A interface é deliberadamente do git. A/M/D/R, diffs unificados, `--stat`. Nada de novo para aprender. Se consegue ler `git status --short`, consegue ler um diff entre duas imagens LUKS. A engenharia subjacente é a parte que vale a pena conhecer. Equivale a duas recusas. Nunca desencripta. O aes-xts permite que uma comparação FIEMAP ao nível dos blocos localize cada sector alterado por endereço. E nunca paga por dados que não mudaram. A camada de armazenamento já registou quais os blocos que divergiram. O fork é o branch. O diff é a revisão. A revisão custa o que a alteração custa, não o que o repositório pesa.
