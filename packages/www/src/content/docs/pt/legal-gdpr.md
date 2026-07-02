---
title: "Conformidade com o RGPD"
description: "Como a arquitetura self-hosted da Rediacc se mapeia com os requisitos do RGPD em matéria de proteção de dados e privacidade."
category: "Legal"
order: 1
language: pt
sourceHash: "76d2b3a911e0d14c"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

O Regulamento Geral sobre a Proteção de Dados (RGPD) é a lei de proteção de dados da União Europeia, em vigor desde maio de 2018. Rege a forma como as organizações recolhem, processam e armazenam dados pessoais de pessoas singulares na UE.

Texto integral: [Regulamento (UE) 2016/679](https://gdpr-info.eu/)

## Mapeamento por Artigo

A tabela seguinte mapeia artigos específicos do RGPD com as capacidades técnicas da Rediacc.

| Artigo | Requisito | Capacidade da Rediacc |
|---------|-------------|-------------------|
| [Art. 5](https://gdpr-info.eu/art-5-gdpr/), Princípios | Minimização de dados, integridade, confidencialidade | Os clones CoW (`cp --reflink=always`) duplicam os dados na mesma máquina sem transferência de rede. O LUKS2 AES-256 encripta todos os dados em repouso. |
| [Art. 17](https://gdpr-info.eu/art-17-gdpr/), Direito ao apagamento | Apagar dados pessoais mediante pedido | `rdc repo delete` apaga criptograficamente o volume LUKS. A eliminação de um fork remove a cópia clonada na totalidade. |
| [Art. 25](https://gdpr-info.eu/art-25-gdpr/), Proteção de dados desde a conceção | Privacidade por defeito | A encriptação é obrigatória, não opcional. Cada repositório dispõe de um daemon Docker e de uma rede isolados. Não existe partilha de dados entre repositórios. O arquivo de configuração utiliza encriptação de conhecimento zero: as configurações são encriptadas do lado do cliente com AES-256-GCM antes do carregamento, pelo que o servidor não consegue ler nenhum dado em texto simples. |
| [Art. 28](https://gdpr-info.eu/art-28-gdpr/), Subcontratante | Obrigações de processamento de dados por terceiros | Self-hosted: a Rediacc funciona na sua infraestrutura. Nenhum dado sai da sua máquina durante operações de fork, clone ou backup. Nenhum componente SaaS processa dados pessoais. |
| [Art. 30](https://gdpr-info.eu/art-30-gdpr/), Registos das atividades de tratamento | Manter registos das atividades de processamento | O registo de auditoria acompanha mais de 70 tipos de eventos: autenticação, tokens de API, operações no arquivo de configuração, licenciamento e operações CLI em máquinas (ciclo de vida de repositórios, backup, sincronização, terminal). Exportação via painel de administração ou página de atividade do portal (exportação JSON disponível). |
| [Art. 32](https://gdpr-info.eu/art-32-gdpr/), Segurança do tratamento | Medidas técnicas adequadas | Encriptação LUKS2 AES-256 em repouso, isolamento de rede via iptables e daemons Docker separados, sub-redes IP de loopback (/26) por repositório. O arquivo de configuração utiliza encriptação de três camadas: chaves SDK com janela temporal, derivação de CEK com chave dividida (passkey e segredo do servidor) e encriptação com frase-passe da organização. |
| [Art. 33](https://gdpr-info.eu/art-33-gdpr/), Notificação de violação | Notificação em 72 horas com trilha forense | Os registos de auditoria fornecem uma trilha forense de todas as operações. A arquitetura self-hosted limita o raio de explosão a repositórios individuais. |

## Residência de Dados

Os clones CoW nunca saem da máquina de origem. O comando `rdc repo fork` cria uma cópia ao nível do sistema de ficheiros utilizando reflinks. Nenhum dado é transferido pela rede.

Para operações entre máquinas, `rdc repo push/pull` transfere dados via SSH. O destino do backup recebe volumes encriptados com LUKS que não podem ser lidos sem as credenciais do operador.

## Clonagem de Ambientes e Mascaramento de Dados

Ao clonar ambientes de produção para desenvolvimento ou testes, o hook de ciclo de vida `up()` do Rediaccfile executa scripts de sanitização após a criação de um fork: elimina dados pessoais das bases de dados, substitui endereços de correio eletrónico reais por endereços de teste, remove tokens de API e dados de sessão, e anonimiza ficheiros de registo. O ambiente de desenvolvimento obtém a estrutura de produção sem as identidades de produção, satisfazendo o princípio da minimização de dados ([Art. 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/)).

## Arquivo de Configuração de Conhecimento Zero

O arquivo de configuração opcional permite sincronizar configurações CLI entre dispositivos. Foi concebido de forma a que o servidor não tenha qualquer conhecimento do conteúdo das configurações:

- **Encriptação do lado do cliente**: as configurações são encriptadas com AES-256-GCM antes do carregamento. A chave de encriptação (CEK) é derivada de um segredo PRF de passkey e de um segredo guardado no servidor, utilizando HKDF com separação de domínio. Nenhuma das partes consegue derivar a chave sozinha.
- **O servidor vê apenas blobs opacos**: chaves SSH, credenciais, endereços IP, topologia de rede. Nada disto é visível para o servidor. Apenas os metadados (IDs de configuração, versões, timestamps) são armazenados em texto simples.
- **Acesso de membros via X25519**: quando um membro da equipa é adicionado, a CEK é encriptada com a sua chave pública X25519 e retransmitida pelo servidor. O servidor nunca vê a CEK em texto simples.
- **Revogação imediata**: a remoção de um membro elimina a CEK encapsulada e revoga os seus tokens. As configurações futuras utilizam novas épocas SDK inacessíveis ao membro removido.
- **Tokens rotativos**: a autenticação CLI utiliza tokens rotativos de utilização única (janela de tolerância de 3 pedidos), vinculados ao IP na primeira utilização, com expiração automática ao fim de 24 horas.

Mesmo uma comprometimento total do servidor não consegue expor o conteúdo das configurações. O servidor nunca possui a chave.

Para mais detalhes, consulte [Armazenamento de Configuração](/pt/docs/config-storage).

## Responsável pelo Tratamento e Subcontratante

Uma vez que a Rediacc é software self-hosted, a sua organização é simultaneamente responsável pelo tratamento e subcontratante. A Rediacc (a empresa) não acede, processa nem armazena os seus dados. Não é necessário qualquer acordo de processamento de dados com a Rediacc para o produto self-hosted, dado que nenhum dado pessoal flui para a infraestrutura da Rediacc.

O arquivo de configuração é o único componente que contacta os servidores da Rediacc (para sincronização), mas o seu design de conhecimento zero significa que o servidor armazena apenas blobs encriptados que não consegue desencriptar.
