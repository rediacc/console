---
title: "Article 21(2)(d) é uma Questão de Fornecedor. O Auto-Alojamento é a Resposta que Deixa de Dever."
description: "Porque razão o registo de fornecedores TIC de terceiros encolhe quando o plano de dados nunca sai do seu alojamento. Uma leitura prática do NIS2 Article 21(2)(d) para CISOs e responsáveis de procurement a renegociar DPAs em 2026."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - cadeia-de-abastecimento
  - auto-alojamento
  - soberania
  - conformidade
featured: false
language: pt
sourceHash: "98f0b752bc5dbd4d"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
translatedFrom: en
---

> **Resumo.** O NIS2 Article 21(2)(d) transforma o risco na cadeia de abastecimento numa questão de conselho de administração, não numa nota de rodapé de procurement. A diretiva não exige efetivamente o auto-alojamento. Pergunta, no entanto, o que existe no seu plano de dados e o que lhe acontece quando um desses fornecedores tem uma segunda-feira de crise. A infraestrutura auto-alojada colapsa três das quatro camadas nos planos de dados SaaS mais comuns. Não colapsa as quatro, e fingir o contrário é a jogada de marketing que coloca um CISO em dificuldades perante um auditor.
>
> - O texto da diretiva e as orientações da ENISA, em linguagem clara.
> - O plano de dados SaaS de quatro camadas que a maioria das equipas esquece de desenhar.
> - O que o modelo de duas ferramentas da Rediacc remove do seu registo de fornecedores, e o que nele deixa.
> - Uma lista de verificação de procurement com seis perguntas para qualquer fornecedor que se afirme "NIS2-ready."

Em julho de 2020, a Blackbaud pagou um resgate e informou o mundo só depois. Notificou mais de 13 000 organizações clientes após o facto, enfrentou ações coletivas em sete jurisdições e acabou por pagar 49,5 milhões de dólares em acordos com procuradores-gerais estaduais e uma coima de 3 milhões de dólares da SEC por divulgações enganosas. Cada uma dessas 13 000 organizações tinha um Acordo de Processamento de Dados com a Blackbaud. A maioria tinha revisto o relatório SOC 2 da Blackbaud. Muitas tinham a Blackbaud num registo de risco de fornecedores, com uma classificação de nível, uma data de renovação e um responsável nomeado.

Nada disso travou a cascata. Os dados estavam do lado da Blackbaud. Quando o ambiente de cópia de segurança foi comprometido, todas as organizações clientes foram comprometidas simultaneamente.

O NIS2 Article 21(2)(d) coloca uma pergunta mais difícil do que "auditou o seu fornecedor." Pergunta o que existe no plano de dados e o que lhe acontece quando esse fornecedor tem uma segunda-feira de crise. A resposta, para a maioria das equipas, é "somos eles, e não nos tínhamos apercebido."

Este artigo destina-se a CISOs e responsáveis de procurement a renegociar DPAs em 2026. É a leitura do plano de dados do Article 21(2)(d), não a leitura das certificações. É também honesto sobre o que a infraestrutura auto-alojada não resolve, porque a secção de lacunas é o que um auditor irá perguntar e um brochura de marketing irá omitir.

## O que o 21(2)(d) efetivamente obriga

O texto da diretiva diz, com ligeira simplificação para clareza:

> "As medidas referidas no n.o 1 devem basear-se numa abordagem que abranja todos os riscos e que vise proteger os sistemas de rede e informação [...] e devem abranger pelo menos os seguintes aspetos: [...] d) Segurança da cadeia de abastecimento, incluindo aspetos de segurança respeitantes às relações entre cada entidade e os respetivos fornecedores ou prestadores de serviços diretos"

Dois elementos nesse texto são relevantes para um comprador.

Em primeiro lugar, a obrigação recai sobre si, não sobre o fornecedor. As certificações do fornecedor, o SOC 2 do fornecedor, o ISO 27001 do fornecedor são contributos para a sua avaliação de risco. Não a substituem. Se o seu fornecedor tiver uma postura de conformidade perfeita e mesmo assim sofrer uma violação, a pergunta do regulador vai incidir sobre a sua gestão de risco de fornecedores, não sobre a deles.

