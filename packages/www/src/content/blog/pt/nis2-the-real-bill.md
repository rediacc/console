---
title: "O Que os Compradores Nos Disseram no Primeiro Ciclo de Auditoria NIS2"
description: "O conjunto de cinco ferramentas de conformidade que as entidades essenciais do mercado intermédio estão discretamente a montar em 2026, o que um plano de controlo auto-alojado consolida, e as rubricas que ficam do seu lado de qualquer forma."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - guia-de-compra
  - conformidade
  - custo
  - mercado-intermedio
featured: false
language: pt
sourceHash: "3fbb581ec14e3f80"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
translatedFrom: en
---

As auditorias NIS2 do primeiro ciclo já ficaram para trás na vaga alemã. Os compradores com quem falámos desde dezembro descrevem todos uma versão do mesmo conjunto: cinco ferramentas, três contratos, dois registos de auditoria sobrepostos e uma lacuna que não conseguem fechar. Esta publicação é a versão estrutural dessa conversa. O que um plano de controlo auto-alojado consolida, o que fica no seu orçamento de qualquer forma, e por que o enquadramento certo para um ciclo de renovação em 2026 não é "mais barato que o Veeam" mas sim "menos entradas no registo, menos sobreposições, as mesmas lacunas nomeadas com honestidade."

- A Frontier Economics estimou o custo de conformidade NIS2 em toda a UE em EUR 31,2 mil milhões por ano. A realidade por organização, no mercado intermédio, é: "já tínhamos uma pilha de segurança; a NIS2 expôs o que estava em falta."
- O conjunto de cinco ferramentas: backup, DR, mascaramento ou dados de teste, contrato de pen test, GRC. Cada um cobre parte do trabalho. Nenhum cobre tudo.
- A Rediacc consolida backup, DR, fork como dados de teste e restauro instantâneo num único plano de controlo com um único registo de auditoria. Não consolida GRC, certificações, formação, MFA corporativo alargado, pen testing, nem SIEM e SOC.
- A tabela honesta de "ainda é seu" é o ponto central desta publicação. Um comprador que a leia e conclua que a Rediacc substitui a Drata vai desapontar o seu auditor.

Em dezembro de 2025, o BSI na Alemanha emitiu 47 notificações formais a entidades que considerou estar no âmbito da NIS2 mas não registadas. A ANSSI em França iniciou um exercício paralelo. A ACN em Itália começou a contactar cerca de 2.000 entidades que considerava não registadas. A primeira vaga de entidades essenciais e importantes do mercado intermédio entrou no seu primeiro ciclo de auditoria NIS2.

Desde então, falámos com cerca de trinta dessas entidades. Setores diferentes, dimensões diferentes, maioritariamente Alemanha e Itália com alguns casos nos Países Baixos e na Estónia. As conversas repetem-se. Cada equipa tem um fornecedor de backup, um plano de DR que pode ou não ter sido testado, uma história sobre staging que é só metade verdade, e um orçamento de aquisição aprovado antes de a NIS2 aparecer nos slides de alguém.

Esta publicação é a versão estrutural dessas conversas. O que um CFO ou um comprador está efetivamente a ser solicitado a assinar em 2026, o que um plano de controlo auto-alojado muda na fatura, e qual é o custo residual honesto. Deliberadamente, não é uma calculadora de TCO. Os compradores com quem falamos não precisam de mais uma folha de cálculo; precisam de um mapa estrutural de onde está a ir o dinheiro e quais as rubricas que se sobrepõem.

Se quiser o argumento de risco da cadeia de fornecimento por detrás da afirmação "o auto-alojamento é importante", veja a [publicação complementar sobre o Artigo 21.º(2)(d)](/pt/blog/nis2-supply-chain-self-hosted). Se quiser o argumento ao nível SRE sobre por que os pen tests anuais já não são suficientes, veja a [publicação complementar sobre eficácia contínua](/pt/blog/nis2-effectiveness-without-theatre). Esta publicação situa-se entre ambas, na conversa orçamental.

