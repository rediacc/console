---
title: "Conformidade com PCI DSS"
description: "Como o Rediacc mapeia os requisitos PCI DSS para proteger dados de cartões de pagamento com encriptação, segmentação de rede e controlo de acesso."
category: "Legal"
order: 6
language: pt
---

A Payment Card Industry Data Security Standard (PCI DSS) é obrigatória para qualquer organização que armazene, processe ou transmita dados de titulares de cartões. A versão atual é a PCI DSS v4.0.1.

Referência: [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## Mapeamento de Requisitos

| Requisito PCI DSS | Descrição | Capacidade Rediacc |
|---------------------|-------------|-------------------|
| **Req 1**, Controlos de segurança de rede | Instalar e manter controlos de segurança de rede | Regras iptables por repositório bloqueiam todo o tráfego entre repositórios. Cada repositório tem a sua própria sub-rede de loopback IP (/26). |
| **Req 2**, Configurações seguras | Aplicar configurações seguras a todos os componentes do sistema | Os hooks de ciclo de vida do Rediaccfile impõem configurações deterministas e reprodutíveis. Sem credenciais predefinidas. As chaves LUKS são geradas pelo operador. |
| **Req 3**, Proteger dados armazenados | Proteger dados armazenados de titulares com encriptação | Encriptação LUKS2 AES-256 em todos os volumes de repositório. A encriptação é obrigatória, não opcional. Eliminação criptográfica via destruição da chave LUKS. |
| **Req 4**, Proteger dados em trânsito | Proteger dados de titulares com criptografia forte durante a transmissão | Todas as operações remotas via SSH. Transporte de cópias de segurança encriptado de ponta a ponta. Sem caminhos de dados não encriptados. |
| **Req 6**, Desenvolvimento seguro | Desenvolver e manter sistemas e software seguros | A clonagem CoW cria ambientes de teste isolados sem expor dados de titulares de produção a redes de desenvolvimento. Fluxo de trabalho fork-test-promote. |
| **Req 7**, Restringir acessos | Restringir o acesso a componentes do sistema e dados de titulares por necessidade de negócio | Sockets do daemon Docker por repositório. O acesso a um repositório não concede acesso a outro. Autenticação baseada em chave SSH. |
| **Req 8**, Identificar utilizadores e autenticar | Identificar utilizadores e autenticar o acesso a componentes do sistema | Autenticação por chave SSH. Tokens de API com vinculação de IP e permissões com âmbito. Autenticação de dois fatores (TOTP). |
| **Req 9**, Restringir acesso físico | Restringir o acesso físico a dados de titulares | Self-hosted: a segurança física está sob o seu controlo direto. A encriptação LUKS torna as unidades roubadas ilegíveis. |
| **Req 10**, Registar e monitorizar | Registar e monitorizar todos os acessos a componentes do sistema e dados de titulares | Mais de 70 tipos de evento (autenticação, tokens de API, configuração, licenciamento, operações de máquina). Painel de administração e portal com filtragem por utilizador, equipa, tipo e data. CLI `rdc audit` para exportação programática. As operações de máquina também ficam nos registos do sistema para defesa em profundidade. |
| **Req 12**, Políticas organizacionais | Apoiar a segurança da informação com políticas e programas organizacionais | O self-hosted elimina o âmbito de processadores terceiros (Req 12.8). Reduz o limite de conformidade PCI DSS. |

## Segmentação de Rede

O PCI DSS dá grande ênfase à segmentação de rede para isolar o ambiente de dados de titulares (CDE). O Rediacc proporciona isso por arquitetura:

- Cada repositório corre no seu próprio daemon Docker em `/var/run/rediacc/docker-<networkId>.sock`
- Os repositórios têm sub-redes de loopback IP isoladas (127.0.x.x/26, 61 IPs utilizáveis por rede)
- Regras iptables impostas pelo renet bloqueiam todo o tráfego entre daemons
- Contentores de repositórios diferentes não conseguem comunicar ao nível da rede

Um repositório de processamento de pagamentos fica isolado ao nível da rede de todas as outras aplicações na mesma máquina. Não é necessária nenhuma configuração adicional de firewall.

## Redução do Âmbito

O Rediacc self-hosted reduz o âmbito de conformidade PCI DSS:

- Sem fornecedor de cloud de terceiros no fluxo de dados de titulares
- Sem fornecedor SaaS a avaliar ao abrigo do Req 12.8 (prestadores de serviços terceiros)
- Os controlos de segurança física estão sob a sua gestão direta
- As chaves de encriptação são armazenadas apenas na configuração local do operador

## Casos de Aplicação

A fraca segmentação de rede e a ausência de encriptação levaram a ações de aplicação PCI DSS com custos elevados:

- Heartland Payment Systems (2008): os atacantes moveram-se lateralmente por 48 bases de dados devido à fraca segmentação de rede, expondo 130 milhões de números de cartões. [O custo total ultrapassou 200 milhões de dólares.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): os atacantes pivotaram da rede de um fornecedor de AVAC para os sistemas de ponto de venda devido à arquitetura de rede plana, capturando 40 milhões de cartões de pagamento. [Acordo por 18,5 milhões de dólares com 47 procuradores-gerais estaduais.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