Em segundo lugar, a obrigação é mais abrangente do que o contrato. As orientações de implementação da ENISA de 2024, constantes do Anexo IV do Regulamento de Execução (UE) 2024/2690 da Comissão, estabelecem a prática esperada: manter um registo de fornecedores TIC, classificá-los por criticidade, avaliar cada um quanto ao risco para as suas operações e para os dados que tratam, e renovar a avaliação com uma cadência definida. O Anexo IV nomeia explicitamente "os fornecedores dos fornecedores" como estando no âmbito, que é onde a maioria das equipas descobre que o seu registo de fornecedores não é realmente um registo, mas uma lista de contratos com um autocolante.

Se está a analisar isto do lado do procurement, a tradução prática é: todos os fornecedores com acesso lógico aos seus dados de produção têm de ser enumerados, classificados, monitorizados e substituíveis. "Substituíveis" é a parte que quebra a maioria dos arranjos existentes.

## O plano de dados SaaS de quatro camadas que a maioria das equipas esquece de desenhar

Sente-se com um responsável de procurement e percorra o que acontece quando o produto de um fornecedor de cópias de segurança escreve um único registo. O plano de dados honesto tem este aspeto, de cima para baixo:

1. A **aplicação do fornecedor**. O código que ingere os seus dados, toma decisões de encaminhamento e aplica lógica de negócio. Corre na infraestrutura do fornecedor. Mantida, corrigida e monitorizada pelo fornecedor.
2. A **nuvem do fornecedor**. A região do hiperscaler ou o centro de dados próprio do fornecedor onde a aplicação corre. Volumes de armazenamento, rede, IAM. Frequentemente um hiperscaler com o qual o fornecedor tem um acordo de subprocessador.
3. A **custódia de chaves do fornecedor**. As chaves de encriptação que protegem os dados em repouso na nuvem do fornecedor. Na maioria dos acordos SaaS, é o fornecedor quem as detém. "Chaves geridas pelo cliente" está por vezes disponível como opção de nível superior; nesses arranjos, as chaves continuam num KMS de hiperscaler que o IAM do fornecedor pode invocar.
4. Os **subprocessadores do fornecedor**. Os serviços de terceiros que o fornecedor utiliza (CDN, observabilidade, faturação, ferramentas de suporte ao cliente) que podem transitar ou armazenar os seus dados, ou metadados deles derivados.

Cada uma dessas quatro camadas é uma entrada no seu registo de fornecedores do Article 21(2)(d). Cada uma tem o seu próprio historial de incidentes, o seu próprio raio de impacto de violação, a sua própria superfície de negociação contratual. Quando renova com o fornecedor SaaS, renova as quatro implicitamente, porque o contrato do fornecedor SaaS é o único que consegue negociar.

O incidente Blackbaud foi uma violação de camada 2 (nuvem do fornecedor) que se propagou através da camada 1 (aplicação do fornecedor) e foi visível para todos os clientes por causa da camada 3 (custódia de chaves do fornecedor, neste caso chaves do lado do servidor sem separação por inquilino na base de dados afetada). Os subprocessadores da Blackbaud não foram o vetor de violação, mas os clientes ficaram a saber de três deles que não tinham enumerado.

## Blackbaud, custódia de chaves estilo Druva e o padrão de cascata

Três detalhes dos registos SEC da Blackbaud são os que importam para uma leitura NIS2.

Em primeiro lugar, a Blackbaud detinha as chaves de encriptação dos dados dos clientes, incluindo o ambiente de cópia de segurança que foi o alvo da violação. As chaves geridas pelo cliente não estavam disponíveis. Na litigância SEC pós-incidente, isto foi caracterizado como uma lacuna de controlo, não uma violação, porque os contratos da Blackbaud o permitiam. A perspetiva do NIS2 sobre o mesmo arranjo, ao abrigo do Article 21(2)(d), é mais exigente, porque o cliente não consegue avaliar de forma significativa o risco de um controlo sobre o qual não tem visibilidade.

Em segundo lugar, a violação afetou dados de cópia de segurança mais antigos do que a base de dados em produção. Organizações clientes cujos dados em produção tinham sido eliminados dos sistemas primários da Blackbaud ainda tinham dados expostos através do ambiente de cópia de segurança. Este é o padrão de cascata: um comprometimento de fornecedor alcança dados históricos que o cliente julgava já fora do âmbito.

Em terceiro lugar, mais de 13 000 organizações clientes receberam notificações de violação. Muitas eram pequenas organizações sem fins lucrativos e escolas sem capacidade operacional para responder, sem runbook de DR, sem segundo fornecedor de cópias de segurança para onde falhar. O incidente do fornecedor tornou-se, nesse sentido, o incidente delas.

