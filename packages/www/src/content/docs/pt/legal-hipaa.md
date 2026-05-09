---
title: "Conformidade com a HIPAA"
description: "Como a arquitetura de encriptação e isolamento da Rediacc se mapeia com os requisitos de salvaguardas da HIPAA para a proteção de informações de saúde."
category: "Legal"
order: 3
language: pt
---

A Health Insurance Portability and Accountability Act (HIPAA) é uma lei federal dos Estados Unidos que estabelece normas para a proteção de informações sensíveis de saúde de doentes (PHI). Aplica-se a entidades cobertas (prestadores de cuidados de saúde, planos de saúde, câmaras de compensação de saúde) e aos seus associados comerciais.

Texto integral: [Public Law 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## Mapeamento das Salvaguardas

A HIPAA exige salvaguardas administrativas, técnicas e físicas. A tabela seguinte mapeia estas salvaguardas com as capacidades da Rediacc.

### Salvaguardas Técnicas

| Requisito | Referência HIPAA | Capacidade da Rediacc |
|-------------|----------------|-------------------|
| Controlo de acesso | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Autenticação por chave SSH. Tokens de API com vinculação de IP e restrições de âmbito. O isolamento do daemon Docker por repositório impede o acesso entre repositórios. |
| Controlos de auditoria | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Mais de 70 tipos de eventos cobrindo autenticação, tokens de API, operações de configuração, licenciamento e operações em máquinas (ciclo de vida de repositórios, backup, sincronização, terminal). Rastreio por utilizador e por equipa. Exportação via painel de administração, página de atividade do portal ou CLI `rdc audit`. |
| Controlos de integridade | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Os snapshots CoW preservam os dados originais antes das modificações. `rdc repo validate` verifica a integridade do repositório e o estado do backup (contentor LUKS, consistência do sistema de ficheiros, configuração). |
| Encriptação em repouso | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Encriptação LUKS2 AES-256 em todos os volumes de repositório. As credenciais são armazenadas apenas na configuração local do operador, nunca no servidor. O arquivo de configuração utiliza encriptação AES-256-GCM de conhecimento zero com derivação de chave dividida. Nem o servidor consegue desencriptar as configurações armazenadas. |
| Segurança de transmissão | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Todas as operações remotas utilizam SSH. O transporte de backup é encriptado de ponta a ponta. Nenhuma transferência de dados sem encriptação. |

### Salvaguardas Administrativas

| Requisito | Capacidade da Rediacc |
|-------------|-------------------|
| Gestão do acesso dos colaboradores | Tokens de API com permissões de âmbito limitado. Controlo de acesso por equipa. Revogação automática do token na remoção da equipa. |
| Procedimentos de incidentes de segurança | Os registos de auditoria fornecem uma trilha forense de todas as operações. O isolamento por repositório limita o raio de explosão. |
| Planeamento de contingência | `rdc repo backup push/pull` suporta backup encriptado para múltiplos destinos. Os snapshots CoW permitem recuperação instantânea. |

### Salvaguardas Físicas

| Requisito | Capacidade da Rediacc |
|-------------|-------------------|
| Controlos de acesso às instalações | Self-hosted: a sua organização controla a segurança física dos seus servidores. Sem dependência de centros de dados de terceiros para operações essenciais. |
| Segurança das estações de trabalho | O LUKS encripta todos os dados em repouso. Os repositórios não montados são blobs encriptados no disco, ilegíveis sem as credenciais do operador. |

## Acordo de Associado Comercial (BAA)

Uma vez que a Rediacc é software self-hosted que funciona na sua infraestrutura, não processa, armazena nem transmite PHI através dos sistemas da Rediacc (a empresa). O requisito típico de BAA aplica-se ao seu fornecedor de infraestrutura (fornecedor de nuvem ou instalação de colocation), não à Rediacc.

A Rediacc opera como uma ferramenta de software nos seus servidores, à semelhança de um sistema operativo ou de um motor de base de dados. Não tem acesso aos seus dados. O arquivo de configuração opcional sincroniza blobs encriptados através dos servidores da Rediacc, mas o seu design de conhecimento zero significa que o servidor não consegue desencriptar o conteúdo. Armazena apenas texto cifrado opaco.

## Ambientes de Desenvolvimento com PHI

Ao clonar ambientes de produção que contêm PHI para fins de desenvolvimento, utilize o hook de ciclo de vida `up()` do Rediaccfile para executar scripts de sanitização que:

- Eliminam PHI das tabelas da base de dados
- Substituem identificadores de doentes por dados sintéticos
- Removem tokens de sessão e chaves de API

Os programadores obtêm infraestrutura semelhante à de produção com dados desidentificados, satisfazendo o padrão de necessidade mínima da HIPAA.