## O número macro e o que significa e não significa

O estudo de 2024 da Frontier Economics para a Comissão Europeia estimou o custo anual direto da conformidade NIS2 em toda a UE em EUR 31,2 mil milhões. O valor é amplamente citado; também é amplamente mal interpretado.

Os EUR 31,2 mil milhões distribuem-se por cerca de 160.000 entidades essenciais e importantes. Por organização, a média situa-se entre EUR 150.000 e EUR 250.000, com o setor e a dimensão a impulsionar a maior parte da variação. Uma entidade essencial do mercado intermédio com 250 colaboradores no setor da manufatura ou da saúde encontra-se na extremidade mais alta desse intervalo. Uma entidade importante com 60 colaboradores num setor com menor intensidade de dados está na extremidade mais baixa.

A orientação da ENISA sobre custos de implementação (Anexo IV do Regulamento de Execução (UE) 2024/2690) é consistente com o valor da Frontier, mas decompõe-no de forma diferente: aproximadamente 35 a 45 por cento em ferramentas, 30 a 40 por cento em pessoal e formação, 15 a 20 por cento em certificação e auditoria, 5 a 10 por cento em retentores de resposta a incidentes e serviços geridos.

O que isto significa para um CFO que assina o orçamento de 2026: a camada de ferramentas representa aproximadamente EUR 50.000 a EUR 120.000 por ano para o mercado intermédio, dependendo do que já está em vigor. É essa camada de ferramentas que vamos percorrer.

O que não significa: que adquirir um pacote NIS2-ready resolve o problema. Os orçamentos de formação de pessoal e certificação são maiores do que o orçamento de ferramentas para a maioria das equipas, e nenhum fornecedor de ferramentas os reduz. Uma apresentação de fornecedor que afirma uma redução de 50 por cento nos custos NIS2 está quase sempre a fazer as contas apenas contra a rubrica de ferramentas, não contra o custo total do programa.

## O conjunto de cinco ferramentas que as equipas do mercado intermédio montaram discretamente

Nas trinta conversas com compradores, o conjunto parece o mesmo em 90 por cento dos casos. Cinco categorias, com um ou dois fornecedores nomeados por categoria. As etiquetas das categorias são estáveis; as escolhas de fornecedores variam.

**1. Fornecedor de backup.** O Veeam Data Platform Foundation ou Premium é a resposta modal. Cohesity DataProtect, Rubrik Security Cloud, Commvault, Acronis Cyber Protect nas soluções de menor dimensão. Custo anual entre EUR 15.000 e EUR 60.000 para o mercado intermédio. Normalmente a rubrica mais antiga; anterior à NIS2 por vários anos.

**2. Site de DR ou DR-as-a-service.** Seja uma região cloud secundária com um runbook, uma licença de Veeam Cloud Connect ou Rubrik Cloud Vault, ou um contrato com um fornecedor gerido de DR. Custo anual entre EUR 8.000 e EUR 35.000. Raramente testado na prática; o runbook é normalmente mais aspiracional do que operacional.

**3. Ferramenta de dados de teste ou mascaramento de dados.** O Delphix (agora Perforce DevOps Data) é o padrão empresarial. Tonic.ai, Redgate Test Data Manager, ocasionalmente um script rsync-and-mask desenvolvido internamente. Custo anual entre EUR 25.000 e EUR 90.000 para as opções licenciadas. A maioria das equipas nas nossas chamadas não tem esta rubrica; têm aquilo que esperam ser um ambiente de staging suficientemente bom. A conversa de auditoria sobre o Artigo 21.º(2)(e) é o que a coloca no orçamento.