Para uma cópia de segurança SaaS moderna ao estilo Druva, a arquitetura é melhor em alguns aspetos (a separação de chaves por inquilino é mais comum, BYOK está disponível em níveis superiores), mas o plano de dados de quatro camadas é o mesmo. A aplicação do fornecedor, a nuvem do fornecedor (tipicamente AWS), a custódia de chaves (por vezes do fornecedor, por vezes BYOK no KMS do cliente, por vezes híbrida), os subprocessadores. Uma violação em qualquer camada atinge todos os clientes simultaneamente, porque os dados de todos os clientes estão do mesmo lado da fronteira.

Este é o argumento estrutural. Não é uma depreciação da Druva. A Druva opera com maior rigor do que a Blackbaud operava. O argumento é que a estrutura de qualquer produto de cópia de segurança concebido para SaaS torna as violações de camada 2 e camada 3 uma obrigação ao abrigo do 21(2)(d) que o cliente não consegue cumprir de forma significativa.

## O auto-alojamento colapsa três das quatro camadas

A Rediacc é construída de forma diferente. A arquitetura completa está documentada na [página de Arquitetura](/pt/docs/architecture), mas a forma relevante para a cadeia de abastecimento são dois binários que comunicam via SSH:

- `rdc` corre na estação de trabalho do operador. Lê um ficheiro de configuração JSON simples (em `~/.config/rediacc/`), liga-se às máquinas próprias do operador via SSH e despacha comandos.
- `renet` corre no servidor próprio do operador, com root, e gere imagens de disco encriptadas com LUKS2, daemons Docker isolados e o proxy inverso.

O operador nunca inicia sessão na infraestrutura da Rediacc-empresa para executar uma cópia de segurança, restauro ou fork. Não existe nuvem da Rediacc-empresa no plano de dados. A credencial LUKS2 do repositório é armazenada no ficheiro de configuração local do operador (modo `0600`), nunca no servidor, nunca enviada para a Rediacc. O plano de dados tem este aspeto:

1. **Estação de trabalho do operador.** Corre `rdc`. Detém a credencial LUKS2.
2. **Servidor próprio do operador.** Corre `renet`. Detém os repositórios encriptados com LUKS2.
3. **Destino de cópia de segurança próprio do operador.** Qualquer armazenamento compatível com rclone (S3, B2, OneDrive, MinIO local). Recebe volumes encriptados.

Não existe camada 4. A Rediacc-empresa não é subprocessadora para nenhum operador que não tenha optado pelo experimental [adaptador Cloud](/pt/docs/architecture). Para operadores auto-alojados, a relação com a Rediacc-empresa é uma licença de software, não um acordo de processamento de dados.

Este é o argumento do plano de dados, e é o argumento certo para liderar numa conversa sobre registo de fornecedores. Um concorrente SaaS pode oferecer chaves geridas pelo cliente (e a maioria dos modernos oferece). Um concorrente SaaS não pode oferecer "não somos um subprocessador."

O segundo ponto, depois de o argumento do plano de dados ter impacto, é a custódia de chaves. Com a Rediacc, a credencial LUKS2 está no ficheiro de configuração do operador, ponto final. Não existe escrow de chaves, nenhum serviço de recuperação que a Rediacc-empresa possa executar se o operador perder a credencial. Esta é também a arquitetura recomendada para o [armazenamento de configuração zero-knowledge](/pt/docs/config-storage), onde a chave de encriptação é derivada do lado do cliente a partir de uma extensão PRF de passkey e o servidor armazena blobs opacos. O servidor não consegue ler as chaves SSH, as credenciais LUKS2, os endereços IP ou qualquer configuração em texto simples. A rotação do token de acesso não confere ao servidor leitura retroativa.

Para o Article 21(2)(h) (encriptação), isto é relevante. Para o Article 21(2)(d) (cadeia de abastecimento), é mais relevante, porque elimina o último caminho de acesso lógico da Rediacc-empresa aos dados do operador.

## O que o auto-alojamento não colapsa

O auto-alojamento desloca a lista de fornecedores, não a elimina. Três aspetos sobre os quais um auditor continuará a perguntar:

**1. Continua a ter fornecedores, apenas diferentes.** O fornecedor de hardware (Hetzner, Hostinger, OVH, o seu colocation, o seu próprio bare metal). O hipervisor (KVM, VMware). O sistema operativo (Debian, Ubuntu, RHEL). O registo de contentores (Docker Hub, GHCR, o seu registo privado). As imagens base que os seus serviços utilizam. Cada um desses é uma entrada do Article 21(2)(d). O auto-alojamento desloca a lista de fornecedores, não a elimina.

