---
title: "Conformidade com SOC 2"
description: "Como o Rediacc mapeia os Critérios de Serviço de Confiança SOC 2 para segurança, disponibilidade e confidencialidade."
category: "Legal"
order: 2
language: pt
sourceHash: "ebdae97034aa3cce"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

O SOC 2 (System and Organization Controls 2) é um referencial desenvolvido pelo American Institute of Certified Public Accountants (AICPA) para avaliar os controlos de uma organização relacionados com segurança, disponibilidade, integridade de processamento, confidencialidade e privacidade.

Referência: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Mapeamento dos Critérios de Serviço de Confiança

| Princípio de Confiança | Critério | Capacidade Rediacc |
|----------------|----------|-------------------|
| **Segurança** (CC6) | Controlos de acesso lógico, encriptação | Encriptação LUKS2 AES-256 em repouso. Credenciais armazenadas apenas na configuração local do operador (`~/.config/rediacc/`), nunca no servidor. Acesso baseado em chave SSH. Daemons Docker isolados por repositório. |
| **Disponibilidade** (A1) | Recuperação e resiliência do sistema | `rdc repo push/pull` com cópias cifradas offsite para SSH, S3, B2, Azure ou GDrive. Snapshots CoW para reversão instantânea. Atualizações baseadas em fork para alterações sem tempo de inatividade. |
| **Integridade de Processamento** (PI1) | Processamento preciso e completo | Os hooks de ciclo de vida deterministas do Rediaccfile (`up`/`down`) garantem implementações consistentes. `rdc repo validate` verifica a integridade do repositório e o estado das cópias de segurança após paragens inesperadas ou operações de backup. |
| **Confidencialidade** (C1) | Proteção de dados contra acesso não autorizado | Encriptação por repositório com credenciais LUKS únicas. Isolamento de rede via iptables, daemons Docker separados e sub-redes de loopback IP. Contentores de repositórios diferentes não se conseguem ver mutuamente. O repositório de configuração de conhecimento zero encripta as configurações do lado do cliente antes do envio. O servidor armazena apenas blobs opacos que não consegue desencriptar. |
| **Privacidade** (P1-P8) | Tratamento de dados pessoais | Self-hosted: sem saída de dados durante as operações. Registo de auditoria para todos os acessos a dados. Gestão de chaves de encriptação sob controlo do cliente. O repositório de configuração usa derivação de chave dividida (passkey PRF + segredo do servidor) para que nenhuma das partes sozinha consiga aceder aos dados. |

## Registo de Auditoria

O Rediacc regista mais de 70 tipos de evento que cobrem:

- **Autenticação**: login, logout, alterações de palavra-passe, ativação/desativação de 2FA, revogação de sessão
- **Autorização**: criação/revogação de tokens de API, alterações de função, adesão a equipas
- **Configuração**: push/pull do repositório de configuração, gestão de membros, falhas de acesso (incompatibilidade de IP, SDK recusado)
- **Licenciamento**: emissão de licenças de repositório, rastreamento de slots de máquina, alterações de subscrição
- **Operações de máquina**: criar/iniciar/parar/eliminar repositório, fork, push/pull de cópias de segurança, sincronização de ficheiros, sessões de terminal

Estes registos são acessíveis através do painel de administração (com filtragem por utilizador, equipa e data), da página de atividade do portal (com filtragem por tipo e data com âmbito de organização para administradores) e da CLI `rdc audit` para exportação programática. As operações de máquina também ficam registadas nos registos do sistema para defesa em profundidade.

## Gestão de Alterações

O fluxo de trabalho baseado em fork suporta gestão de alterações controlada:

1. Fazer fork de um repositório de produção (`rdc repo fork`)
2. Aplicar e testar alterações no fork
3. Validar o fork de forma independente
4. Promover o fork para produção (`rdc repo takeover`)

Cada passo é registado com marcas de data e hora e identificação do ator.

## Controlo de Acesso

- **Acesso a máquinas**: apenas autenticação por chave SSH. Sem SSH por palavra-passe.
- **Tokens de API**: permissões com âmbito, vinculação de IP opcional, revogação automática ao sair da equipa.
- **Isolamento de repositório**: cada repositório tem o seu próprio socket do daemon Docker. O acesso a um repositório não concede acesso a outro na mesma máquina.
- **Tokens do repositório de configuração**: tokens rotativos de uso único com vinculação de IP no primeiro uso, expiração automática em 24 horas e janela de tolerância de 3 pedidos para concorrência. O acesso dos membros é gerido via troca de chaves X25519 com revogação imediata.
