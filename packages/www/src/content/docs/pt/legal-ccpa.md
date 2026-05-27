---
title: "Conformidade com a CCPA"
description: "Como o modelo self-hosted da Rediacc responde aos requisitos da California Consumer Privacy Act relativos à proteção de dados dos consumidores."
category: "Legal"
order: 4
language: pt
sourceHash: "949159b302cf6ab9"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

A California Consumer Privacy Act (CCPA) é uma lei estadual que confere aos consumidores da Califórnia direitos sobre as suas informações pessoais, incluindo o direito de saber que dados são recolhidos, o direito de os eliminar e o direito de recusar a sua venda.

Referência: [California Attorney General, CCPA](https://oag.ca.gov/privacy/ccpa)

## Mapeamento dos Direitos dos Consumidores

A CCPA centra-se nos direitos dos consumidores relativos às informações pessoais. A Rediacc é uma ferramenta self-hosted implementada na sua infraestrutura, não um serviço de terceiros que recolhe ou vende dados de consumidores. A tabela seguinte mapeia os direitos da CCPA e a forma como a Rediacc apoia a conformidade da sua organização.

| Direito da CCPA | Requisito | Capacidade da Rediacc |
|-----------|-------------|-------------------|
| Direito de acesso (1798.100) | Divulgar categorias e finalidades dos dados recolhidos | Os registos de auditoria acompanham todas as operações com dados. Self-hosted: a sua organização mantém total visibilidade sobre os dados existentes em cada repositório. |
| Direito de eliminação (1798.105) | Eliminar informações pessoais do consumidor mediante pedido | `rdc repo delete` apaga criptograficamente o volume encriptado com LUKS. A eliminação de um fork remove as cópias clonadas. |
| Direito de recusa (1798.120) | Não vender nem partilhar informações pessoais | Arquitetura self-hosted: sem transferências de dados para a Rediacc ou para terceiros. Os dados permanecem nos seus servidores. A sincronização do arquivo de configuração utiliza encriptação de conhecimento zero. Nem o servidor de sincronização consegue ler os dados. |
| Segurança de dados (1798.150) | Implementar medidas de segurança razoáveis | Encriptação LUKS2 AES-256, isolamento de rede, acesso exclusivo por SSH, daemons Docker isolados, registo de auditoria. O arquivo de configuração utiliza encriptação de três camadas com derivação de chave dividida e tokens de utilização única rotativos. |

## Estatuto de Prestador de Serviços

A Rediacc, enquanto software, não acede, processa nem armazena dados de consumidores. A sua equipa de TI opera a Rediacc na sua própria infraestrutura. Nenhum dado flui para a empresa Rediacc. As implicações são as seguintes:

- A Rediacc não é um "prestador de serviços" ao abrigo da CCPA (não processa dados em seu nome)
- Não é necessário qualquer acordo de processamento de dados com a Rediacc para o produto self-hosted
- As suas obrigações ao abrigo da CCPA são entre a sua organização e os seus consumidores

## Inventário de Dados

Cada repositório da Rediacc é uma unidade discreta e encriptada de dados com um GUID único. É possível inventariar com exatidão que dados existem e onde:

- `rdc machine query --name <machine> --repositories` lista todos os repositórios numa máquina com tamanho e estado de montagem
- Cada repositório está isolado ao nível do sistema de ficheiros, da rede e dos contentores
- As relações de fork são acompanhadas, permitindo identificar todas as cópias de um conjunto de dados

A CCPA exige o mapeamento de dados. O modelo de repositórios da Rediacc disponibiliza-o: um GUID por conjunto de dados, enumerável por máquina, com a linhagem dos forks registada.
