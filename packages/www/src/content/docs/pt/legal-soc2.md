---
title: "Conformidade com SOC 2"
description: "A verdade sobre SOC 2: os auditores querem evidências de que os seus controlos funcionam. O Rediacc fornece os registos, o rasto de gestão de alterações e tudo o resto que vão pedir."
category: "Legal"
order: 2
language: pt
sourceHash: "27d2366f84e21d8c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Sei o que é SOC 2 porque já estive em reuniões de auditoria. Os auditores usam o referencial AICPA para verificar se os seus controlos realmente funcionam, não apenas se afirma que funcionam. Cinco Critérios de Serviço de Confiança: segurança, disponibilidade, integridade de processamento, confidencialidade e privacidade.

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

Portanto, o Rediacc regista mais de 70 tipos de evento diferentes. Ações de utilizador, alterações de sistema, atualizações de configuração, modificações de controlo de acesso, eventos de segurança, operações de fork, registos de auditoria. Sei que parece muito, mas os auditores realmente querem ver isto.

- **Autenticação**: login, logout, alterações de palavra-passe, ativação/desativação de 2FA, revogação de sessão
- **Autorização**: criação/revogação de tokens de API, alterações de função, adesão a equipas
- **Configuração**: push/pull do repositório de configuração, gestão de membros, falhas de acesso (incompatibilidade de IP, SDK recusado)
- **Licenciamento**: emissão de licenças de repositório, rastreamento de slots de máquina, alterações de subscrição
- **Operações de máquina**: criar/iniciar/parar/eliminar repositório, fork, push/pull de cópias de segurança, sincronização de ficheiros, sessões de terminal

Há três formas de aceder a estes registos. Painel de administração com filtragem por utilizador, equipa e data. Página de atividade do portal para administradores de organização, com filtragem por tipo e data. Ou a CLI `rdc audit` para exportação programática. Redirecione para as suas ferramentas, integre em qualquer lugar. As operações de máquina também são registadas nos registos do sistema, de modo que tem defesa em profundidade.

## Gestão de Alterações

Os forks tornam a gestão de alterações auditável. Faz fork da produção, obtém uma cópia do estado em direto. Teste. Reveja. Promova ou descarte. Cada passo com marca de tempo e ligado a uma pessoa. É isto que os auditores querem ver: sem alterações anónimas.

1. Fazer fork de um repositório de produção (`rdc repo fork`)
2. Aplicar e testar alterações no fork
3. Validar o fork de forma independente
4. Promover o fork para produção (`rdc repo takeover`)

Cada passo: registado. Com marca de tempo. Atribuído a uma pessoa. Sem momentos de "Não sei quem alterou isto".

## Controlo de Acesso

- **Acesso a máquinas**: apenas autenticação por chave SSH. Sem SSH por palavra-passe.
- **Tokens de API**: permissões com âmbito, vinculação de IP opcional, revogação automática ao sair da equipa.
- **Isolamento de repositório**: cada repositório tem o seu próprio socket do daemon Docker. O acesso a um repositório não concede acesso a outro na mesma máquina.
- **Tokens do repositório de configuração**: tokens rotativos de uso único com vinculação de IP no primeiro uso, expiração automática em 24 horas e janela de tolerância de 3 pedidos para concorrência. O acesso dos membros é gerido via troca de chaves X25519 com revogação imediata.
