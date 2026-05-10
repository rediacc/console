---
title: "Resolução de Problemas"
description: "Soluções para problemas comuns com SSH, configuração, repositórios, serviços e Docker."
category: "Guides"
order: 10
language: pt
---

# Resolução de Problemas

Problemas comuns e as suas soluções. Em caso de dúvida, comece com `rdc doctor` para executar um diagnóstico abrangente.

## Falha na Ligação SSH

- Verifique se consegue ligar manualmente: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Execute `rdc config machine scan-keys -m server-1` para atualizar as chaves do servidor
- Confirme que a porta SSH está correta: `--port 22`
- Teste com um comando simples: `rdc term connect -m server-1 -c "hostname"`

## Incompatibilidade de Chave do Servidor

Se um servidor foi reinstalado ou as suas chaves SSH foram alteradas, verá "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

Isto obtém as chaves atualizadas e atualiza a sua configuração.

## Falha na Configuração da Máquina

- Certifique-se de que o utilizador SSH tem acesso sudo sem palavra-passe, ou configure `NOPASSWD` para os comandos necessários
- Verifique o espaço disponível em disco no servidor
- Execute com `--debug` para output detalhado: `rdc config machine setup --name server-1 --debug`

## Problemas de Configuração Específicos por Distribuição

Os cinco sistemas operativos de servidor oficialmente suportados (Ubuntu 24.04, Debian 13, Fedora 43, openSUSE Leap 16.0, Oracle Linux 10) têm políticas de segurança e gestores de pacotes diferentes. A maioria das configurações "simplesmente funciona"; os casos abaixo cobrem os que não funcionam.

### Negações SELinux (Fedora 43, Oracle Linux 10)

Ambos executam o SELinux em modo de aplicação estrita. O setup do rdc não instala uma política SELinux personalizada; o daemon docker por repositório executa no contexto padrão `container_t`. Se o setup falhar com negações AVC, verifique o registo de auditoria e identifique o domínio:

```bash
sudo ausearch -m AVC -ts recent | head -40
# Ou:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

Se uma negação apontar para o binário renet ou um caminho de ficheiro específico, a solução é quase sempre re-etiquetar (`restorecon -v /path`) em vez de desativar o SELinux. Como solução temporária enquanto investiga, `sudo setenforce 0` coloca o sistema em modo permissivo. Reative com `sudo setenforce 1` assim que confirmar que a re-etiquetagem é estável.

### Negações AppArmor (Ubuntu 24.04, openSUSE Leap 16.0)

Ambos executam o AppArmor por predefinição; o daemon docker por repositório usa o perfil de contentor padrão. Se um contentor dentro de um repositório estiver a ser bloqueado:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

O CRIU é o caso conhecido que aciona o AppArmor. O renet define automaticamente `security_opt: apparmor=unconfined` nos contentores com a etiqueta `rediacc.checkpoint=true`. Não deverá precisar de configurar perfis AppArmor para mais nada. Consulte as notas sobre CRIU em [Rules of Rediacc](/pt/docs/rules-of-rediacc).

### Assinaturas de erros do gestor de pacotes

| SO | Gestor de pacotes | Erro típico | Resolução |
|----|-------------------|-------------|-----------|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cache de borda do Cloudflare atrás da origem. Repita `apt-get update` após ~15s; a verificação de integridade passa na próxima tentativa. |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | Os metadados do repositório RPM em cache estão desatualizados. Execute `sudo dnf clean all && sudo dnf makecache`. |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | Execute `sudo zypper refresh rediacc` uma vez; as instalações seguintes deverão funcionar. |

### Módulo btrfs em falta (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

Se `rdc config machine setup` ou `renet system check-btrfs` falhar com:

```
Module btrfs not found
```

...o servidor está a executar o kernel padrão do RHEL 10, que não inclui o módulo btrfs integrado. Isto não é um problema do Rediacc; o RHEL 10 removeu o btrfs intencionalmente. A solução é utilizar **Oracle Linux 10**. O Oracle 10 usa por predefinição o Unbreakable Enterprise Kernel (UEK), que mantém o btrfs. Consulte [Requisitos -> Por que UEK?](/pt/docs/requirements) para a história completa.

## Falha na Criação de Repositório

- Verifique se a configuração foi concluída: o diretório do armazenamento de dados deve existir
- Verifique o espaço em disco no servidor
- Certifique-se de que o binário renet está instalado (execute o setup novamente se necessário)

## Falha no Arranque dos Serviços

- Verifique a sintaxe do Rediaccfile: deve ser Bash válido
- Certifique-se de que o seu Rediaccfile usa `renet compose --` (não `docker compose`)
- Verifique se as imagens Docker estão acessíveis (considere `renet compose -- pull` em `up()`)
- Verifique os logs do contentor usando o socket Docker do repositório:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

Ou veja todos os contentores:

```bash
rdc machine containers --name server-1
```

## Erros de Permissão Negada

- As operações em repositórios requerem root no servidor (o renet executa via `sudo`)
- Verifique se o seu utilizador SSH pertence ao grupo `sudo`
- Confirme que o diretório do armazenamento de dados tem as permissões corretas

## Problemas com o Socket Docker

Cada repositório tem o seu próprio daemon Docker. Ao executar comandos Docker manualmente, deve especificar o socket correto:

```bash
# Usando rdc term (configurado automaticamente):
rdc term connect -m server-1 -r my-app -c "docker ps"

