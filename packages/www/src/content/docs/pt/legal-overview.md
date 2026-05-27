---
title: "Visão Geral de Conformidade"
description: "Como a arquitetura self-hosted da Rediacc responde aos requisitos de conformidade em matéria de proteção de dados, privacidade e segurança."
category: "Legal"
order: 0
language: pt
sourceHash: "e20385eb9adfe180"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

A Rediacc funciona inteiramente na sua infraestrutura. Durante as operações de clonagem de ambientes, backup e implementação, os dados nunca saem da sua máquina. A sua organização mantém-se simultaneamente responsável pelo tratamento e subcontratante dos dados. Nenhum SaaS de terceiros gere os seus dados.

Esta secção mapeia as capacidades técnicas da Rediacc com os requisitos dos principais referenciais de conformidade. Cada página cobre um regulamento específico com referências ao nível do artigo para os textos jurídicos oficiais.

## Matriz de Conformidade

| Referencial | Âmbito | Principais Capacidades da Rediacc |
|-----------|-------|--------------------------|
| [RGPD](/pt/docs/legal-gdpr) | Proteção de dados e privacidade na UE | Clonagem CoW na mesma máquina, encriptação LUKS2, arquivo de configuração de conhecimento zero, registo de auditoria, direito ao apagamento via `rdc repo delete` |
| [SOC 2](/pt/docs/legal-soc2) | Critérios de serviços de confiança para organizações de serviços | Encriptação em repouso, sincronização de configuração de conhecimento zero, isolamento de rede, trilha de auditoria, backup e recuperação |
| [HIPAA](/pt/docs/legal-hipaa) | Proteção de informações de saúde nos EUA | Encriptação LUKS2, arquivo de configuração de conhecimento zero, acesso exclusivo por SSH, daemons Docker isolados, segurança de transmissão |
| [CCPA](/pt/docs/legal-ccpa) | Direitos de privacidade dos consumidores da Califórnia | Self-hosted (sem venda/partilha de dados), encriptação de conhecimento zero, eliminação encriptada, inventário de dados por repositório |
| [ISO 27001](/pt/docs/legal-iso27001) | Controlos de gestão de segurança da informação | Gestão de ativos, controlos criptográficos, arquivo de configuração de conhecimento zero, controlo de acessos, segurança operacional |
| [PCI DSS](/pt/docs/legal-pci-dss) | Proteção de dados de cartões de pagamento | Segmentação de rede por arquitetura, encriptação obrigatória, registo de auditoria, redução de âmbito via self-hosted |
| [NIS2 e DORA](/pt/docs/legal-nis2-dora) | Cibersegurança e resiliência financeira na UE | Eliminação do risco da cadeia de fornecimento, testes de resiliência via clonagem CoW, encriptação, deteção de incidentes |
| [Soberania de Dados](/pt/docs/legal-data-sovereignty) | Leis globais de residência de dados (PIPL, LGPD, KVKK, PIPA e outras) | Self-hosted = os dados nunca saem da sua jurisdição. Sem transferências transfronteiriças, sem avaliações de adequação |

## Fundamentos Arquitetónicos

Todos os referenciais de conformidade desta secção remetem para as mesmas propriedades técnicas:

- **Encriptação em repouso**: cada repositório é encriptado com LUKS2 AES-256. As credenciais são armazenadas apenas na configuração local do operador, nunca no servidor.
- **Isolamento de rede**: cada repositório dispõe do seu próprio daemon Docker, sub-rede IP de loopback (/26) e regras iptables. Os contentores de repositórios diferentes não conseguem comunicar entre si.
- **Clonagem copy-on-write**: `rdc repo fork` utiliza reflinks do sistema de ficheiros (`cp --reflink=always`). Os dados são duplicados na mesma máquina sem qualquer transferência de rede.
- **Registo de auditoria**: mais de 70 tipos de eventos cobrindo autenticação (início de sessão, 2FA, alterações de palavra-passe, revogação de sessão), ciclo de vida de tokens de API, operações no arquivo de configuração, atividade de subscrição/licenciamento e operações CLI em máquinas (ciclo de vida de repositórios, backup, sincronização, sessões de terminal). Acessível via painel de administração, página de atividade do portal (com filtragem por organização) e CLI `rdc audit`. As operações em máquinas são também registadas nos registos do sistema para defesa em profundidade.
- **Backup encriptado**: `rdc repo push/pull` transfere dados via SSH. O destino do backup recebe volumes encriptados com LUKS.
- **Arquivo de configuração de conhecimento zero**: sincronização de configuração encriptada opcional entre dispositivos. As configurações são encriptadas do lado do cliente com AES-256-GCM antes do carregamento. O servidor armazena apenas blobs opacos. O servidor não consegue ler chaves SSH, credenciais, endereços IP nem quaisquer dados de configuração em texto simples. A derivação de chaves utiliza a extensão PRF de passkey com HKDF e separação de domínio. O acesso dos membros é gerido via troca de chaves X25519 e a revogação é imediata.

Para mais detalhes sobre estas capacidades, consulte [Arquitetura](/pt/docs/architecture), [Repositórios](/pt/docs/repositories), [Armazenamento de Configuração](/pt/docs/config-storage) e [Segurança da Conta](/pt/docs/account-security).

## Por que é Importante

Os incumprimentos em matéria de conformidade são dispendiosos. Estes casos de execução envolveram problemas que a arquitetura da Rediacc impede estruturalmente:

| Incidente | Coima | O que correu mal |
|----------|------|----------------|
| [Meta: transferências de dados UE-EUA](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 1,2 mil milhões de EUR | Dados pessoais transferidos através de fronteiras sem salvaguardas adequadas. O self-hosted significa que não há transferência. |
| [Equifax: dados não encriptados](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 700 milhões de USD | 147 milhões de registos armazenados sem encriptação e com segmentação de rede deficiente. O LUKS2 é obrigatório, não opcional. |
| [Target: movimento lateral](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 18,5 milhões de USD | Os atacantes pivotaram de um fornecedor de AVAC para os sistemas de pagamento através de uma rede plana. O isolamento por repositório impede isto. |
| [Anthem: PHI não encriptado](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 16 milhões de USD | 79 milhões de registos de saúde armazenados sem encriptação. O LUKS2 AES-256 está sempre ativo. |
| [Blackbaud: violação em cascata de SaaS](https://www.sec.gov/newsroom/press-releases/2023-48) | 49,5 milhões de USD | Ransomware num fornecedor SaaS expôs dados de mais de 13.000 organizações clientes. O self-hosted significa que uma violação de fornecedor não consegue alcançar os seus dados. |
| [British Airways: segmentação deficiente](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 20 milhões de GBP | Atacantes injetaram código malicioso devido a controlos de rede inadequados. Os daemons Docker isolados e o iptables impedem o acesso lateral. |
| [Google: direito ao apagamento](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 50 milhões de EUR | Dificuldade em apagar integralmente dados em sistemas distribuídos. O apagamento criptográfico via destruição LUKS é instantâneo e completo. |

## Aviso Importante

Estas páginas descrevem as capacidades técnicas da Rediacc em relação aos requisitos de conformidade. A conformidade com qualquer regulamento exige políticas organizacionais, procedimentos, formação de pessoal e, potencialmente, auditorias por terceiros que ultrapassam o âmbito de qualquer ferramenta individual. Consulte a sua equipa jurídica e de conformidade para obter orientação específica para a sua organização.