**4. Contrato de pen test.** Um retainer com uma empresa de testes de segurança ou uma plataforma autónoma como a Pentera ou a Horizon3.ai. Custo anual entre EUR 15.000 e EUR 50.000 para as ferramentas autónomas, EUR 20.000 a EUR 80.000 para os compromissos liderados por humanos. A maioria das equipas tem este contrato. A maioria das equipas faz-o uma ou duas vezes por ano.

**5. Plataforma GRC.** Drata, Vanta, OneTrust, AuditBoard, Hyperproof, DataGuard, Kertos. Às vezes uma folha de cálculo desenvolvida internamente para as equipas mais pequenas. Custo anual entre EUR 12.000 e EUR 60.000. Utilizada para o registo de fornecedores, atestação do quadro de controlos, recolha de evidências e (cada vez mais) suporte a auditorias SOC 2 ou ISO 27001.

Cinco rubricas, três a cinco fornecedores nomeados, tipicamente entre EUR 75.000 e EUR 295.000 por ano antes de pessoal e formação. A variação é ampla, mas a estrutura é consistente.

Os cinco contratos frequentemente não comunicam entre si. Os registos de auditoria não estão unificados. Os planos de saída são escritos separadamente. As revisões de fornecedores são feitas separadamente, por vezes por diferentes responsáveis de aquisição. Esta é a forma estrutural que a NIS2 torna incómoda.

## Onde estão as sobreposições

Cada categoria no conjunto sobrepõe-se pelo menos a uma outra.

**O backup sobrepõe-se ao DR.** Os fornecedores de backup modernos afirmam todos ser capazes de DR. O Veeam Data Platform com Cloud Connect é um produto de DR. O Rubrik com Cloud Vault é um produto de DR. As duas rubricas pagam frequentemente capacidades adjacentes no mesmo fornecedor. Os compradores que historicamente não consolidaram as rubricas tinham razões operacionais (equipas separadas, SLAs separados); sob a expetativa da NIS2 de "fonte única de verdade para recuperação", o racional enfraquece.

**O backup sobrepõe-se aos dados de teste.** O Veeam Instant Recovery, o Rubrik Live Mount e o Cohesity SmartFiles oferecem todos alguma forma de backup montável para testes. Não são substitutos completos do Delphix (a camada de mascaramento é separada, a integração de bases de dados é mais superficial), mas para muitos casos de utilização de dados de teste a ferramenta de backup é metade da resposta. A maioria das equipas não se apercebe.

**O pen test sobrepõe-se aos testes autónomos.** O pen test humano baseado em retainer e os testes contínuos ao estilo Pentera são por vezes apresentados como alternativas, por vezes como complementos. Na prática, um comprador com ambos está a pagar duas vezes por capacidade adjacente. Um comprador sem nenhum tem uma lacuna no Artigo 21.º(2)(f).

**O GRC sobrepõe-se a tudo.** A Drata afirma integração com backup, DR, identidade, gestão de vulnerabilidades, formação e resposta a incidentes. As integrações variam em profundidade. Uma plataforma GRC com integração superficial numa ferramenta de backup produz evidências de conformidade que não são as mesmas que as evidências da própria ferramenta de backup; os auditores estão a começar a perguntar qual é a canónica.

As sobreposições não são desperdício. São a consequência de um conjunto montado ao longo de uma década, antes de a NIS2 tornar a questão da consolidação estrutural.

## Onde estão as lacunas

As lacunas são mais interessantes do que as sobreposições, porque as lacunas são o que a NIS2 expõe.

**Validação de patches contra dados de produção reais.** Nenhuma das cinco categorias faz isto bem. As ferramentas de backup montam o backup; o ambiente montado é o backup recuperado, não a produção atual. As ferramentas de dados de teste mascaram os dados de produção; o ambiente mascarado é realista na forma, mas perde os deltas de configuração. Os contratos de pen test testam o que lhes é apontado, que é o staging em 90 por cento dos casos. A lacuna entre "temos ferramentas" e "conseguimos testar um patch de CVE contra um ambiente equivalente à produção atual em menos de uma hora" é real e estrutural.