# Ou manualmente com o socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Substitua `2816` pelo ID de rede do seu repositório (encontrado em `rediacc.json` ou `rdc repo status`).

## `docker run` sem rede, `apt update` falha, `curl` fica bloqueado

Dentro de uma shell de repositório, executar um contentor sem `--network host` dá-lhe um contentor isolado com apenas uma interface de loopback, sem DNS e sem conectividade de saída. Comandos como `apt update`, `pip install`, `curl https://...` ou qualquer pedido de rede falharão imediatamente com erros DNS.

Isto é intencional. O modelo de rede do Rediacc é **host networking para todos os serviços**, imposto pelo `renet compose`. Uma bridge Docker padrão com NAT contornaria o isolamento de loopback ao nível do kernel que impede um repositório de alcançar os serviços de outro, pelo que o daemon Docker por repositório é configurado com `"bridge": "none"` e `"iptables": false`. Não existe bridge encaminhável a que um contentor `docker run` simples se possa ligar.

**Para obter acesso à rede num contentor ad-hoc, use host networking:**

```bash
# Dentro de uma shell de repositório (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Agora apt update, curl e pip install funcionam.
```

**Para serviços em produção, use um Rediaccfile com `renet compose`** em vez de `docker run` direto. O `renet compose` injeta `network_mode: host`, etiquetas de IP de serviço e etiquetas de encaminhamento Traefik automaticamente. Consulte [Serviços](/pt/docs/services) para mais detalhes.

## Permissão Negada do VS Code em Ficheiros do Sandbox

Ao ligar com `rdc vscode connect -m <machine> -r <repo>`, pode ter visto erros como `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` após uma sessão anterior do VS Code. Isto era causado por propriedade de ficheiros mista dentro do diretório sandbox, que continha ficheiros escritos tanto pelo seu utilizador SSH como pelo utilizador interno `rediacc`.

As versões modernas do renet corrigem isto:

- Criando o espaço de trabalho sandbox por repositório (`/mnt/rediacc/.interim/sandbox/<repo>/`) com o grupo `rediacc` e o bit set-group-ID (modo `2775`), para que todos os ficheiros escritos abaixo herdem o grupo correto.
- Aplicando umask `002` dentro do runtime do sandbox para que os novos ficheiros sejam criados com permissão de escrita de grupo (`0664`/`0775`).
- Normalizando uma subárvore `.vscode-server/` existente no arranque para que ficheiros desatualizados anteriores à correção sejam reparados automaticamente.

Se ainda vir erros de permissão, reinicie o daemon Docker do repositório uma vez com `sudo systemctl restart rediacc-docker-<network-id>` a partir de uma shell na máquina para que a passagem de normalização seja executada, e tente novamente `rdc vscode connect`.

## O Daemon Falha ao Arrancar Após uma Atualização do renet

Antes de cada arranque, `renet daemon start-foreground` reescreve `daemon.json` e `containerd.toml` no diretório de configuração do repositório a partir dos modelos atuais, pelo que um repositório cuja configuração foi gerada por uma versão mais antiga do renet obtém automaticamente o novo formato. Não precisa de executar nenhum comando de migração, nem de regenerar manualmente a unidade systemd. Basta reiniciar o serviço:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Se a unidade continuar a falhar, verifique o journal para um erro específico:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Contentores Criados no Daemon Docker Errado

Se os seus contentores aparecerem no daemon Docker do sistema anfitrião em vez do daemon isolado do repositório, a causa mais comum é o uso de `sudo docker` dentro de um Rediaccfile.

O `sudo` reinicia as variáveis de ambiente, pelo que `DOCKER_HOST` é perdido e o Docker usa por predefinição o socket do sistema (`/var/run/docker.sock`). O Rediacc bloqueia isto automaticamente, mas se se deparar com isso:

- **Use `docker` diretamente**, as funções do Rediaccfile já executam com privilégios suficientes
- Se precisar de usar sudo, use `sudo -E docker` para preservar as variáveis de ambiente
- Verifique o seu Rediaccfile em busca de comandos `sudo docker` e remova o `sudo`

## Terminal Não Funciona

Se `rdc term` falhar ao abrir uma janela de terminal:

- Use o modo inline com `-c` para executar comandos diretamente:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Force o terminal externo com `--external` se o modo inline tiver problemas
- No Linux, certifique-se de que tem `gnome-terminal`, `xterm` ou outro emulador de terminal instalado

## Executar Diagnósticos

```bash
rdc doctor
```

Isto verifica o seu ambiente, a instalação do renet, a configuração e o estado de autenticação. Cada verificação reporta OK, Aviso ou Erro com uma breve explicação.
