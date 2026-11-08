---
title: "Regiões de Dados"
description: "Onde os seus dados são armazenados e como funciona a residência regional de dados."
category: "Concepts"
tags:
  - compliance
  - account
subcategory: platform
order: 3
language: pt
sourceHash: "c73d7300b75b57c4"
sourceCommit: "c69b28b08afd5e7602afd1e8efe90785e6e36938"
---

Quando cria uma conta Rediacc, escolhe uma região de dados. Todos os seus dados permanecem nessa região. Esta escolha é permanente e não pode ser alterada após o registo. Nenhum caminho de migração existe. Escolha com base em onde os seus dados precisam residir legalmente, não em onde estão os seus servidores atualmente.

## Regiões Disponíveis

| Região | Localização | Domínio |
|---|---|---|
| **Europa (EU)** | Frankfurt, Alemanha | `eu.rediacc.cloud` |
| **Estados Unidos (US)** | Virgínia, EUA | `us.rediacc.cloud` |
| **Ásia-Pacífico** | Tóquio, Japão | `asia.rediacc.cloud` |

O produto funciona nestes domínios `rediacc.cloud`. Toda a documentação e o website de marketing estão em `www.rediacc.com`, que o encaminha para a região certa a partir do seletor de região.

No registo, o seletor sugere uma região com base na sua localização, que pode confirmar ou alterar. No início de sessão, encaminha-o para a sua região após uma breve contagem decrescente que pode cancelar ou alterar. Se a sua empresa tem uma implementação própria, a opção «Cliente Enterprise?» leva-o até lá a partir do domínio de email da empresa. Só o domínio é enviado, nunca o endereço completo.

## O Que Fica na Sua Região

Estes tipos de dados são armazenados e processados exclusivamente na região escolhida:

- **Dados da conta**: e-mail, nome, organização, membros de equipa
- **Registos de faturação e subscrição**: plano, ativações, emissões de licenças
- **Blobs de configuração cifrados**: cifrados pelo cliente com conhecimento zero. O servidor não consegue descifrá-los.
- **E-mails transacionais**: reposições de palavra-passe, links mágicos, notificações. Enviados a partir de um endpoint de e-mail regional.

## O Que É Global

Estes elementos não são específicos de nenhuma região:

- **Artefactos de lançamento da CLI**: binários públicos alojados numa CDN global
- **Website de marketing e documentação**: `www.rediacc.com`, servido globalmente a partir de localizações de edge
- **Processamento de pagamentos Stripe**: gerido pela própria infraestrutura da Stripe ao abrigo do seu acordo de processamento de dados

## Infraestrutura Regional

| Componente | EU | US | Ásia |
|---|---|---|---|
| Base de dados (D1) | Europa de Leste (EEUR) | América do Norte Oriental (ENAM) | Ásia-Pacífico (APAC) |
| Armazenamento de configurações (R2) | Jurisdição EU | US | Ásia-Pacífico |
| E-mail (SES) | Frankfurt (eu-central-1) | Virgínia (us-east-1) | Frankfurt (eu-central-1) |

Cada região executa infraestrutura independente. Não existem consultas entre regiões nem fluxos de dados entre regiões.

## Garantias de Dados da EU

Escute: se está sujeito a requisitos de residência de dados europeus, a região EU adiciona garantias específicas:

- **Base de dados D1**: executa na Europa de Leste (dica de localização EEUR)
- **Armazenamento de configurações R2**: utiliza imposição jurisdicional da EU (garantia contratual, não apenas uma dica de localização)
- **E-mail**: enviado a partir de Frankfurt (eu-central-1)
- **Decisão de adequação mútua EU-Japão (2019)**: permite fluxos de dados conformes para a infraestrutura da região Ásia

Para o mapeamento detalhado do RGPD, consulte [Conformidade com o RGPD](/pt/docs/legal-gdpr).

## Cifração de Conhecimento Zero

Os blobs de configuração armazenados no R2 são cifrados pelo lado do cliente antes do envio, utilizando troca de chaves X25519 e AES-256-GCM. O servidor guarda apenas o texto cifrado. Nem a Rediacc nem qualquer fornecedor de infraestrutura consegue ler os seus dados de configuração.

As chaves são derivadas de uma chave de acesso com extensão PRF. O servidor armazena um segredo do lado do servidor que participa na derivação de chaves, mas nem a chave de acesso por si só nem o segredo do servidor por si só conseguem decifrar os dados.

Para detalhes sobre a arquitetura de cifração, consulte [Armazenamento de Configurações](/pt/docs/config-storage).

## Como Escolher

- **Escolha a região mais próxima de si** para menor latência.
- **Escolha a região exigida pela sua organização** por motivos de conformidade. Se a sua empresa obriga à residência de dados na EU, escolha EU.
- **A escolha é permanente.** Não é possível mover a sua conta para uma região diferente após o registo.

## Para Responsáveis de Conformidade

Propriedades técnicas da arquitetura regional:

- **Bases de dados separadas por região**: cada região tem a sua própria base de dados Cloudflare D1. Sem consultas entre regiões.
- **Armazenamento separado por região**: cada região tem o seu próprio bucket R2. A EU utiliza imposição jurisdicional.
- **Entrega de e-mail via AWS SES**: os e-mails transacionais são enviados via AWS SES. A EU e os EUA utilizam endpoints regionais dedicados; a Ásia-Pacífico encaminha através do endpoint da EU (eu-central-1).
- **Um utilizador, uma região**: uma conta de utilizador existe numa única região. Não pode abranger múltiplas regiões.
- **Isolamento de webhooks**: os eventos de webhook da Stripe são recebidos por todos os workers regionais, mas apenas processados pela região que detém o registo do cliente.
- **Cifração de configurações com conhecimento zero**: o servidor não consegue ler dados de configuração. As chaves de cifração nunca saem do dispositivo cliente.

Para uma visão mais ampla da conformidade com a soberania dos dados, consulte [Soberania de Dados](/pt/docs/legal-data-sovereignty).