**Avaliação contínua de eficácia.** A cadência anual é o que a maioria das equipas faz. O Artigo 21.º(2)(f) quer algo mais frequente. Nenhuma das cinco categorias produz evidências semanais ou bissemais por defeito. O comprador ou executa exercícios personalizados (raro, caro) ou aceita a cadência anual e espera que o auditor a aceite (cada vez mais, não aceita).

**Consolidação do registo da cadeia de fornecimento.** Cada um dos cinco fornecedores é a sua própria entrada no registo. Cada um tem o seu próprio DPA, SCC, lista de subprocessadores e plano de saída. O registo tem cinco entradas de nível 1 antes de se adicionarem ferramentas de formação de pessoal, ferramentas de identidade, ferramentas de observabilidade e IaaS. A conversa sobre a cadeia de fornecimento, em termos NIS2, é tanto uma conversa de gestão de registo como uma conversa de segurança. (Veja a [publicação sobre a cadeia de fornecimento](/pt/blog/nis2-supply-chain-self-hosted) para o argumento estrutural.)

**Fluxo de trabalho de reporte do Artigo 23.º.** O aviso precoce de 24 horas, a notificação de 72 horas e o relatório de um mês não são produzidos automaticamente por nenhuma das cinco categorias. Requerem um SIEM, um SOC (interno ou externalizado) e uma pessoa que saiba como reportar ao CSIRT nacional. As equipas mais pequenas frequentemente não têm isto. O primeiro incidente é a experiência de aprendizagem dolorosa.

## O que a Rediacc consolida

A Rediacc é um único plano de controlo com um registo de auditoria unificado, substituindo a capacidade central de quatro das cinco categorias para infraestrutura auto-alojada.

**O Backup** corre em dois modos. O modo quente é um snapshot BTRFS crash-consistent. Sem tempo de inatividade. O modo frio faz um ciclo de paragem, snapshot, arranque. Ambos agendam em timers systemd. Ambos enviam para vários destinos via rclone. Os volumes são encriptados com LUKS. O operador detém a chave. A Rediacc-empresa nunca vê dados em texto simples. Veja [Backup & Restore](/pt/docs/backup-restore) e [Cross Backup Strategy](/pt/docs/cross-backup).

**DR**: a mesma primitiva do backup, mais `rdc repo migrate` para movimentação de dados entre máquinas, mais a primitiva fork para arranque rápido do estado recuperado numa máquina paralela. O site de DR pode ser outra máquina Hetzner, uma máquina OVH, um rack on-prem, em qualquer lugar que o SSH alcance. Sem cloud de fornecedor de DR no caminho de dados.

**Os dados de teste e clonagem full-stack** correm em reflink BTRFS. O fork é de tempo constante, independentemente do tamanho do repositório. Full-stack significa dados, configurações, contentores e serviços. Fizemos fork de um repositório de 128 GB em 7,2 segundos no nosso [teste PocketOS](/pt/blog/i-tested-rediacc-against-the-pocketos-incident). O fork é a produção atual, não uma cópia de staging simplificada. Veja [Risk-Free Upgrades](/pt/docs/risk-free-upgrades).

**Restauro instantâneo**: `rdc repo backup pull` de qualquer destino rclone para um fork novo, iniciado sob um subdomínio específico do fork coberto pelo certificado wildcard do repositório pai. Sem confusão de DNS, sem dança de certificados.

**Registo de auditoria unificado.** Mais de 70 tipos de eventos em todo o plano de controlo. Cobrem logins, tokens de API, escritas de configuração, ciclo de vida de repositórios, backup, sincronização, sessões de terminal e operações de máquina. A cadeia está encadeada por hash na workstation do operador. `rdc audit verify` verifica-a de ponta a ponta.

