---
title: Aplicação Web
description: "Utilizar a consola web do Rediacc para gerir máquinas, repositórios e backups"
category: Reference
order: 1
language: pt
sourceHash: "0951a0a1b320f570"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Guia do Utilizador da Plataforma Rediacc

## Visão Geral

O **Rediacc** é um software auto-alojado que instala nos seus próprios servidores. Com ele pode fazer backup, fork e restauro de sistemas completos e em execução. Aplicações, bases de dados e configuração em conjunto, não ficheiro a ficheiro. Essa última parte é o ponto central: a maioria das ferramentas de backup copia ficheiros e perde as relações entre eles.

Este guia percorre a consola web em [https://www.rediacc.com/](https://www.rediacc.com/).

### Objectivo Deste Guia

- Ajudar novos utilizadores a familiarizarem-se rapidamente com a plataforma
- Explicar as funções básicas (gestão de recursos, backup) passo a passo

---

## 1. Criação de Conta e Início de Sessão

### 1.1 Registo

![Demonstração do processo de registo](/assets/videos/user-guide/01-01-registration.webm)
*(Vídeo: Fluxo completo de registo do início ao fim)*

Para utilizar o Rediacc, precisa primeiro de uma conta.

![Página de início de sessão do Rediacc - infraestrutura sempre activa](/assets/images/user-guide/01_login.png)
*(Figura 1: Página principal de início de sessão, com as funcionalidades principais da plataforma Rediacc)*

1. Aceda a [https://www.rediacc.com/](https://www.rediacc.com/) no seu browser.
2. Clique no botão **{{t:auth.login.signIn}}** no canto superior direito da página.
3. Escolha **Get Started** para acesso gratuito ou **Request Demo** para uma demonstração.

> **Sugestão**: Pode criar uma conta gratuita sem necessitar de cartão de crédito. Inclui equipas ilimitadas.

![Formulário de início de sessão do Rediacc - campos de email e palavra-passe](/assets/images/user-guide/02_register.png)
*(Figura 2: Ecrã de início de sessão para utilizadores existentes)*

4. Se não tiver conta, clique na ligação **{{t:auth.login.register}}** para criar uma nova conta.

5. Preencha as seguintes informações no formulário que abre:
   - **{{t:auth.registration.organizationName}}**: Introduza o nome da sua organização
   - **{{t:auth.login.email}}**: Introduza um endereço de email válido
   - **{{t:auth.login.password}}**: Crie uma palavra-passe com pelo menos 8 caracteres
   - **{{t:auth.registration.passwordConfirm}}**: Reintroduza a mesma palavra-passe

![Modal de criação de conta - passos de registo, verificação e conclusão](/assets/images/user-guide/03_create_account.png)
*(Figura 3: Formulário passo a passo para novos utilizadores - Registar > Verificar > Concluir)*

6. Marque a caixa para aceitar os termos de serviço e a política de privacidade.
7. Clique no botão **{{t:auth.registration.createAccount}}**.

> **Sugestão**: A palavra-passe deve ter pelo menos 8 caracteres e ser robusta. Todos os campos são obrigatórios.

8. Introduza sequencialmente nos campos o código de verificação de 6 dígitos enviado para o seu email.
9. Clique no botão **{{t:auth.registration.verifyAccount}}**.

![Introdução do código de verificação - código de activação de 6 dígitos](/assets/images/user-guide/04_verification_code.png)
*(Figura 4: Janela para introduzir o código de activação enviado ao administrador)*

> **Sugestão**: O código de verificação tem validade limitada. Se não receber o código, verifique a pasta de spam.

---

### 1.2 Início de Sessão

![Demonstração do processo de início de sessão](/assets/videos/user-guide/01-02-login.webm)
*(Vídeo: Fluxo completo de início de sessão)*

Após criar a conta, pode iniciar sessão na plataforma.

1. Preencha o campo **{{t:auth.login.email}}** (obrigatório se aparecer um aviso a vermelho).
2. Preencha o campo **{{t:auth.login.password}}**.
3. Clique no botão **{{t:auth.login.signIn}}**.

![Formulário de início de sessão - campos obrigatórios com aviso de erro](/assets/images/user-guide/05_sign_in.png)
*(Figura 5: Formulário de início de sessão - as mensagens de erro são assinaladas com um contorno vermelho)*

> **Sugestão**: Se a mensagem de erro indicar "Este campo é obrigatório", preencha os campos em branco. Em caso de palavra-passe esquecida, contacte o administrador.

4. Após o início de sessão bem-sucedido, será redirecionado para o ecrã **{{t:common.navigation.dashboard}}**.

![Painel do Rediacc - lista de máquinas e menu lateral](/assets/images/user-guide/06_dashboard.png)
*(Figura 6: Painel principal após início de sessão bem-sucedido - menus Organização, Máquinas e Definições na barra lateral esquerda)*

> **Sugestão**: O painel actualiza-se automaticamente. Pode actualizar a página com F5 para obter informações mais recentes.

---

## 2. Visão Geral da Interface

Após iniciar sessão, o ecrã que vê é composto pelas seguintes secções principais:

- **{{t:common.navigation.organization}}**: Utilizadores, equipas e controlo de acesso
- **{{t:common.navigation.machines}}**: Gestão de servidores e repositórios
- **{{t:common.navigation.settings}}**: Definições de perfil e do sistema
- **{{t:common.navigation.storage}}**: Gestão de áreas de armazenamento
- **{{t:common.navigation.credentials}}**: Credenciais de acesso
- **{{t:common.navigation.queue}}**: Gestão da fila de tarefas
- **{{t:common.navigation.audit}}**: Registos de auditoria do sistema

---

## 2.1 Organização - Utilizadores

A gestão de utilizadores é onde controla quem na sua organização tem acesso.

### 2.1.1 Adicionar Utilizadores

![Demonstração de adição de utilizadores](/assets/videos/user-guide/02-01-01-user-create.webm)
*(Vídeo: Criar um novo utilizador)*

1. Clique na opção **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** na barra lateral esquerda.
2. Consulte a lista de todos os utilizadores em formato de tabela.
3. Cada linha de utilizador mostra o email, o estado ({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), o grupo de permissões e a hora da última actividade.

![Página de gestão de utilizadores - lista de utilizadores activos](/assets/images/user-guide/07_users.png)
*(Figura 7: Secção de Utilizadores em Organização - todas as informações dos utilizadores são apresentadas)*

4. Clique no ícone **"+"** no canto superior direito.
5. Clique no botão **{{t:organization.users.modals.createTitle}}** e preencha o formulário que abre:
   - **{{t:organization.users.form.emailLabel}}**: Introduza o endereço de email do utilizador
   - **{{t:organization.users.form.passwordLabel}}**: Introduza uma palavra-passe temporária

![Modal de criação de utilizador - campos de email e palavra-passe](/assets/images/user-guide/08_user_add.png)
*(Figura 8: Janela modal para adicionar novo utilizador - formulário de criação simples e rápido)*

6. Clique no botão **{{t:common.actions.create}}**.

> **Sugestão**: As credenciais de acesso devem ser comunicadas ao utilizador criado de forma segura. Recomenda-se a alteração da palavra-passe no primeiro início de sessão.

![Lista de utilizadores - tabela completa com três utilizadores](/assets/images/user-guide/09_user_list.png)
*(Figura 9: Todos os utilizadores activos e inactivos na página de gestão de utilizadores)*

> **Sugestão**: A página apresenta automaticamente 20 registos. Utilize a paginação para ver mais registos.

### 2.1.2 Atribuir Permissões a Utilizadores

![Demonstração de permissões de utilizador](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(Vídeo: Atribuir grupos de permissões a utilizadores)*

Pode gerir os direitos de acesso atribuindo grupos de permissões específicos aos utilizadores.

1. Seleccione um utilizador no separador **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**.
2. Clique no ícone de escudo na coluna de acções (**{{t:organization.access.tabs.permissions}}**).

![Gestão de permissões - ícones de escudo, engrenagem e eliminação](/assets/images/user-guide/10_users_permissions.png)
*(Figura 10: Apresentação dos ícones de acções do utilizador - cada ícone representa uma acção diferente)*

3. Seleccione um **{{t:organization.users.modals.permissionGroupLabel}}** no formulário que abre.
4. O número de utilizadores e permissões no grupo é apresentado junto ao utilizador.
5. Clique no botão **{{t:organization.users.modals.assignTitle}}** para guardar as alterações.

![Modal de atribuição de permissões - grupo Administradores](/assets/images/user-guide/11_user_permissions_form.png)
*(Figura 11: Modal para atribuir grupo de permissões ao utilizador seleccionado - dropdown com os grupos disponíveis)*

> **Sugestão**: Alguns grupos de permissões são fixos pelo sistema e não podem ser alterados.

### 2.1.3 Activação de Utilizadores

![Demonstração de activação de utilizador](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(Vídeo: Activar um utilizador inactivo)*

Pode reactivar utilizadores desactivados.

1. Encontre o utilizador com estado inactivo na lista de **Utilizadores**.
2. Clique no ícone vermelho na coluna de acções.

![Activação de utilizador - vista da dica de ferramentas "Activar"](/assets/images/user-guide/12_users_activation.png)
*(Figura 12: Activar um utilizador inactivo)*

3. Clique no botão **{{t:common.general.yes}}** na janela de confirmação.

![Modal de confirmação de activação](/assets/images/user-guide/13_users_activation_confirm.png)
*(Figura 13: Janela modal para confirmar a activação do utilizador)*

> **Sugestão**: Esta acção é reversível. Pode desactivar o utilizador da mesma forma.

### 2.1.4 Rastreio de Utilizadores

![Demonstração de rastreio de utilizador](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(Vídeo: Ver o rastreio de actividade do utilizador)*

Pode utilizar a funcionalidade de rastreio para monitorizar as actividades dos utilizadores.

1. Seleccione um utilizador e clique no ícone de engrenagem na coluna de acções.
2. Clique na opção **{{t:common.actions.trace}}** para abrir o histórico de actividade do utilizador.

![Rastreio do utilizador - dica de ferramentas "Trace" com botão de acção](/assets/images/user-guide/14_users_trace.png)
*(Figura 14: Opção de rastreio de actividade do utilizador)*

3. As actividades passadas do utilizador são listadas no ecrã que abre.
4. As estatísticas são apresentadas no topo: Total de Registos, Registos Visualizados, Última Actividade.
5. Clique no botão **{{t:common.actions.export}}** e seleccione o formato: **{{t:common.exportCSV}}** ou **{{t:common.exportJSON}}**.

![Histórico de auditoria - opções de exportação](/assets/images/user-guide/15_user_trace_export.png)
*(Figura 15: Histórico completo de actividade do utilizador - estatísticas, detalhes e opções de exportação)*

> **Sugestão**: Exporte regularmente os dados de auditoria para manter registos de segurança e conformidade. O formato CSV pode ser aberto no Excel.

---

## 2.2 Organização - Equipas

As equipas agrupam utilizadores para que possa conceder acesso em bloco.

### 2.2.1 Criar Equipas

![Demonstração de criação de equipas](/assets/videos/user-guide/02-02-01-team-create.webm)
*(Vídeo: Criar uma nova equipa)*

1. Aceda ao separador **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}**.
2. Clique no botão **"+"**.
3. Introduza o nome da equipa no campo **{{t:common.vaultEditor.fields.TEAM.name.label}}**.
4. Preencha os campos **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** e **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** na secção **{{t:common.vaultEditor.vaultConfiguration}}**.

![Formulário de criação de nova equipa - nome e chaves SSH](/assets/images/user-guide/16_teams_create.png)
*(Figura 16: Criar uma nova equipa em "Private Team")*

5. Clique no botão **{{t:common.actions.create}}** para guardar a equipa.

> **Sugestão**: As chaves SSH são necessárias para a autenticação SSH do Bridge. Se receber um aviso de chave em falta, forneça ambas as chaves.

### 2.2.2 Edição de Equipas

![Demonstração de edição de equipas](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(Vídeo: Editar informações da equipa)*

1. Clique no ícone de lápis junto à equipa que pretende editar na lista de equipas.
2. Altere o nome da equipa no campo **{{t:common.vaultEditor.fields.TEAM.name.label}}**, se necessário.
3. Actualize as chaves SSH na secção **{{t:common.vaultEditor.vaultConfiguration}}**.
4. Clique no botão **{{t:common.save}}** para aplicar as alterações.

![Formulário de edição de equipa - mensagem de informação azul](/assets/images/user-guide/17_teams_edit_form.png)
*(Figura 17: Editar as informações de uma equipa existente)*

> **Sugestão**: A configuração da equipa é utilizada para a estrutura organizacional. As alterações têm efeito para todos os membros da equipa.

### 2.2.3 Gestão de Membros da Equipa

![Demonstração de gestão de membros da equipa](/assets/videos/user-guide/02-02-03-team-members.webm)
*(Vídeo: Gerir membros da equipa)*

1. Seleccione uma equipa e clique no ícone de utilizador.
2. Consulte os membros já atribuídos à equipa no separador **{{t:organization.teams.manageMembers.currentTab}}**.
3. Mude para o separador **{{t:organization.teams.manageMembers.addTab}}**.
4. Introduza um endereço de email ou seleccione um utilizador no dropdown.
5. Clique no botão **"+"** para adicionar o membro à equipa.

![Formulário de gestão de membros da equipa - separadores "Membros Actuais" e "Adicionar Membro"](/assets/images/user-guide/18_teams_members_form.png)
*(Figura 18: Painel de gestão de membros da equipa)*

> **Sugestão**: Pode atribuir o mesmo membro a múltiplas equipas.

### 2.2.4 Rastreio de Equipas

![Demonstração de rastreio de equipa](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(Vídeo: Ver o histórico de auditoria da equipa)*

1. Seleccione a equipa que pretende rastrear.
2. Clique no ícone de relógio/histórico.
3. Consulte as contagens de Total de Registos, Registos Visualizados e Última Actividade no modal **{{t:resources.audit.title}}**.
4. Clique no botão **{{t:common.actions.export}}** para exportar em formato {{t:common.exportCSV}} ou {{t:common.exportJSON}}.

![Modal de histórico de auditoria - equipa DataBassTeam](/assets/images/user-guide/19_teams_trace.png)
*(Figura 19: Ver o histórico de auditoria da equipa)*

> **Sugestão**: O histórico de auditoria é importante para controlo de conformidade e segurança.

### 2.2.5 Eliminação de Equipas

![Demonstração de eliminação de equipa](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(Vídeo: Eliminar uma equipa)*

1. Clique no ícone de caixote do lixo (vermelho) junto à equipa que pretende eliminar.
2. Verifique se o nome da equipa está correcto na caixa de confirmação.
3. Clique no botão **{{t:common.general.yes}}**.

![Caixa de confirmação de eliminação de equipa](/assets/images/user-guide/20_teams_delete.png)
*(Figura 20: Confirmação de eliminação de equipa)*

> **Aviso**: A eliminação de uma equipa é irreversível. Verifique se existem dados importantes na equipa antes de eliminar.

---

## 2.3 Organização - Controlo de Acesso

O controlo de acesso centraliza as permissões através de grupos, em vez de ser por utilizador.

### 2.3.1 Criar Grupos de Permissões

![Demonstração de criação de grupo de permissões](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(Vídeo: Criar um grupo de permissões)*

1. Aceda ao separador **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}**.
2. Clique no botão **"+"**.
3. Introduza um nome significativo no campo **{{t:organization.access.modals.groupPlaceholder}}**.
4. Clique no botão **{{t:common.actions.confirm}}** para criar o grupo.

![Formulário de criação de grupo de permissões](/assets/images/user-guide/21_create_access.png)
*(Figura 21: Criar um novo Grupo de Permissões)*

> **Sugestão**: Os grupos de permissões são utilizados para organizar utilizadores com permissões semelhantes. Mantenha os nomes dos grupos descritivos (por exemplo, "Admin", "Só Leitura", "Gestor de Repositórios").

### 2.3.2 Gestão de Permissões

![Demonstração de gestão de permissões](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(Vídeo: Gerir permissões para um grupo)*

1. Seleccione um Grupo de Permissões e clique na opção **{{t:organization.access.modals.managePermissionsTitle}}**.
2. Consulte os direitos de acesso do grupo no separador **{{t:organization.access.modals.currentPermissionsTab}}**.
3. Pode revogar uma permissão clicando no botão vermelho **{{t:common.delete}}** junto a cada acção.
4. Clique no separador **{{t:organization.access.modals.addPermissionsTab}}** para adicionar novas permissões ao grupo.

![Painel de gestão de permissões - lista de permissões atribuídas](/assets/images/user-guide/22_access_permission.png)
*(Figura 22: Gerir Permissões para o Grupo de Permissões)*

> **Sugestão**: Conceda permissões com base no princípio do menor privilégio. Reveja e remova regularmente as permissões desnecessárias.

---

## 2.4 Máquinas

A secção Máquinas é onde gere os seus servidores e os repositórios neles existentes.

### 2.4.1 Adicionar Máquinas

![Demonstração de adição de máquinas](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(Vídeo: Adicionar uma nova máquina)*

1. Aceda ao separador **{{t:common.navigation.machines}}** no menu esquerdo.
2. Clique no botão **{{t:machines.createMachine}}** no canto superior direito.

![Página de máquinas - botão "Adicionar Máquina"](/assets/images/user-guide/23_machines_add.png)
*(Figura 23: Página inicial de gestão de máquinas)*

3. Preencha o formulário que abre:
   - **{{t:machines.machineName}}**: Introduza um nome único (por exemplo, "servidor-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: Introduza o endereço IP da máquina (por exemplo, 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: Especifique o directório de armazenamento (por exemplo, /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: Introduza o nome de utilizador SSH
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: Introduza o número de porta (predefinição: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: Introduza a palavra-passe (opcional)

![Formulário de adição de máquina - todos os campos](/assets/images/user-guide/24_machine_create.png)
*(Figura 24: Formulário de adição de nova máquina - nome da máquina, definições de rede, credenciais SSH)*

4. Clique no botão **{{t:common.vaultEditor.testConnection.button}}** para verificar a ligação.
5. Após o teste ter sucesso, clique no botão **{{t:common.actions.create}}**.

> **Sugestão**: Se a opção "Iniciar configuração automaticamente após criar a máquina" estiver marcada, a máquina efectuará automaticamente os passos de configuração adicionais.

![Criação de máquina concluída - janela de acompanhamento de tarefa](/assets/images/user-guide/25_machine_create_complete.png)
*(Figura 25: Janela de acompanhamento de tarefa após a criação bem-sucedida da máquina)*

6. Acompanhe as fases: **{{t:queue.trace.assigned}}** → **Em processamento** → **{{t:queue.statusCompleted}}**
7. Clique no botão **{{t:common.actions.close}}** para fechar a operação.

> **Sugestão**: Clique no botão "{{t:common.actions.refresh}}" para verificar manualmente o estado mais recente.

### 2.4.2 Teste de Conectividade

![Demonstração de teste de conectividade](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(Vídeo: Executar um teste de conectividade)*

Pode verificar o estado da ligação de máquinas existentes.

1. Clique no botão **{{t:machines.connectivityTest}}**.

![Botão de Teste de Conectividade](/assets/images/user-guide/26_connectivity_test_button.png)
*(Figura 26: Botão de Teste de Conectividade na barra de ferramentas de acções de máquina)*

2. Veja a lista de máquinas a testar.
3. Clique no botão **{{t:machines.runTest}}**.
4. Os resultados bem-sucedidos são mostrados a verde, as falhas a vermelho.

![Formulário de teste de conectividade - lista de máquinas](/assets/images/user-guide/27_connectivity_test_form.png)
*(Figura 27: Formulário de teste de conectividade - função de ping para as máquinas seleccionadas)*

> **Sugestão**: Se o teste falhar, verifique o endereço IP da máquina e as definições SSH.

### 2.4.3 Actualizar Lista de Máquinas

![Demonstração de actualização da lista de máquinas](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(Vídeo: Actualizar a lista de máquinas)*

Clique no botão **{{t:common.actions.refresh}}** para actualizar a lista de máquinas.

![Botão de actualização](/assets/images/user-guide/28_refresh.png)
*(Figura 28: Botão de actualização na barra de ferramentas de acções de máquina)*

### 2.4.4 Detalhes da Máquina

![Demonstração de detalhes da máquina](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(Vídeo: Ver os detalhes da máquina)*

1. Seleccione a máquina cujos detalhes pretende ver.
2. Clique no botão com o ícone de olho (**{{t:common.viewDetails}}**).

![Botão Ver Detalhes](/assets/images/user-guide/29_view_details_button.png)
*(Figura 29: Ícone de olho na coluna de acções da máquina)*

3. O painel de detalhes da máquina abre no lado direito:
   - **Hostname**: Nome da máquina
   - **Uptime**: Tempo de funcionamento
   - **{{t:queue.trace.operatingSystem}}**: Sistema operativo e versão
   - **{{t:queue.trace.kernelVersion}}**: Versão do kernel
   - **CPU**: Informações do processador
   - **System Time**: Relógio do sistema

![Painel de detalhes da máquina - informações do sistema](/assets/images/user-guide/30_machine_view_details.png)
*(Figura 30: Painel de detalhes da máquina - informações de hostname, uptime, sistema operativo, kernel e CPU)*

> **Sugestão**: Reveja estas informações regularmente para verificar a compatibilidade do sistema operativo e a disponibilidade de recursos.

### 2.4.5 Edição de Máquinas

![Demonstração de edição de máquinas](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(Vídeo: Editar definições da máquina)*

1. Seleccione a máquina que pretende editar.
2. Clique no botão com o ícone de lápis (**{{t:common.actions.edit}}**).

![Botão de edição](/assets/images/user-guide/31_edit_button.png)
*(Figura 31: Ícone de lápis na coluna de acções da máquina)*

3. Efectue as alterações necessárias.
4. Clique no botão **{{t:common.vaultEditor.testConnection.button}}**.
5. Quando a ligação for bem-sucedida, clique no botão **{{t:common.save}}**.

![Formulário de edição de máquina](/assets/images/user-guide/32_edit_form.png)
*(Figura 32: Formulário de edição de máquina - nome da máquina, região e configuração de vault)*

> **Sugestão**: Execute sempre "Testar Ligação" após alterar definições críticas.

### 2.4.6 Rastreio de Máquinas

![Demonstração de rastreio de máquinas](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(Vídeo: Ver o histórico de auditoria da máquina)*

1. Seleccione a máquina e clique no botão com o ícone de relógio (**{{t:common.actions.trace}}**).

![Botão de rastreio](/assets/images/user-guide/33_trace_button.png)
*(Figura 33: Ícone de relógio na coluna de acções da máquina)*

2. Consulte as operações na janela do histórico de auditoria:
   - **{{t:resources.audit.action}}**: Tipo de operação realizada
   - **Detalhes**: Campos alterados
   - **{{t:resources.audit.performedBy}}**: Utilizador que realizou a acção
   - **Timestamp**: Data e hora

![Janela de histórico de auditoria da máquina](/assets/images/user-guide/34_trace_list.png)
*(Figura 34: Histórico de auditoria - lista de todas as alterações)*

> **Sugestão**: Clique na coluna Timestamp para ver as alterações em ordem cronológica.

### 2.4.7 Eliminação de Máquinas

![Demonstração de eliminação de máquinas](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(Vídeo: Eliminar uma máquina)*

1. Seleccione a máquina que pretende eliminar.
2. Clique no botão com o ícone de caixote do lixo (**{{t:common.delete}}**).

![Botão de eliminação](/assets/images/user-guide/35_delete_button.png)
*(Figura 35: Ícone de caixote do lixo na coluna de acções da máquina)*

3. Clique no botão **{{t:common.delete}}** na janela de confirmação.

![Janela de confirmação de eliminação de máquina](/assets/images/user-guide/36_delete_form.png)
*(Figura 36: Janela de confirmação "Tem a certeza que pretende eliminar esta máquina?")*

> **Aviso**: Quando uma máquina é eliminada, todas as definições de repositórios nela existentes são também removidas. Esta acção é irreversível.

### 2.4.8 Operações Remotas

![Demonstração de operações remotas](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(Vídeo: Executar operações remotas numa máquina)*

Pode executar operações remotas numa máquina a partir da web.

1. Seleccione a máquina e clique no botão **{{t:common.actions.remote}}**.
2. Veja as opções no menu dropdown:
   - **{{t:machines.runAction}}**: Executar função na máquina
   - **{{t:common.vaultEditor.testConnection.button}}**: Fazer ping à máquina

![Menu remoto - Executar no Servidor e Testar Ligação](/assets/images/user-guide/37_remote_button.png)
*(Figura 37: Botão remoto - menu de execução de funções na máquina seleccionada)*

> **Sugestão**: Utilize a opção "{{t:common.vaultEditor.testConnection.button}}" para verificar se a máquina está acessível antes de executar funções.

#### Configuração

1. Seleccione a opção **{{t:machines.runAction}}**.
2. Encontre a função **Setup** na lista **{{t:functions.availableFunctions}}**.
3. Clique no nome da função para a seleccionar.

![Lista de funções da máquina - função de configuração](/assets/images/user-guide/38_server_setup.png)
*(Figura 38: Função de configuração - prepara a máquina com as ferramentas e configurações necessárias)*

> **Sugestão**: Recomenda-se executar primeiro a função "setup" ao configurar uma nova máquina.

#### Verificação de Ligação (Hello)

1. Seleccione **{{t:machines.runAction}}** > função **Hello**.
2. Clique no botão **{{t:common.actions.addToQueue}}**.

![Selecção da função Hello](/assets/images/user-guide/39_remote_hello.png)
*(Figura 39: Função Hello - função de teste simples que devolve o hostname)*

3. Acompanhe os resultados na janela de acompanhamento de tarefas.
4. Consulte o resultado da máquina na secção **{{t:queue.trace.responseConsole}}**.

![Função Hello concluída](/assets/images/user-guide/40_remote_hello_complete.png)
*(Figura 40: Função Hello concluída com sucesso - resposta com o hostname)*

> **Sugestão**: A função hello é ideal para verificar a conectividade da máquina.

#### Operações Avançadas

1. Siga o caminho **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}**.
2. Veja as funções disponíveis: setup, hello, ping, ssh_test, uninstall
3. Seleccione a função pretendida e clique no botão **{{t:common.actions.addToQueue}}**.

![Lista de funções avançadas](/assets/images/user-guide/41_remote_advanced.png)
*(Figura 41: Opção Avançadas - lista de funções avançadas)*

> **Sugestão**: Certifique-se de que a configuração da máquina está concluída antes de utilizar as funções Avançadas.

#### Teste Rápido de Conectividade

![Menu remoto - Testar Ligação](/assets/images/user-guide/42_connectivity_test.png)
*(Figura 42: Opção Testar Ligação no menu Remoto)*

> **Sugestão**: Se a máquina tiver problemas de SSH ou de rede, pode identificar rapidamente os problemas com este teste.

---

## 2.5 Criação e Operações de Repositórios

Um repositório é uma implementação de aplicação isolada. As suas aplicações, os seus dados, a sua configuração, o seu próprio Docker daemon. Por isso, quase todos os botões desta página actuam sobre um repositório, não sobre a máquina em que se encontra. Vale a pena saber antes de clicar em Eliminar.

### 2.5.1 Criar Repositórios

![Demonstração de criação de repositório](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(Vídeo: Criar um novo repositório)*

1. Seleccione uma máquina no separador **{{t:common.navigation.machines}}**.
2. Clique no botão **{{t:machines.createRepository}}** no canto superior direito.

![Botão Criar Repositório](/assets/images/user-guide/43_create_repo_add.png)
*(Figura 43: Ecrã de gestão de repositórios da máquina - botão Criar Repositório)*

3. Preencha o formulário:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: Introduza o nome do repositório (por exemplo, postgresql)
   - **{{t:resources.repositories.size}}**: Introduza o tamanho do repositório (por exemplo, 2GB)
   - **{{t:resources.repositories.repositoryGuid}}**: Consulte a credencial gerada automaticamente
   - **{{t:resources.templates.selectTemplate}}**: Escolha um modelo (por exemplo, databases_postgresql)

![Formulário de criação de repositório](/assets/images/user-guide/44_repo_form.png)
*(Figura 44: Formulário de criação de repositório - nome, tamanho e selecção de modelo)*

4. Clique no botão **{{t:common.actions.create}}**.

> **Sugestão**: O ID da credencial é gerado automaticamente; não se recomenda a modificação manual.

5. Acompanhe as fases na janela de acompanhamento de tarefas: **{{t:queue.trace.assigned}}** → **Em processamento** → **{{t:queue.statusCompleted}}**

![Criação de repositório concluída](/assets/images/user-guide/45_repo_complete.png)
*(Figura 45: Repositório criado em fila - monitorização da tarefa)*

6. Clique no botão **{{t:common.actions.close}}**.

> **Sugestão**: A tarefa normalmente conclui dentro de 1 a 2 minutos.

![Lista de repositórios](/assets/images/user-guide/46_repo_list.png)
*(Figura 46: O repositório criado aparece na lista)*

### 2.5.2 Fork de Repositório

![Demonstração de fork de repositório](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(Vídeo: Criar um fork de um repositório)*

Pode criar um novo repositório copiando um existente.

1. Seleccione o repositório que pretende copiar.
2. Clique no menu **fx** (função).
3. Clique na opção **fork**.

![Menu fx - opção fork](/assets/images/user-guide/47_fork_button.png)
*(Figura 47: Menu fx no lado direito - operações de repositório)*

4. Introduza uma nova etiqueta no campo **{{t:functions.functions.fork.params.tag.label}}** (por exemplo, 2025-12-06-20-37-08).
5. Clique no botão **{{t:common.actions.addToQueue}}**.

![Formulário de configuração do fork](/assets/images/user-guide/48_fork_form.png)
*(Figura 48: Especificar a nova etiqueta para o repositório na operação de fork)*

6. Aguarde a mensagem **{{t:queue.statusCompleted}}** e clique no botão **{{t:common.actions.close}}**.

![Fork concluído](/assets/images/user-guide/49_repo_completed.png)
*(Figura 49: Operação de fork concluída com sucesso)*

> **Sugestão**: Criar etiquetas no formato data-hora predefinido é uma boa prática. A operação de fork não afecta o repositório original.

### 2.5.3 Iniciar Repositório (Up)

![Demonstração de início de repositório](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(Vídeo: Iniciar um repositório)*

Para activar o repositório:

1. Seleccione o repositório e siga o caminho **fx** > **up**.

![Operação Up](/assets/images/user-guide/50_repo_up.png)
*(Figura 50: Opção "up" no menu fx - iniciar o repositório)*

2. Aguarde a mensagem **{{t:queue.statusCompleted}}**.

![Up concluído](/assets/images/user-guide/51_repo_up_complete.png)
*(Figura 51: Arranque do repositório concluído)*

> **Sugestão**: A operação "Up" inicia os serviços Docker definidos no repositório.

### 2.5.4 Parar Repositório (Down)

![Demonstração de paragem de repositório](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(Vídeo: Parar um repositório)*

Para parar um repositório activo:

1. Seleccione o repositório e siga o caminho **fx** > **down**.

![Operação Down](/assets/images/user-guide/52_down_button.png)
*(Figura 52: Opção "down" no menu fx - encerrar o repositório)*

2. Aguarde a mensagem **{{t:queue.statusCompleted}}**.

![Down concluído](/assets/images/user-guide/53_down_completed.png)
*(Figura 53: Encerramento do repositório concluído)*

> **Sugestão**: A operação "Down" encerra o repositório de forma segura. Não são perdidos dados; apenas os serviços são parados.

### 2.5.5 Implementação (Deploy)

![Demonstração de implementação de repositório](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(Vídeo: Implementar um repositório)*

Para implementar o repositório noutro local:

1. Seleccione o repositório e siga o caminho **fx** > **deploy**.

![Operação Deploy](/assets/images/user-guide/54_deploy_button.png)
*(Figura 54: Opção "deploy" no menu fx)*

2. Introduza a versão a implementar no campo **{{t:functions.functions.fork.params.tag.label}}**.
3. Seleccione as máquinas de destino no campo **{{t:functions.functions.backup_deploy.params.machines.label}}**.
4. Marque a opção **{{t:functions.checkboxOptions.overrideExistingFile}}** (se aplicável).
5. Clique no botão **{{t:common.actions.addToQueue}}**.

![Formulário de implementação](/assets/images/user-guide/55_deploy_form.png)
*(Figura 55: Configurar a operação de implementação - etiqueta, máquinas de destino e opções)*

6. Aguarde a mensagem **{{t:queue.statusCompleted}}**.

![Implementação concluída](/assets/images/user-guide/56_deploy_completed.png)
*(Figura 56: Implementação do repositório concluída)*

> **Sugestão**: Após a conclusão da implementação, pode executar o comando "up" para iniciar o repositório nas máquinas de destino.

### 2.5.6 Backup

![Demonstração de backup de repositório](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(Vídeo: Criar backup de um repositório)*

Para criar backup do repositório:

1. Seleccione o repositório e siga o caminho **fx** > **backup**.

![Operação de backup](/assets/images/user-guide/57_backup_button.png)
*(Figura 57: Opção "backup" no menu fx)*

2. Preencha o formulário:
   - **{{t:functions.functions.fork.params.tag.label}}**: Introduza um nome descritivo (por exemplo, backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}**: Seleccione o local de backup
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: Activar ou desactivar a opção
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: Reveja a definição

![Formulário de backup](/assets/images/user-guide/58_backup_form.png)
*(Figura 58: Formulário de configuração de backup - destino, nome do ficheiro e opções)*

3. Clique no botão **{{t:common.actions.addToQueue}}**.

> **Sugestão**: Utilize um nome descritivo para a etiqueta de backup. Considere activar o checkpoint para repositórios de grande dimensão.

4. Aguarde a mensagem **{{t:queue.statusCompleted}}**.

![Backup concluído](/assets/images/user-guide/59_backup_completed.png)
*(Figura 59: Tarefa de backup concluída com sucesso)*

> **Sugestão**: Aguarde com paciência antes de atingir o estado concluído; backups de grande dimensão podem demorar vários minutos.

### 2.5.7 Aplicação de Modelos

![Demonstração de aplicação de modelo](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(Vídeo: Aplicar um modelo a um repositório)*

Para aplicar um novo modelo ao repositório:

1. Seleccione o repositório e siga o caminho **fx** > **{{t:resources.templates.selectTemplate}}**.

![Operação de modelos](/assets/images/user-guide/60_templates_button.png)
*(Figura 60: Opção "Modelos" no menu fx)*

2. Filtre os modelos escrevendo na caixa de pesquisa.
3. Clique no modelo pretendido para o seleccionar (o modelo seleccionado é destacado com um contorno a negrito).
4. Clique no botão **{{t:common.actions.addToQueue}}**.

![Formulário de selecção de modelo](/assets/images/user-guide/61_templates_form.png)
*(Figura 61: Pesquisar e seleccionar modelos disponíveis)*

> **Sugestão**: Utilize a caixa de pesquisa para encontrar modelos rapidamente. Utilize "{{t:common.viewDetails}}" para conhecer as funcionalidades do modelo.

5. Aguarde a mensagem **{{t:queue.statusCompleted}}**.

![Modelo aplicado](/assets/images/user-guide/62_templates_completed.png)
*(Figura 62: Aplicação do modelo concluída com sucesso)*

### 2.5.8 Desmontar (Unmount)

![Demonstração de desmontagem de repositório](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(Vídeo: Desmontar um repositório)*

Para desligar o repositório:

1. Seleccione o repositório e siga o caminho **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}**.

![Operação de desmontagem](/assets/images/user-guide/63_unmount_button.png)
*(Figura 63: Opção "Desmontar" no menu avançado)*

2. Aguarde a mensagem **{{t:queue.statusCompleted}}**.

![Desmontagem concluída](/assets/images/user-guide/64_unmount_completed.png)
*(Figura 64: Operação de desmontagem concluída)*

> **Sugestão**: Certifique-se de que não existem operações activas no repositório antes de desmontar. Após a desmontagem, o repositório fica inacessível.

### 2.5.9 Expandir (Expand)

![Demonstração de expansão de repositório](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(Vídeo: Expandir o tamanho do repositório)*

Para aumentar o tamanho do repositório:

1. Seleccione o repositório e siga o caminho **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}**.

![Operação de expansão](/assets/images/user-guide/65_expand_button.png)
*(Figura 65: Opção "Expandir" no menu avançado)*

2. Introduza o tamanho pretendido no campo **{{t:functions.functions.repository_expand.params.size.label}}**.
3. Seleccione a unidade no dropdown à direita (GB, TB).
4. Clique no botão **{{t:common.actions.addToQueue}}**.

![Formulário de expansão](/assets/images/user-guide/66_expand_form.png)
*(Figura 66: Novo parâmetro de tamanho para aumentar o tamanho do repositório)*

> **Sugestão**: Não introduza um valor inferior ao tamanho actual. O serviço não é interrompido durante a expansão do repositório.

5. Aguarde a mensagem **{{t:queue.statusCompleted}}**.

![Expansão concluída](/assets/images/user-guide/67_expand_completed.png)
*(Figura 67: Expansão do repositório concluída)*

### 2.5.10 Renomear

![Demonstração de renomeação de repositório](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(Vídeo: Renomear um repositório)*

Para alterar o nome do repositório:

1. Seleccione o repositório e siga o caminho **fx** > **{{t:common.actions.rename}}**.

![Operação de renomeação](/assets/images/user-guide/68_rename_button.png)
*(Figura 68: Opção "Renomear" no menu fx)*

2. Introduza o novo nome do repositório.
3. Clique no botão **{{t:common.save}}**.

![Formulário de renomeação](/assets/images/user-guide/69_rename_form.png)
*(Figura 69: Caixa de diálogo para introduzir o novo nome do repositório)*

> **Sugestão**: Os nomes dos repositórios devem ser significativos para reflectir o tipo e a finalidade do repositório. Evite caracteres especiais.

### 2.5.11 Eliminação de Repositórios

![Demonstração de eliminação de repositório](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(Vídeo: Eliminar um repositório)*

Para eliminar permanentemente o repositório:

1. Seleccione o repositório e siga o caminho **fx** > **{{t:resources.repositories.deleteRepository}}**.

![Operação de eliminação de repositório](/assets/images/user-guide/70_delete_repo_button.png)
*(Figura 70: Opção "Eliminar Repositório" no menu fx - a vermelho)*

2. Clique no botão **{{t:common.delete}}** na janela de confirmação.

> **Aviso**: A eliminação de repositórios é irreversível. Certifique-se de que os dados do repositório têm backup antes de eliminar.

### 2.5.12 Detalhes do Repositório

![Demonstração de detalhes do repositório](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(Vídeo: Ver detalhes do repositório)*

Para obter informações detalhadas sobre o repositório:

1. Seleccione o repositório.
2. Clique no ícone de olho (**{{t:common.viewDetails}}**).

![Botão Ver Detalhes](/assets/images/user-guide/71_repo_view_button.png)
*(Figura 71: Ícone de olho para abrir os detalhes do repositório)*

3. Consulte as informações no painel de detalhes:
   - **Nome do repositório** e tipo
   - **Equipa**: A equipa a que pertence
   - **Máquina**: A máquina em que se encontra
   - **Vault Version**: Versão de encriptação
   - **Repository GUID**: Identificador único
   - **Estado**: Estado Montado/Desmontado
   - **Image Size**: Tamanho total
   - **Last Modified**: Data da última modificação

![Painel de detalhes do repositório](/assets/images/user-guide/72_repo_details_view.png)
*(Figura 72: Informação completa sobre o repositório seleccionado)*

> **Sugestão**: Todas as informações apresentadas neste painel são de referência. Utilize as opções do menu fx para operações no repositório.

---

## 2.6 Operações de Ligação a Repositórios

Pode ligar-se a um repositório de duas formas. A aplicação de ambiente de trabalho dá-lhe um terminal real e SSH. O browser é adequado para inspecção e gestão por cliques, mas não consegue sustentar sessões de shell longas. Escolha a aplicação de ambiente de trabalho se estiver a fazer trabalho real.

### 2.6.1 Ligação via Aplicação de Ambiente de Trabalho

![Demonstração de ligação via ambiente de trabalho](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(Vídeo: Ligar através da aplicação de ambiente de trabalho)*

1. Clique no botão **{{t:resources.localActions.local}}** na linha do repositório.

![Botão de ligação local](/assets/images/user-guide/73_repo_connection_local.png)
*(Figura 73: Botão "Local" na linha do repositório - acesso pela aplicação de ambiente de trabalho)*

2. Seleccione o método de acesso no menu dropdown:
   - **{{t:resources.localActions.openInDesktop}}**: Acesso com interface gráfica
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: Abrir no editor de código
   - **{{t:common.terminal.terminal}}**: Acesso via linha de comandos
   - **{{t:resources.localActions.showCLICommands}}**: Ferramentas de linha de comandos

![Menu de opções de ligação](/assets/images/user-guide/74_repo_connection.png)
*(Figura 74: Menu de ligação ao repositório - diferentes caminhos de acesso)*

> **Sugestão**: Se trabalhar com VS Code, a opção "{{t:resources.localCommandBuilder.vscodeTab}}" proporciona a integração mais rápida.

3. Clique no botão **{{t:common.vscodeSelection.open}}** quando o browser solicitar permissão.

![Permissão para abrir a aplicação de ambiente de trabalho](/assets/images/user-guide/75_desktop_open_page.png)
*(Figura 75: Browser a solicitar permissão para abrir a aplicação de ambiente de trabalho)*

> **Sugestão**: Se não pretender conceder permissão de cada vez que abre a aplicação de ambiente de trabalho, marque a opção "Permitir sempre".

---

## 2.7 Definições

Pode gerir o seu perfil e as definições do sistema na secção Definições.

### 2.7.1 Alterar Palavra-passe

![Demonstração de alteração de palavra-passe](/assets/videos/user-guide/02-07-03-password-change.webm)
*(Vídeo: Alterar a sua palavra-passe)*

1. Aceda ao separador **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}** no menu esquerdo.

![Página de definições do perfil](/assets/images/user-guide/76_profiles_button.png)
*(Figura 76: Página Definições > Perfil - definições de vault pessoal)*

2. Clique no botão **{{t:settings.personal.changePassword.submit}}**.

![Botão Alterar Palavra-passe](/assets/images/user-guide/77_profiles_change_button.png)
*(Figura 77: Botão "Alterar Palavra-passe" na secção de definições pessoais)*

3. Introduza a sua nova palavra-passe. Requisitos da palavra-passe:
   - Pelo menos 8 caracteres
   - Deve conter letras maiúsculas e minúsculas
   - Deve conter pelo menos um número
   - Deve conter pelo menos um carácter especial

4. Reintroduza a mesma palavra-passe no campo **{{t:settings.personal.changePassword.confirmPasswordLabel}}**.
5. Clique no botão **{{t:settings.personal.changePassword.submit}}**.

![Formulário de alteração de palavra-passe](/assets/images/user-guide/78_profiles_change_form.png)
*(Figura 78: Formulário de Alteração de Palavra-passe - requisitos de segurança visíveis)*

> **Sugestão**: Utilize combinações aleatórias ao criar uma palavra-passe robusta.

---

## 2.8 Armazenamento

A secção Armazenamento é onde define as localizações físicas onde os seus dados de backup ficam guardados.

### 2.8.1 Adicionar Armazenamento

![Demonstração de criação de armazenamento](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(Vídeo: Adicionar um local de armazenamento)*

1. Aceda ao separador **{{t:common.navigation.storage}}** no menu esquerdo.
2. Clique no botão **{{t:resources.storage.createStorage}}**.

![Botão Adicionar Armazenamento](/assets/images/user-guide/79_storage_add_button.png)
*(Figura 79: Página de gestão de armazenamento - botão "Adicionar Armazenamento")*

3. Preencha o formulário:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: Introduza um nome descritivo
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: Seleccione (por exemplo, s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: Adicione uma descrição opcional
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: Opcional
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: flags do rclone (por exemplo, --transfers 4)

![Formulário de criação de armazenamento](/assets/images/user-guide/80_storage_form.png)
*(Figura 80: Formulário de adição de armazenamento - nome, fornecedor, descrição e parâmetros)*

4. Clique no botão **{{t:common.actions.create}}**.

> **Sugestão**: Os parâmetros adicionais aceitam flags do rclone para optimizar o desempenho do armazenamento.

---

## 2.9 Credenciais

A secção Credenciais é onde gere os segredos que os seus repositórios utilizam para aceder a recursos externos.

### 2.9.1 Edição de Credenciais

![Demonstração de edição de credenciais](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(Vídeo: Editar credenciais)*

1. Aceda ao separador **{{t:common.navigation.credentials}}** no menu esquerdo.
2. Seleccione o registo que pretende editar.
3. Clique no botão **{{t:common.actions.edit}}**.

![Lista de credenciais](/assets/images/user-guide/81_credentials.png)
*(Figura 81: Página de credenciais - nomes de repositórios, equipas e botões de gestão)*

4. Altere o **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}** se necessário.
5. Guarde com o botão **{{t:common.save}}**.

![Formulário de edição de credencial](/assets/images/user-guide/82_credentials_form.png)
*(Figura 82: Formulário de edição do nome do repositório - campos de configuração de vault)*

> **Sugestão**: As credenciais são armazenadas de forma encriptada e apenas são desencriptadas durante a implementação.

### 2.9.2 Rastreio de Credenciais

![Demonstração de rastreio de credenciais](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(Vídeo: Ver o histórico de auditoria de credenciais)*

1. Seleccione o registo que pretende rastrear.
2. Clique no botão **{{t:common.actions.trace}}**.

![Botão de rastreio](/assets/images/user-guide/83_credentials_trace_button.png)
*(Figura 83: Botão "Rastrear" na tabela de Credenciais)*

3. Consulte o histórico de auditoria.
4. Seleccione o formato no botão **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** ou **{{t:common.exportJSON}}**.

![Histórico de auditoria de credenciais](/assets/images/user-guide/84_credentials_list_export.png)
*(Figura 84: Lista de credenciais - opções de exportação)*

> **Sugestão**: A funcionalidade de rastreio fornece o acompanhamento da utilização das credenciais para fins de auditoria de segurança.

### 2.9.3 Eliminação de Credenciais

![Demonstração de eliminação de credenciais](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(Vídeo: Eliminar uma credencial)*

1. Seleccione o registo que pretende eliminar.
2. Clique no botão vermelho **{{t:common.delete}}**.

![Botão de eliminação](/assets/images/user-guide/85_credentials_delete.png)
*(Figura 85: Botão vermelho "Eliminar" na página de Credenciais)*

3. Clique no botão **{{t:common.delete}}** na janela de confirmação.

![Confirmação de eliminação](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(Figura 86: Caixa de confirmação de eliminação - aviso de acção irreversível)*

> **Aviso**: Antes de eliminar, certifique-se de que a credencial não está a ser utilizada noutras máquinas ou operações. Garanta que tem um backup das credenciais críticas antes de eliminar.

---

## 2.10 Fila de Tarefas

A secção Fila de Tarefas acompanha as operações pendentes e concluídas em todo o sistema.

### 2.10.1 Operações na Fila de Tarefas

![Demonstração de operações na fila de tarefas](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(Vídeo: Gerir operações na fila de tarefas)*

1. Clique no separador **{{t:common.navigation.queue}}** no menu esquerdo.

![Página da fila de tarefas](/assets/images/user-guide/87_queue_button.png)
*(Figura 87: Página da fila de tarefas - opções de filtragem e separadores de estado)*

2. Para filtrar itens da fila:
   - Utilize os filtros **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}** e **{{t:queue.trace.bridge}}**
   - Especifique o **{{t:system.audit.filters.dateRange}}**
   - Marque a opção **{{t:queue.filters.onlyStale}}**

3. Veja os detalhes nos separadores de estado:
   - **{{t:queue.statusActive}}**: Tarefas em processamento
   - **{{t:queue.statusCompleted}}**: Tarefas concluídas com sucesso
   - **{{t:queue.statusCancelled}}**: Tarefas canceladas
   - **{{t:queue.statusFailed}}**: Tarefas com falha

4. Seleccione um formato no botão **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** ou **{{t:common.exportJSON}}**.

![Exportação da fila de tarefas](/assets/images/user-guide/88_queue_export.png)
*(Figura 88: Lista da fila de tarefas - opções de exportação)*

> **Sugestão**: A opção "{{t:queue.filters.onlyStale}}" ajuda a encontrar tarefas que estão em processamento há muito tempo. Exporte regularmente o histórico da fila para analisar as tendências de execução de tarefas.

---

## 2.11 Auditoria

A secção Auditoria mantém um registo de todas as operações executadas no sistema.

### 2.11.1 Registos de Auditoria

![Demonstração de registos de auditoria](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(Vídeo: Ver registos de auditoria do sistema)*

1. Clique no separador **{{t:common.navigation.audit}}** no menu esquerdo.

![Lista de auditoria](/assets/images/user-guide/89_audit_list.png)
*(Figura 89: Página de auditoria - registo detalhado de todas as operações do sistema)*

2. Filtre os registos de auditoria:
   - **Intervalo de Datas**: Filtrar por um período específico
   - **Tipo de Entidade**: Filtrar por Pedido, Máquina, Fila, etc.
   - **Pesquisa**: Efectuar pesquisa de texto

3. Consulte as informações de cada registo:
   - **Timestamp**: Data e hora da operação
   - **Acção**: Tipo de operação (Criar, Editar, Eliminar, etc.)
   - **Tipo de Entidade**: Tipo de objecto afectado
   - **Nome da Entidade**: Identificador do objecto específico
   - **Utilizador**: Utilizador que realizou a operação
   - **Detalhes**: Informações adicionais sobre a operação

4. Seleccione um formato no botão **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** ou **{{t:common.exportJSON}}**.

![Exportação de auditoria](/assets/images/user-guide/90_audit_export.png)
*(Figura 90: Exportação de registos de auditoria - opções CSV e JSON)*

> **Sugestão**: O registo de auditoria é fundamental para acompanhar toda a actividade do sistema para fins de segurança e conformidade. Exporte regularmente o registo de auditoria e armazene-o num local seguro.

---

**© 2025 Rediacc Platform - Todos os Direitos Reservados.**
