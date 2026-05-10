---
title: "Soberania de Dados"
description: "Como a arquitetura self-hosted da Rediacc satisfaz os requisitos de residência e soberania de dados nas diferentes jurisdições globais."
category: "Legal"
order: 7
language: pt
---

Muitos países exigem que os dados pessoais dos seus cidadãos sejam armazenados e processados dentro das fronteiras nacionais. A arquitetura self-hosted da Rediacc satisfaz estes requisitos por conceção: os dados permanecem na sua máquina, no seu centro de dados, na sua jurisdição. Nenhum dado sai da máquina durante a clonagem e nenhum SaaS de terceiros processa os seus dados.

## Por que o Self-Hosted Resolve a Soberania de Dados

As transferências transfronteiriças de dados constituem o problema de conformidade mais complexo na computação em nuvem. Cada jurisdição tem regras, decisões de adequação e mecanismos de transferência distintos. O self-hosted elimina por completo esta categoria de problemas:

- **Sem transferências transfronteiriças**: a clonagem CoW (`cp --reflink=always`) duplica os dados na mesma máquina
- **Sem processador terceiro**: a Rediacc funciona na sua infraestrutura, não nos servidores da Rediacc
- **Sem necessidade de avaliação de adequação**: os dados nunca saem da jurisdição, pelo que as regras de transferência não se aplicam
- **Sem cláusulas contratuais-tipo**: não existe fluxo internacional de dados a regular

## Cobertura por Jurisdição

### União Europeia

O [RGPD](https://gdpr-info.eu/) restringe as transferências de dados pessoais para fora da UE/EEE, salvo se o destino oferecer proteção adequada. O acórdão Schrems II invalidou o EU-US Privacy Shield e a [coima de 1,2 mil milhões de euros aplicada à Meta](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) demonstrou o custo de errar nas transferências transfronteiriças.

A Rediacc self-hosted implementada na UE mantém todos os dados dentro da UE. Não é necessário qualquer mecanismo de transferência. Consulte [Conformidade com o RGPD](/pt/docs/legal-gdpr) para o mapeamento por artigo.

### China

A [Lei de Proteção de Informações Pessoais (PIPL)](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) exige que os dados pessoais dos cidadãos chineses sejam armazenados na China. As transferências transfronteiriças requerem avaliações de segurança pela Administração do Ciberespaço da China (CAC). A Rediacc self-hosted em infraestrutura chinesa evita inteiramente as avaliações de segurança da CAC.

### Brasil

A [Lei Geral de Proteção de Dados (LGPD)](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) exige medidas de segurança adequadas e restringe as transferências internacionais. O self-hosted no Brasil elimina as preocupações com transferências e satisfaz o requisito de medidas técnicas do Art. 46 através da encriptação LUKS2 e do isolamento de rede.

### Índia

A [Lei de Proteção de Dados Pessoais Digitais (DPDP Act, 2023)](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023) restringe transferências para países que não constem de uma lista aprovada pelo governo. O self-hosted em infraestrutura indiana significa que não existe transferência, independentemente dos países que venham a ser bloqueados. Os setores governamental e de defesa da Índia preferem fortemente soluções on-premises.

### Turquia

A [KVKK (Lei n.º 6698)](https://kvkk.gov.tr/en/) restringe as transferências internacionais com requisitos de adequação complexos. A Turquia não consta da lista de adequação da UE, pelo que as transferências transfronteiriças requerem aprovação explícita. O self-hosted na Turquia elimina este problema na totalidade.

### Coreia do Sul

A [Lei de Proteção de Informações Pessoais (PIPA)](https://www.pipc.go.kr/eng/index.do) é uma das mais rigorosas a nível mundial e exige explicitamente a encriptação dos dados pessoais durante o armazenamento e a transmissão. O LUKS2 AES-256 satisfaz diretamente este requisito. As coimas podem ascender a 3% das receitas.

### Japão

A [Lei de Proteção de Informações Pessoais (APPI)](https://www.ppc.go.jp/en/legal/) restringe as transferências transfronteiriças, salvo se o país destinatário oferecer proteção adequada. O self-hosted no Japão evita as restrições de transferência e alinha-se com a preferência cultural do mercado por soluções on-premises.

### Austrália

A [Privacy Act 1988](https://www.legislation.gov.au/C2004A03712/latest/text) responsabiliza a entidade divulgadora pelo tratamento de dados por um destinatário no estrangeiro (APP 8). O self-hosted elimina inteiramente esta responsabilidade. A encriptação LUKS2 e o isolamento de rede constituem "medidas razoáveis" concretas ao abrigo do APP 11.

### Emirados Árabes Unidos

O [Decreto-Lei Federal n.º 45/2021](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws) exige medidas de segurança adequadas e restringe as transferências transfronteiriças. Os setores governamental e financeiro dos EAU preferem fortemente implementações on-premises.

### Arábia Saudita

A [Lei de Proteção de Dados Pessoais (PDPL)](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) exige que os dados pessoais dos residentes sauditas sejam armazenados e processados na Arábia Saudita. O self-hosted satisfaz diretamente este rigoroso requisito de localização.

### Singapura

A [Lei de Proteção de Dados Pessoais (PDPA)](https://sso.agc.gov.sg/Act/PDPA2012) exige segurança razoável e restringe as transferências transfronteiriças. O self-hosted em Singapura, um importante hub de dados na região APAC, satisfaz a conformidade regional para operações na ASEAN.

### Rússia

A [Lei Federal 242-FZ](https://pd.rkn.gov.ru/) exige que os dados pessoais dos cidadãos russos sejam armazenados em servidores localizados na Rússia. As infrações podem resultar no bloqueio de sítios web. O self-hosted em solo russo garante a conformidade por arquitetura.

## O Padrão

Em todas as jurisdições, a equação de conformidade é a mesma:

| Propriedade | Cloud/SaaS | Rediacc Self-Hosted |
|----------|-----------|-------------------|
| Localização dos dados | Centros de dados do fornecedor (podem abranger fronteiras) | A sua máquina, a sua jurisdição |
| Mecanismo de transferência necessário | Sim (SCCs, adequação, consentimento) | Não (não ocorre transferência) |
| Responsabilidade por processador terceiro | Sim | Não |
| Controlo da encriptação | Chaves geridas pelo fornecedor | As suas credenciais LUKS, armazenadas localmente |
| Clonagem/dados de staging | Podem cruzar fronteiras ou sair do seu controlo | CoW na mesma máquina, mesma jurisdição |

## Serviço Alojado: Residência Regional de Dados

Para utilizadores do serviço Rediacc alojado (não self-hosted), a residência de dados é aplicada através de infraestrutura regional. Estão disponíveis três regiões: UE (Frankfurt), EUA (Virgínia) e Ásia-Pacífico (Tóquio). Cada região opera bases de dados e armazenamento independentes, sem fluxos de dados entre regiões. O correio eletrónico transacional é enviado via AWS SES; a UE e os EUA utilizam endpoints regionais dedicados, e a Ásia-Pacífico utiliza o endpoint da UE (eu-central-1). A região da UE aplica controlo jurisdicional ao armazenamento R2. Consulte [Regiões de Dados](/pt/docs/data-regions) para a análise técnica completa.