**2. A Rediacc ainda não tem ISO 27001, SOC 2 ou BSI C5.** Estes estão no roadmap, não em mãos. Para uma equipa de procurement que usa certificações como mecanismo de filtragem, isto é uma fricção real. O contra-argumento defensável é o que este artigo tem vindo a avançar: o argumento do plano de dados significa que a maior parte do que essas certificações atestam (controlos de segurança da nuvem do fornecedor, gestão de acessos de pessoal do fornecedor, gestão de subprocessadores do fornecedor) não está no âmbito, porque a Rediacc-empresa não está no plano de dados. Esse argumento tem de ser apresentado com cuidado e de forma defensável, não como substituto de certificações quando as certificações são o que o comprador necessita.

**3. A camada GRC ainda é sua.** A Rediacc fornece ao operador um registo de auditoria com encadeamento de hash de mais de 70 eventos (`rdc audit verify` valida a cadeia de ponta a ponta). Não fornece um registo de fornecedores, uma estrutura de controlos ou um fluxo de trabalho de recolha de evidências. Esses continuam a vir da Drata, Vanta, OneTrust ou de um dos intervenientes europeus. O artigo complementar sobre [o custo real](/pt/blog/nis2-the-real-bill) aborda em detalhe a estrutura de custos dessa complementaridade.

## O DPA que já não tem de negociar

Para tornar isto concreto, aqui está uma linha de registo "antes vs depois" de uma conversa real de procurement, anonimizada. O comprador é uma empresa alemã de manufatura com 280 colaboradores, classificada como "entidade importante" do Annex II. A entrada original do registo de fornecedores para cópias de segurança tinha este aspeto:

| Campo | Antes |
|---|---|
| Fornecedor | Acme Backup SaaS |
| Nível | Crítico |
| Dados tratados | Base de dados de produção, PII de clientes, registos financeiros |
| Subprocessadores | AWS (eu-central-1), Datadog, Stripe, Zendesk |
| Estado contratual | DPA assinado em 2023, SCCs anexadas, calendário de medidas revisto pela última vez em jan 2025 |
| Custódia de chaves | Gerida pelo fornecedor (opção BYOK não disponível no nível atual) |
| Plano de saída | "O fornecedor compromete-se a fornecer exportação de dados em CSV no prazo de 30 dias após a rescisão" |
| Última avaliação | 2025-Q1, lacuna identificada na custódia de chaves, adiada para a renovação |

Após migrar para a Rediacc no Hetzner:

| Campo | Depois |
|---|---|
| Fornecedores | (1) Rediacc OÜ, licença de software; (2) Hetzner, IaaS |
| Nível | (1) Não crítico (sem plano de dados); (2) Crítico (plano de dados, mas controlado pelo cliente) |
| Dados tratados | (1) Nenhum; (2) Volumes encriptados, cliente detém as chaves |
| Subprocessadores | (1) Nenhum para auto-alojado; (2) Apenas internos da Hetzner, listados no DPA deles |
| Estado contratual | (1) Licença de software, não é necessário DPA; (2) DPA Hetzner + SCCs já em vigor |
| Custódia de chaves | Cliente (credencial LUKS2 na configuração do operador, não no servidor) |
| Plano de saída | "rdc repo backup pull a partir de qualquer destino compatível com rclone. Os volumes são encriptados com LUKS2; o operador detém a credencial." |
| Última avaliação | (2) abrangida pela revisão IaaS existente |

Duas entradas de registo em vez de uma. A entrada de nível crítico é para o fornecedor IaaS, onde o comprador já tinha um DPA em vigor e um plano de saída testado, porque IaaS é uma relação que a maioria das equipas sabe gerir. A entrada Rediacc é não crítica porque é uma licença de software, não um processador de dados.

Esta é a razão estrutural pela qual um CISO acaba por querer menos dependências SaaS no plano de dados, mesmo que o custo de procurement pareça semelhante numa folha de cálculo. A entrada do registo não tem a mesma forma.

## Lista de verificação de procurement

Para qualquer fornecedor que afirme "NIS2-ready" num ciclo de vendas de 2026, seis perguntas:

**1. Onde está a chave de encriptação dos nossos dados em repouso?** Se a resposta for "no nosso HSM" ou "no KMS do nosso cliente que podemos invocar via IAM," o fornecedor está na sua cadeia de custódia de chaves. Se for "no seu ficheiro de configuração local, nunca na nossa infraestrutura," não está.

**2. Quem na sua empresa consegue tecnicamente ler os nossos dados, ignorando os termos legais?** Não "quem está autorizado a" mas "quem poderia, se quisesse e o registo de auditoria estivesse desativado." Se a resposta for diferente de zero, essa é a sua população para uma avaliação de risco interno.

**3. O restauro é testado contra um clone de produção real, ou contra dados de teste sintéticos?** O Article 21(2)(c) e (e) lidos em conjunto exigem que a cópia de segurança efetivamente restaure. Um fornecedor que só valida contra dados sintéticos não está a validar a recuperação, está a validar a integridade do ficheiro de cópia de segurança. (Para mais informações, veja o artigo complementar sobre [avaliação contínua de eficácia](/pt/blog/nis2-effectiveness-without-theatre).)

**4. O seu registo de auditoria regista o tipo de ator, humano ou agente, por detrás de cada ação?** A atividade de agentes de IA é a categoria de registo de auditoria de crescimento mais rápido. Um registo de auditoria de 2026 que não distingue humano de agente vai parecer uma lacuna em 2027.

**5. Liste todos os subprocessadores com acesso lógico aos nossos dados, incluindo metadados.** "Acesso lógico" é a expressão certa. "Acesso lógico incluindo metadados" é a melhor, porque o acesso exclusivo a metadados é o que os subprocessadores de faturação, observabilidade e suporte ao cliente tipicamente têm, e é suficiente para vazar estrutura sensível mesmo quando o payload está encriptado.

**6. Qual é o seu plano de saída se for adquirido por um comprador não europeu em 2027?** O quadro de adequação do RGPD, o Cloud Act e o FISA 702 são todos alvos em movimento. A afirmação de residência de dados de um fornecedor hoje não é uma garantia daqui a três anos. A questão do comprador é o que acontece ao plano de dados se a propriedade do fornecedor mudar.

Um fornecedor que responde de forma limpa a seis em seis é invulgar. Um fornecedor que responde a quatro em seis e reconhece abertamente os outros dois é mais credível do que um que responde com confiança a todos os seis. O sinal de credibilidade é a disposição para nomear o que não está resolvido.

## O que isto significa para o próximo ciclo de renovação

Se está a entrar numa renovação de cópia de segurança ou DR nos próximos doze meses e o Article 21(2)(d) está na scorecard de procurement, três medidas concretas:

1. Desenhe o plano de dados de quatro camadas do seu fornecedor atual num quadro branco. Se não conseguir nomear o terceiro subprocessador, tem um problema de completude do registo que é anterior ao NIS2 e a renovação é o momento certo para o resolver.
2. Execute a lista de verificação com as seis perguntas acima contra o seu fornecedor atual. Envie as respostas ao seu DPO e ao seu auditor e pergunte se as lacunas são aceites. Se as lacunas incluírem a camada 3 (custódia de chaves) ou a camada 4 (subprocessadores que não enumerou), esse é o ponto de pressão.
3. Veja como seria um registo de fornecedores alternativo com um plano de controlo auto-alojado. Compare as entradas do registo, não os custos de licença. Os custos de licença são semelhantes dentro de um fator de dois; as entradas do registo têm formas diferentes. (O artigo complementar sobre [o custo estrutural da pilha NIS2](/pt/blog/nis2-the-real-bill) percorre o que colapsa e o que permanece.)

Se somos a alternativa na sua lista curta, a oferta é concreta. Envie-nos o seu questionário de fornecedor. Preenchemo-lo contra uma instância em produção, com as nossas respostas reais às suas perguntas, incluindo as lacunas. Se quiser percorrer a arquitetura antes de enviar papelada, agendamos uma revisão de arquitetura de 30 minutos com o fundador. O caminho para uma entrada de registo defensável não é uma brochura vistosa. São as respostas, incluindo as desconfortáveis.

Quer o mapa por artigo do Rediacc? Consulte [NIS2 e DORA](/pt/docs/legal-nis2-dora). Precisa de um enquadramento mais amplo? Leia [Visão Geral de Conformidade](/pt/docs/legal-overview). Para residência de dados, consulte [Soberania de Dados](/pt/docs/legal-data-sovereignty). Para saber porque o self-hosting importa, consulte [On-Premise](/pt/docs/on-premise).
