---
title: Modelo de Segurança
description: Quem pode ver o quê no armazenamento de configuração, como as chaves são delimitadas, o que os agentes e o MCP remoto podem alcançar e o que é recuperável.
category: Guides
tags:
  - security
  - account
subcategory: account
order: 14
language: pt
sourceHash: "dd01eccb85dd4e7c"
sourceCommit: "467795d4f62f378389037e0027cac2676125b437"
---

# Modelo de Segurança

Esta página indica o que o armazenamento de configuração protege, que chave abre o quê e o que cada tipo de chamador consegue alcançar. Para os passos de configuração, consulte [Armazenamento de Configuração](/pt/docs/config-storage); para sessões e tokens, consulte [Segurança da Conta e API](/pt/docs/account-security).

## Quem pode ver o quê

![Hierarquia de chaves](/img/security-key-hierarchy.svg)

*O servidor guarda as chaves da camada SDK e da frase secreta da organização; só os titulares de slots de chave abrem a CEK.*

![Quem pode ver o conteúdo da configuração](/img/security-who-can-see.svg)

*O que cada tipo de atacante consegue ler.*

Uma configuração armazenada é encriptada em três camadas. A camada do SDK e a camada da frase-passe da organização são geridas pelo servidor. A camada intermédia é a chave de encriptação de conteúdo (CEK), que só os titulares de um slot de chave conseguem desbloquear: um segredo de slot guardado no dispositivo combina-se com um segredo guardado no servidor, e nenhuma das metades a abre sozinha.

