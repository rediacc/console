---
title: "Conformidade com a ISO 27001"
description: "Como a Rediacc se mapeia com os controlos de segurança da informação da ISO 27001 relativos a encriptação, gestão de acessos e segurança operacional."
category: "Legal"
order: 5
language: pt
sourceHash: "52709a22c0b38178"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Pois bem. A ISO/IEC 27001:2022 é a norma internacional para sistemas de gestão de segurança da informação. Publicada pela ISO/IEC, é um documento extenso que lista controlos de encriptação, gestão de acessos, resposta a incidentes e dezenas de domínios de segurança. Muito provavelmente já tem conhecimento disto. Portanto, vou ser direto: a Rediacc não aborda todos os controlos da norma, e não vamos fingir que aborda. O que se segue é um mapeamento honesto de onde a Rediacc se encaixa. A versão atual é ISO/IEC 27001:2022.

Referência: [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Ora bem, a Rediacc é um componente da camada de controlos técnicos dentro de um ISMS. A tabela seguinte mapeia as capacidades da Rediacc com os domínios de controlo relevantes do Anexo A.

## Mapeamento dos Controlos do Anexo A

| Domínio de Controlo | Controlo | Capacidade da Rediacc |
|---------------|---------|-------------------|
| **A.8**, Gestão de ativos | A.8.1 Inventário de ativos | Cada repositório é um ativo discreto e identificável com um GUID único. `rdc machine query --name <machine> --repositories` lista todos os repositórios com tamanho, estado de montagem e contagem de contentores. |
| **A.8**, Gestão de ativos | A.8.24 Utilização de criptografia | Encriptação obrigatória LUKS2 AES-256 em todos os repositórios. Gestão de chaves: credenciais armazenadas apenas na configuração local do operador, nunca no servidor. |
| **A.9**, Controlo de acessos | A.9.2 Gestão de acessos de utilizadores | Autenticação por chave SSH. Tokens de API com vinculação de IP, âmbito por equipa e revogação automática na remoção da equipa. Suporte para autenticação de dois fatores (TOTP). |
| **A.10**, Criptografia | A.10.1 Controlos criptográficos | LUKS2 com parâmetros de chave configuráveis. Credenciais de encriptação por repositório. Todo o transporte remoto via SSH. O arquivo de configuração implementa encriptação de conhecimento zero: AES-256-GCM com derivação de chave HKDF, troca de chaves de membros X25519 e chaves SDK com janela temporal para revogação instantânea. |
| **A.12**, Segurança operacional | A.12.3 Backup | `rdc repo push/pull` com armazenamento externo encriptado para múltiplos destinos (SSH, S3, B2, Azure, GDrive). Snapshots CoW para recuperação pontual. `rdc repo validate` verifica o estado do backup e a integridade do repositório. |
| **A.12**, Segurança operacional | A.12.4 Registo e monitorização | Mais de 70 tipos de eventos (autenticação, tokens de API, configuração, licenciamento, operações em máquinas). Monitorização do estado das máquinas via `rdc machine query`. Monitorização do estado dos contentores e dos recursos. |
| **A.13**, Segurança das comunicações | A.13.1 Gestão da segurança de rede | Isolamento do daemon Docker por repositório. Regras iptables bloqueiam o tráfego entre repositórios. Sub-redes IP de loopback (/26) por repositório. Proxy inverso com terminação TLS para acesso externo. |
| **A.14**, Desenvolvimento de sistemas | A.14.2 Segurança no desenvolvimento | Os ambientes de desenvolvimento baseados em forks garantem paridade com a produção sem exposição dos dados de produção. Os hooks de ciclo de vida do Rediaccfile permitem a sanitização automatizada de dados em ambientes clonados. |

## Gestão de Ativos

O modelo de repositórios da Rediacc suporta naturalmente os requisitos de inventário de ativos:

- Cada repositório tem um GUID único atribuído na criação
- Os repositórios são enumeráveis por máquina (`rdc machine query --repositories`)
- O estado de encriptação, o estado de montagem, a contagem de contentores e o uso de disco de cada repositório são visíveis
- As relações de fork acompanham a linhagem dos ambientes clonados

## Gestão de Alterações

O fluxo de trabalho fork-testar-promover alinha-se com os requisitos de gestão de alterações da ISO 27001:

1. **Fork**: criar uma cópia isolada do ambiente de produção
2. **Testar**: aplicar e validar as alterações no fork
3. **Promover**: utilizar `rdc repo takeover` para colocar o fork em produção
4. **Auditoria**: todas as operações são registadas com timestamps e identificação do ator

## Melhoria Contínua

- A exportação do registo de auditoria suporta revisões de segurança periódicas
- As verificações do estado das máquinas (`rdc machine query --system`) suportam a monitorização operacional
- `rdc repo validate` verifica o estado do backup após cada operação
