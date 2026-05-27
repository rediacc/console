---
title: "NIS2 e DORA"
description: "Como a Rediacc responde aos requisitos da Diretiva NIS2 de cibersegurança da UE e do DORA em matéria de resiliência operacional digital."
category: "Legal"
order: 8
language: pt
sourceHash: "a2078388f7ae1906"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

A NIS2 e o DORA são regulamentos da UE que impõem requisitos de cibersegurança e resiliência operacional a organizações de infraestruturas críticas e do setor financeiro. Ambos entraram em vigor em 2025 e aplicam-se amplamente às indústrias da UE.

## Diretiva NIS2

A Diretiva sobre Segurança das Redes e da Informação 2 (NIS2) estabelece requisitos de cibersegurança para entidades "essenciais" e "importantes" em setores como a energia, os transportes, a saúde, a infraestrutura digital e a administração pública.

Texto integral: [Diretiva (UE) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### Mapeamento dos Requisitos NIS2

| Requisito NIS2 | Capacidade da Rediacc |
|-----------------|-------------------|
| Medidas de gestão de risco (Art. 21) | Encriptação LUKS2 em repouso, isolamento de rede por repositório, acesso exclusivo por SSH, registo de auditoria (mais de 70 tipos de eventos incluindo operações em máquinas) |
| Tratamento de incidentes (Art. 21(2)(b)) | Mais de 70 tipos de eventos (autenticação, tokens, configuração, licenciamento, operações em máquinas) fornecem trilha forense. O isolamento por repositório limita o raio de explosão. |
| Continuidade de negócio (Art. 21(2)(c)) | `rdc repo push/pull` com backup encriptado para múltiplos destinos. Snapshots CoW para reversão instantânea. |
| Segurança da cadeia de fornecimento (Art. 21(2)(d)) | O self-hosted elimina o risco da cadeia de fornecimento SaaS. Nenhum fornecedor de nuvem terceiro processa os seus dados. |
| Segurança de rede (Art. 21(2)(e)) | Daemons Docker por repositório, regras iptables, isolamento IP de loopback (sub-redes /26). |
| Encriptação (Art. 21(2)(h)) | Encriptação obrigatória LUKS2 AES-256. Arquivo de configuração de conhecimento zero com AES-256-GCM. |
| Controlo de acessos (Art. 21(2)(i)) | Autenticação por chave SSH, tokens de API de âmbito limitado com vinculação de IP, autenticação de dois fatores (TOTP). |
| Notificação de incidentes, aviso prévio de 24h (Art. 23) | O registo de auditoria permite a deteção e delimitação rápidas de incidentes. |

### Risco da Cadeia de Fornecimento

A segurança da cadeia de fornecimento é uma preocupação central da NIS2 (Art. 21(2)(d)). As organizações devem avaliar e gerir os riscos dos seus fornecedores e prestadores de serviços TIC.

A Rediacc self-hosted elimina a maior superfície de ataque da cadeia de fornecimento: nenhum SaaS terceiro gere os seus dados, nenhum fornecedor de nuvem tem acesso lógico à sua infraestrutura e nenhum ambiente de multi-inquilino cria exposição à postura de segurança de outros clientes. As violações de fornecedores SaaS causaram danos em cascata em milhares de organizações. [O ataque de ransomware de 2020 à Blackbaud expôs dados de mais de 13.000 organizações clientes, com um custo de 49,5 milhões de dólares em acordos.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (Digital Operational Resilience Act)

O DORA estabelece requisitos de gestão de risco TIC, notificação de incidentes, testes de resiliência e gestão de risco de terceiros para o setor financeiro da UE. Aplica-se a bancos, companhias de seguros, empresas de investimento, prestadores de serviços de criptoativos e aos seus fornecedores TIC terceiros críticos.

Texto integral: [Regulamento (UE) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### Mapeamento dos Requisitos DORA

| Requisito DORA | Capacidade da Rediacc |
|-----------------|-------------------|
| Quadro de gestão de risco TIC (Art. 6) | A encriptação, o isolamento, o registo de auditoria e o backup formam a camada de controlos técnicos. |
| Proteção e prevenção (Art. 9) | Encriptação LUKS2 AES-256 em repouso. O isolamento de rede impede o movimento lateral. Acesso exclusivo por SSH. |
| Deteção (Art. 10) | Mais de 70 tipos de eventos incluindo operações em máquinas (ciclo de vida de repositórios, backup, sincronização, terminal). Painel de administração e portal com filtragem por utilizador e por equipa. As operações em máquinas também constam dos registos do sistema para defesa em profundidade. |
| Resposta e recuperação (Art. 11) | Snapshots CoW para reversão instantânea. `rdc repo push/pull` para recuperação com múltiplos destinos. Testes de recuperação de desastres baseados em forks. |
| Risco de terceiros TIC (Art. 28-30) | O self-hosted elimina inteiramente a classificação de "fornecedor TIC terceiro crítico". |
| Testes de resiliência operacional digital (Art. 24-27) | A clonagem CoW permite testes de penetração orientados por ameaças em ambientes semelhantes à produção sem exposição de dados. Clonar, testar, destruir. |

### Risco de Fornecedores TIC Terceiros

Os requisitos mais exigentes do DORA dizem respeito à gestão de fornecedores TIC terceiros críticos (Art. 28-30). As instituições financeiras têm de manter registos de fornecedores TIC, realizar avaliações de risco, negociar disposições contratuais específicas e planear estratégias de saída.

A Rediacc self-hosted evita tudo isto. Nenhum fornecedor TIC terceiro a registar, avaliar ou monitorizar. A instituição financeira controla diretamente a sua própria infraestrutura.

### Testes de Resiliência

O DORA impõe testes de resiliência operacional digital, incluindo testes de penetração orientados por ameaças (TLPT) para grandes instituições (Art. 26). A clonagem CoW trata diretamente desta exigência:

1. Criar um fork do ambiente de produção (instantâneo, na mesma máquina, sem transferência de dados)
2. Executar testes de penetração contra o fork
3. Destruir o fork após a conclusão

A produção nunca é tocada, mas o ambiente de teste é uma réplica exata. Nenhum dado sai da máquina.