| O atacante possui | Vê o conteúdo da configuração | Motivo |
|---|---|---|
| Apenas uma cópia da base de dados | Não | Os blobs de configuração ficam no armazenamento de objetos, não na base de dados |
| A base de dados e o armazenamento de objetos | Não | A camada da frase-passe da organização precisa do segredo do Worker, e a camada da CEK de um segredo de slot |
| Um comprometimento total do servidor | Não sem um segredo de slot | As camadas do servidor caem, mas a CEK continua protegida pela saída PRF da passkey ou pelo kit de recuperação de 160 bits, e nenhum dos dois se adivinha |
| O dispositivo de um membro removido | O que já foi obtido | As versões posteriores continuam fechadas após uma rotação da CEK |
| Um URL de agente divulgado | Uma configuração, como esse utilizador | Veja [Agentes e MCP remoto](#agentes-e-mcp-remoto) |

O servidor continua a ver metadados (ids de configuração, equipas, versões, carimbos de data/hora, tamanhos de blob) e pode recusar, atrasar ou apagar pedidos. Um operador que sirva código malicioso do portal pode ler chaves no browser. Cada blob está ligado ao seu armazenamento, configuração, equipa e versão, pelo que o servidor não consegue trocar nem editar um sem ser detetado, e o CLI recusa uma versão mais antiga do que uma que já tenha visto.

## Âmbito das chaves

![Escopo das chaves](/img/security-key-scope.svg)

*Um armazenamento e uma CEK por organização; as equipes são controle de acesso, não chaves separadas.*

- Um armazenamento de configuração por organização e uma CEK por armazenamento. As equipas são controlo de acesso no servidor, não isolamento criptográfico: um kit de recuperação ou um slot de chave abre a CEK de toda a organização.
- Os slots de chave são únicos por armazenamento, utilizador e método, por isso há um kit de recuperação por utilizador e por organização. Um utilizador em duas organizações tem dois kits, e não existe kit de equipa.
- Um segredo de máquina é um por máquina e por organização e serve para inscrever uma máquina headless.
- Cada configuração tem a sua própria chave de conteúdo sob a CEK. Uma concessão de agente transporta a chave de conteúdo de uma única configuração, pelo que nenhuma outra configuração da organização se abre com ela.
- A política de autorização de cada configuração é um registo separado, sob uma chave derivada da CEK e do ponteiro do registo. Quem tem a chave de uma política só abre os registos desse ponteiro.

## Agentes e MCP remoto

![Fluxo do MCP remoto](/img/security-remote-mcp-flow.svg)

*Uma chamada do cliente passa pelo Worker MCP até o executor da organização; uma concessão expirada leva o cliente a autorizar de novo.*

Uma concessão de agente é o tipo de titular de chaves por trás de um URL de MCP remoto. Transporta a chave de conteúdo de uma configuração e as chaves de política da configuração de equipa da própria concessão e da configuração ao nível da organização, nunca a CEK, de modo que um agente lê exatamente o que a sua pessoa lê.

- **Duração.** Um URL dura 7 dias por predefinição e 30 no máximo, depois expira ou é revogado. Uma concessão expirada é recusada e o cliente volta a autorizar.
- **Âmbito.** Uma concessão alcança uma configuração e pertence a uma região (eu, us ou asia). Um URL apresentado a outra região é recusado, indicando a região correta, e nunca é reencaminhado. As instalações on-premise têm uma única região.
- **Política.** Um agente só atua onde a adesão explícita de uma pessoa e o teto da política o permitem ambos. O teto é a política da organização restringida pela política da equipa. Um agente não pode editar a política, ler valores secretos nem alargar a sua própria concessão.
- **Raio de impacto.** Um URL divulgado atua como esse utilizador na sua única configuração até expirar ou ser revogado. Não abre nada fora do executor alojado da sua região.

A saída das ferramentas chega ao fornecedor de modelos que o utilizador liga, o qual a Rediacc não escolhe.

### On-premise

Não há Cloudflare no caminho. Os segredos do Worker da cloud passam a variáveis de ambiente ou configuração no anfitrião do cliente, pelo que o acesso ao anfitrião substitui a fronteira do segredo do Worker na tabela acima, e as chamadas de ferramentas correm no executor daemon do próprio cliente.

## Política

![Teto da política](/img/security-policy-ceiling.svg)

*Um agente só age onde a aceitação humana e a interseção das políticas da organização e da equipe permitem.*

A política é um registo separado, selado por entrada de configuração com dados autenticados que ligam armazenamento, configuração, equipa, versão e geração da chave. O servidor não o consegue ler, e um registo repetido ou trocado falha na sua etiqueta de integridade. Os registos de política da versão 1 são recusados.

Apenas um proprietário ou administrador da organização escreve a política da organização, e apenas um administrador de equipa (ou um proprietário ou administrador) escreve a política dessa equipa. Uma escrita exige 2FA e uma sessão elevada, e uma passkey associada quando o armazenamento exige passkeys. Cada membro e cada executor que o serve lê-a. Uma chave que a organização bloqueia é ignorada na política de uma equipa.

## O que é recuperável

![Caminhos de desbloqueio e recuperação](/img/security-unlock-recovery.svg)

*Todo método de desbloqueio termina na CEK, e o kit de recuperação é obrigatório.*

| Situação | Recuperação |
|---|---|
| Passkey perdida | Desbloqueie com o kit de recuperação e depois inscreva uma nova passkey |
| Kit perdido | Gere-o de novo a partir de uma passkey funcional; a impressão antiga deixa de servir |
| Ambos perdidos | Um proprietário ou administrador volta a adicionar o membro através da transferência de membro |
| O último titular de chave perde ambos | Irrecuperável, e por isso se aconselha um segundo titular de chave |
| Membro removido | Os seus slots e tokens desaparecem de imediato; uma rotação da CEK fecha as versões posteriores a uma chave que tenha guardado |
| Rotação da CEK | Reembrulha a CEK sob uma nova geração e invalida todos os kits de recuperação |

O servidor recusa qualquer eliminação de slot, remoção de membro ou saída de membro que deixasse menos de dois titulares de chave e nenhum slot de recuperação. Cada membro recebe um kit de recuperação obrigatório na inscrição, e guardá-lo é responsabilidade do membro.
