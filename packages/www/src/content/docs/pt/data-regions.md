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
sourceHash: "9efeb1e2b1f9c8db"
sourceCommit: "c477e296238c19495f4a07ef6c5a62f15e942f90"
---

Quando cria uma conta Rediacc, escolhe uma região de dados. Todos os seus dados permanecem nessa região. Esta escolha é permanente e não pode ser alterada após o registo. Nenhum caminho de migração existe. Escolha com base em onde os seus dados precisam residir legalmente, não em onde estão os seus servidores atualmente.

## Regiões Disponíveis

| Região | Localização | Domínio |
|---|---|---|
| **Europa (EU)** | União Europeia | `eu.rediacc.cloud` |
| **Estados Unidos (US)** | Leste da América do Norte | `us.rediacc.cloud` |
| **Ásia-Pacífico** | Ásia-Pacífico | `asia.rediacc.cloud` |

A coluna de localização indica uma região da Cloudflare, não uma cidade com centro de dados. A Cloudflare não promete nenhuma cidade.

O produto funciona nestes domínios `rediacc.cloud`. Toda a documentação e o website de marketing estão em `www.rediacc.com`, que o encaminha para a região certa a partir do seletor de região.

No registo, o seletor sugere uma região com base na sua localização, que pode confirmar ou alterar. No início de sessão, encaminha-o para a sua região após uma breve contagem decrescente que pode cancelar ou alterar. Se a sua empresa tem uma implementação própria, a opção «Cliente Enterprise?» leva-o até lá a partir do seu e-mail profissional. Só o domínio é enviado para encontrar a região; o e-mail serve apenas para preencher previamente a página de início de sessão.

## O Que Fica na Sua Região

Estes tipos de dados são armazenados e processados na região que escolher, exceto o e-mail transacional da Ásia-Pacífico, que é enviado através do endpoint da UE (veja abaixo a infraestrutura regional para saber o que está garantido):

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
| Base de dados (D1) | Indicação Europa de Leste (EEUR) | Indicação Leste da América do Norte (ENAM) | Indicação Ásia-Pacífico (APAC) |
| Armazenamento de configurações (R2) | Jurisdição da UE (garantida) | Sem jurisdição (melhor esforço) | Sem jurisdição (melhor esforço) |
| E-mail (SES) | Frankfurt (eu-central-1) | Virgínia (us-east-1) | Frankfurt (eu-central-1) |

Apenas o armazenamento de configuração da UE fica sujeito a uma jurisdição garantida: a Cloudflare mantém dentro da UE os objetos R2 sob a jurisdição da UE. A colocação da base de dados D1 e o armazenamento de US e Ásia-Pacífico usam indicações de localização, aplicadas com o melhor esforço. A Cloudflare não garante que funcionem na região indicada.

Cada região executa infraestrutura independente. Não existem consultas entre regiões nem fluxos de dados entre regiões.

## Garantias de Dados da EU

Se está sujeito a requisitos europeus de residência de dados, a região EU oferece uma garantia firme e uma colocação de melhor esforço:

- **Base de dados D1**: colocada com a indicação de localização EEUR (Europa de Leste), de melhor esforço e sem garantia
- **Armazenamento de configuração R2**: sujeito à jurisdição da UE, que a Cloudflare garante (uma restrição firme, não apenas uma indicação de localização)
- **E-mail**: enviado a partir de Frankfurt (eu-central-1)

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
- **Armazenamento separado por região**: cada região tem o seu próprio bucket R2. Apenas o bucket da EU fica sujeito a uma jurisdição; US e Ásia-Pacífico são colocados com o melhor esforço.
- **Entrega de e-mail via AWS SES**: os e-mails transacionais são enviados via AWS SES. A EU e os EUA utilizam endpoints regionais dedicados; a Ásia-Pacífico encaminha através do endpoint da EU (eu-central-1).
- **Um utilizador, uma região**: uma conta de utilizador existe numa única região. Não pode abranger múltiplas regiões.
- **Isolamento de webhooks**: os eventos de webhook da Stripe são recebidos por todos os workers regionais, mas apenas processados pela região que detém o registo do cliente.
- **Cifração de configurações com conhecimento zero**: o servidor não consegue ler dados de configuração. As chaves de cifração nunca saem do dispositivo cliente.

Para uma visão mais ampla da conformidade com a soberania dos dados, consulte [Soberania de Dados](/pt/docs/legal-data-sovereignty).