Para uma entidade essencial do mercado intermédio com 250 colaboradores, a consolidação passa de quatro fornecedores nomeados (backup, DR, dados de teste, restauro instantâneo) para um. Uma licença, um registo de auditoria, um conjunto de decisões de atualização, uma entrada no registo.

A quinta categoria, GRC, não é consolidada. Voltamos a isso.

## O que fica no seu orçamento de qualquer forma

Esta é a secção que determina se o resto da publicação é honesto. A tabela de duas colunas:

| Removido pela Rediacc | Ainda seu, rubrica a rubrica |
|---|---|
| Licença do fornecedor de backup | Plataforma GRC (Drata, Vanta, OneTrust, AuditBoard, DataGuard) para o registo de fornecedores, atestação do quadro de controlos, recolha de evidências e suporte a auditorias SOC 2 ou ISO 27001 |
| Contrato de site DR ou licença DR-as-a-service | Custos de auditoria de certificação (ISO 27001, SOC 2, BSI C5 se necessários; a Rediacc ainda não está certificada, pelo que esse custo fica do seu lado entretanto) |
| Licença de ferramenta de dados de teste ou mascaramento | Orçamento de formação de pessoal e sensibilização para a segurança (Artigo 21.º(2)(g) da NIS2) |
| Licença de recuperação instantânea no fornecedor de backup | Solução MFA corporativa mais abrangente; a Rediacc tem TOTP no portal, não uma plataforma MFA corporativa |
| | Contrato de pen testing ou plataforma de testes autónomos; a Rediacc disponibiliza o ambiente alvo, não a capacidade de teste |
| | SIEM e SOC para deteção e reporte do Artigo 23.º; a Rediacc disponibiliza artefactos de qualidade forense, não a camada de reporte operacional |
| | Fornecedor de IaaS (Hetzner, OVH, o seu colo, o seu bare metal); a Rediacc corre sobre, não em vez de, infraestrutura |
| | Pessoal a gerir o programa. A Rediacc é uma camada de ferramentas, não uma equipa de segurança |

O lado direito da tabela é mais longo do que o lado esquerdo. Esta é a forma honesta do que a NIS2 custa. Remover a sobreposição de backup, DR e dados de teste poupa dinheiro real e entradas reais no registo; não transforma um programa de segurança numa subscrição SaaS.

Um comprador que leia isto e conclua "posso substituir a Drata pela Rediacc" vai desapontar o seu auditor. A leitura correta é: a consolidação de fornecedores no plano de dados que a Rediacc permite é o que as ferramentas GRC não conseguem fazer, e o trabalho de registo e evidências que as ferramentas GRC fazem é o que a Rediacc não faz. As duas são complementares.

Mais três ligações se quiser profundidade. O mapeamento público está em [NIS2 e DORA](/pt/docs/legal-nis2-dora). O enquadramento mais amplo está em [Compliance Overview](/pt/docs/legal-overview). O lado comercial da Rediacc está em [Subscription & Licensing](/pt/docs/subscription-licensing).

## Um cenário de referência, estrutural e não numérico

Considere uma empresa alemã de manufatura com 250 colaboradores. Classificação de "entidade importante" do Anexo II. Dados de produção em 4 a 6 servidores, maioritariamente auto-alojados com uma ou duas ferramentas SaaS (CRM, salários). Faturação anual de EUR 80M. Equipa de segurança existente de 3 pessoas.

**Antes**, o seu conjunto no plano de dados:

- Veeam Data Platform Foundation, EUR 24.000/ano
- Veeam Cloud Connect para DR, EUR 12.000/ano
- Um esquema rsync-plus-pg_dump desenvolvido internamente para dados de teste, gratuito em licença mas custa a um SRE meio dia de duas em duas semanas
- Pen test anual, EUR 22.000
- Drata para GRC, EUR 18.000/ano

Cinco contratos. Dois deles (Veeam, Veeam Cloud Connect) são com o mesmo fornecedor mas SKUs diferentes. As rubricas do plano de dados totalizam EUR 36.000/ano antes de contar o pen test ou GRC. A equipa produz um teste de recuperação anual, sem evidências de eficácia contínua, e um registo de fornecedores com cinco entradas apenas no lado do plano de dados.

**Depois**, com a Rediacc no Hetzner para as cargas de trabalho auto-alojadas:

- Rediacc Business tier, EUR 8.400/ano (cobre o tamanho dos seus repositórios)
- IaaS Hetzner para primário e secundário, EUR 9.600/ano combinados (já no orçamento; sem nova rubrica)
- O contrato de pen test mantém-se (EUR 22.000)
- A Drata mantém-se (EUR 18.000)
- O esquema de dados de teste desenvolvido internamente é retirado; o meio dia do SRE de duas em duas semanas passa a executar a rotina de eficácia semanal

Consolidação do plano de dados: 5 rubricas passam a 1 (Rediacc) mais a linha IaaS existente. A secção de plano de dados do registo de fornecedores passa de 5 entradas para 2. O argumento de eficácia contínua passa a ser exercícios semanais com evidências de registo de auditoria encadeado por hash; o argumento de teste de recuperação passa a ser suportado pelo output de `rdc machine backup status` e um exercício de restauro semanal.

Os números são ilustrativos, não promessas. O seu conjunto é diferente. A forma, quatro a cinco rubricas a consolidar numa mais a IaaS existente, é o que parece uma conversa real com um comprador.

## Uma nota sobre o que isto não é

Esta publicação não é um ataque ao Veeam nem uma calculadora de TCO. O Veeam detém a maior quota de mercado de backup de VMs na Europa por boas razões; o seu produto é maduro, a sua rede de parceiros é ampla, o seu marketing NIS2 é forte, e um comprador que escolha o Veeam em 2026 não está a cometer um erro. Os números no cenário de referência são ilustrativos, retirados de conversas reais com compradores, não de benchmarks. Execute a análise estrutural contra os seus próprios contratos.

O que isto é: um enquadramento do lado do comprador para um CFO que está a renegociar um contrato de backup, DR ou conformidade nos próximos doze meses e quer saber o que um plano de controlo auto-alojado muda nas rubricas.

## O que fazer a seguir

Se está a entrar num ciclo de renovação e o orçamento está em aberto, três ações concretas:

1. **Retire as três maiores rubricas de segurança e infraestrutura do ano passado.** Envie-as ao seu DPO, ao seu CISO e ao seu auditor. Pergunte quais já eram redundantes antes de a NIS2 o tornar visível. A maioria das equipas encontra pelo menos uma sobreposição pela qual tem estado a pagar.
2. **Mapeie o seu conjunto atual de plano de dados contra a lista das cinco categorias acima.** Note quais as categorias para as quais tem um fornecedor, quais tem dois e quais não tem nenhum. As células "nenhum" são as lacunas que a NIS2 vai expor.
3. **Execute o exercício de registo de fornecedores da [publicação sobre a cadeia de fornecimento](/pt/blog/nis2-supply-chain-self-hosted)** para cada fornecedor do plano de dados. Conte as entradas do registo. O número é habitualmente superior ao que a equipa esperava.

Se estamos na lista restrita, a oferta é concreta. Envie as suas três maiores rubricas do orçamento de segurança e infraestrutura do ano passado. Diremos quais podem ser consolidadas e quais não podem, por escrito, em uma semana. A resposta incluirá as lacunas, porque nomear as lacunas é o que torna o resto da resposta credível.

Mais três documentos se quiser ir mais fundo. [Backup de custo zero](/pt/docs/zero-cost-backup) explica porque corremos mais leve no armazenamento do que os incumbentes. [Cross Backup Strategy](/pt/docs/cross-backup) cobre o DR intercontinental. [Subscription & Licensing](/pt/docs/subscription-licensing) é o lado comercial.
