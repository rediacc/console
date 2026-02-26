---
title: 网页应用
description: 了解 Rediacc 网页应用的架构和部署
category: Reference
order: 1
language: zh
sourceHash: "ee9dff9ac2c8bce1"
---

# Rediacc 平台用户指南

## 概述

**Rediacc** 是一个提供 AI 驱动备份服务的云平台。

本指南介绍了网页界面 [https://www.rediacc.com/](https://www.rediacc.com/) 的基本使用方法。

### 本指南的目的

- 帮助新用户快速适应平台
- 逐步说明基本功能（资源管理、备份）

---

## 1. 账户创建和登录

### 1.1 注册

![Registration process walkthrough](/assets/videos/user-guide/01-01-registration.webm)
*(视频: Complete registration flow from start to finish)*

要开始使用 Rediacc 平台，您首先需要创建一个账户。

![Rediacc 登录页面 - 始终在线的基础设施](/assets/images/user-guide/01_login.png)
*（图 1：主登录页面，展示 Rediacc 平台的主要功能）*

1. 在浏览器中导航至 [https://www.rediacc.com/](https://www.rediacc.com/)。
2. 点击页面右上角的 **{{t:auth.login.signIn}}** 按钮。
3. 选择 **开始使用** 进行免费访问，或选择 **请求演示** 进行演示。

> **提示**：您可以创建免费账户，无需任何信用卡。包含 10 个 CPU 核心和无限团队。

![Rediacc 登录表单 - 邮箱和密码字段](/assets/images/user-guide/02_register.png)
*（图 2：现有用户的登录屏幕）*

4. 如果您没有账户，点击 **{{t:auth.login.register}}** 链接创建新账户。

5. 在打开的表单中填写以下信息：
   - **{{t:auth.registration.organizationName}}**：输入您的组织名称
   - **{{t:auth.login.email}}**：输入有效的电子邮件地址
   - **{{t:auth.login.password}}**：创建至少 8 个字符的密码
   - **{{t:auth.registration.passwordConfirm}}**：重新输入相同的密码

![创建账户模态框 - 注册、验证和完成步骤](/assets/images/user-guide/03_create_account.png)
*（图 3：新用户注册分步表单 - 注册 > 验证 > 完成）*

6. 勾选复选框以接受服务条款和隐私政策。
7. 点击 **{{t:auth.registration.createAccount}}** 按钮。

> **提示**：密码必须至少 8 个字符且应足够强。所有字段都是必填的。

8. 在方框中依次输入发送到您邮箱的 6 位验证码。
9. 点击 **{{t:auth.registration.verifyAccount}}** 按钮。

![验证码输入 - 6 位激活码](/assets/images/user-guide/04_verification_code.png)
*（图 4：输入发送给管理员的激活码的窗口）*

> **提示**：验证码有效期有限。如果未收到验证码，请检查垃圾邮件文件夹。

---

### 1.2 登录

![Sign in process walkthrough](/assets/videos/user-guide/01-02-login.webm)
*(视频: Complete sign in flow)*

创建账户后，您可以登录平台。

1. 填写 **{{t:auth.login.email}}** 字段（如果出现红色警告则必填）。
2. 填写 **{{t:auth.login.password}}** 字段。
3. 点击 **{{t:auth.login.signIn}}** 按钮。

![登录表单 - 带错误警告的必填字段](/assets/images/user-guide/05_sign_in.png)
*（图 5：登录表单 - 错误消息用红色边框标记）*

> **提示**：如果错误消息显示"此字段为必填项"，请填写空白字段。如忘记密码，请联系管理员。

4. 成功登录后，您将被重定向到 **{{t:common.navigation.dashboard}}** 屏幕。

![Rediacc 仪表板 - 机器列表和侧边栏菜单](/assets/images/user-guide/06_dashboard.png)
*（图 6：成功登录后的主仪表板 - 左侧边栏中的组织、机器和设置菜单）*

> **提示**：仪表板自动刷新。您可以按 F5 刷新页面以获取最新信息。

---

## 2. 界面概览

登录后，您看到的屏幕由以下主要部分组成：

- **{{t:common.navigation.organization}}**：用户、团队和访问控制
- **{{t:common.navigation.machines}}**：服务器和仓库管理
- **{{t:common.navigation.settings}}**：个人资料和系统设置
- **{{t:common.navigation.storage}}**：存储区域管理
- **{{t:common.navigation.credentials}}**：访问凭证
- **{{t:common.navigation.queue}}**：作业队列管理
- **{{t:common.navigation.audit}}**：系统审计日志

---

## 2.1 组织 - 用户

用户管理允许您控制组织中人员对平台的访问。

### 2.1.1 添加用户

![Adding users walkthrough](/assets/videos/user-guide/02-01-01-user-create.webm)
*(视频: Creating a new user)*

1. 在左侧边栏中点击 **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** 选项。
2. 以表格格式查看所有用户的列表。
3. 每个用户行显示电子邮件、状态（{{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}）、权限组和最后活动时间。

![用户管理页面 - 活动用户列表](/assets/images/user-guide/07_users.png)
*（图 7：组织下的用户部分 - 显示所有用户的信息）*

4. 点击右上角的 **"+"** 图标。
5. 点击 **{{t:organization.users.modals.createTitle}}** 按钮并填写打开的表单：
   - **{{t:organization.users.form.emailLabel}}**：输入用户的电子邮件地址
   - **{{t:organization.users.form.passwordLabel}}**：输入临时密码

![用户创建模态框 - 邮箱和密码字段](/assets/images/user-guide/08_user_add.png)
*（图 8：添加新用户的模态窗口 - 简单快速的用户创建表单）*

6. 点击 **{{t:common.actions.create}}** 按钮。

> **提示**：应安全地将登录凭证传达给创建的用户。建议首次登录时更改密码。

![用户列表 - 包含三个用户的完整表格视图](/assets/images/user-guide/09_user_list.png)
*（图 9：用户管理页面上的所有活动和非活动用户）*

> **提示**：页面自动显示 20 条记录。使用分页查看更多记录。

### 2.1.2 分配用户权限

![User permissions walkthrough](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(视频: Assigning permission groups to users)*

您可以通过向用户分配特定权限组来管理访问权限。

1. 从 **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** 标签中选择用户。
2. 点击操作列中的盾牌图标（**{{t:organization.access.tabs.permissions}}**）。

![权限管理 - 盾牌、齿轮和删除图标](/assets/images/user-guide/10_users_permissions.png)
*（图 10：用户操作的图标显示 - 每个图标代表不同的操作）*

3. 从打开的表单中选择 **{{t:organization.users.modals.permissionGroupLabel}}**。
4. 组中的用户数量和权限数量显示在用户旁边。
5. 点击 **{{t:organization.users.modals.assignTitle}}** 按钮保存更改。

![权限分配模态框 - 管理员组](/assets/images/user-guide/11_user_permissions_form.png)
*（图 11：为选定用户分配权限组的模态框 - 包含可用组的下拉菜单）*

> **提示**：某些权限组由系统固定，无法更改。

### 2.1.3 用户激活

![User activation walkthrough](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(视频: Activating an inactive user)*

您可以重新激活已禁用的用户。

1. 在 **用户** 列表中找到状态为非活动的用户。
2. 点击操作列中的红色图标。

![用户激活 - "激活"工具提示视图](/assets/images/user-guide/12_users_activation.png)
*（图 12：激活非活动用户）*

3. 在确认窗口中点击 **{{t:common.general.yes}}** 按钮。

![激活确认模态框](/assets/images/user-guide/13_users_activation_confirm.png)
*（图 13：确认用户激活的模态窗口）*

> **提示**：此操作是可逆的。您可以以相同方式停用用户。

### 2.1.4 用户追踪

![User trace walkthrough](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(视频: Viewing user activity trace)*

您可以使用追踪功能监控用户活动。

1. 选择用户并点击操作列中的齿轮图标。
2. 点击 **{{t:common.actions.trace}}** 选项打开用户的活动历史记录。

![用户追踪 - 带操作按钮的"追踪"工具提示](/assets/images/user-guide/14_users_trace.png)
*（图 14：用户活动追踪选项）*

3. 用户的过去活动列在打开的屏幕上。
4. 顶部显示统计信息：总记录数、已查看记录数、最后活动。
5. 点击 **{{t:common.actions.export}}** 按钮并选择格式：**{{t:common.exportCSV}}** 或 **{{t:common.exportJSON}}**。

![审计历史 - 导出选项](/assets/images/user-guide/15_user_trace_export.png)
*（图 15：用户的完整活动历史 - 统计、详细信息和导出选项）*

> **提示**：定期导出审计数据以维护安全和合规记录。CSV 格式可在 Excel 中打开。

---

## 2.2 组织 - 团队

团队允许您对用户进行分组并提供对资源的批量访问。

### 2.2.1 创建团队

![Creating teams walkthrough](/assets/videos/user-guide/02-02-01-team-create.webm)
*(视频: Creating a new team)*

1. 转到 **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}** 标签。
2. 点击 **"+"** 按钮。
3. 在 **{{t:common.vaultEditor.fields.TEAM.name.label}}** 字段中输入您的团队名称。
4. 在 **{{t:common.vaultEditor.vaultConfiguration}}** 部分填写 **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** 和 **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** 字段。

![新团队创建表单 - 团队名称和 SSH 密钥](/assets/images/user-guide/16_teams_create.png)
*（图 16：在"私有团队"内创建新团队）*

5. 点击 **{{t:common.actions.create}}** 按钮保存团队。

> **提示**：SSH 密钥是 Bridge SSH 身份验证所必需的。如果收到缺少密钥警告，请提供两个密钥。

### 2.2.2 团队编辑

![Team editing walkthrough](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(视频: Editing team information)*

1. 在团队列表中点击要编辑的团队旁边的铅笔图标。
2. 如需要，在 **{{t:common.vaultEditor.fields.TEAM.name.label}}** 字段中更改团队名称。
3. 在 **{{t:common.vaultEditor.vaultConfiguration}}** 部分更新 SSH 密钥。
4. 点击 **{{t:common.save}}** 按钮应用更改。

![团队编辑表单 - 蓝色信息消息](/assets/images/user-guide/17_teams_edit_form.png)
*（图 17：编辑现有团队的信息）*

> **提示**：团队配置用于组织结构。更改对所有团队成员生效。

### 2.2.3 团队成员管理

![Team members management walkthrough](/assets/videos/user-guide/02-02-03-team-members.webm)
*(视频: Managing team members)*

1. 选择团队并点击用户图标。
2. 在 **{{t:organization.teams.manageMembers.currentTab}}** 标签页中查看已分配给团队的成员。
3. 切换到 **{{t:organization.teams.manageMembers.addTab}}** 标签页。
4. 输入电子邮件地址或从下拉菜单中选择用户。
5. 点击 **"+"** 按钮将成员添加到团队。

![团队成员管理表单 - "当前成员"和"添加成员"标签](/assets/images/user-guide/18_teams_members_form.png)
*（图 18：团队成员管理面板）*

> **提示**：您可以将同一成员分配给多个团队。

### 2.2.4 团队追踪

![Team trace walkthrough](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(视频: Viewing team audit history)*

1. 选择要追踪的团队。
2. 点击时钟/历史图标。
3. 在 **{{t:resources.audit.title}}** 模态窗口中查看总记录数、已查看记录数和最后活动计数。
4. 点击 **{{t:common.actions.export}}** 按钮以 {{t:common.exportCSV}} 或 {{t:common.exportJSON}} 格式导出。

![审计历史模态框 - DataBassTeam 团队](/assets/images/user-guide/19_teams_trace.png)
*（图 19：查看团队审计历史）*

> **提示**：审计历史对于合规和安全控制很重要。

### 2.2.5 团队删除

![Team deletion walkthrough](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(视频: Deleting a team)*

1. 点击要删除的团队旁边的垃圾桶（红色）图标。
2. 在确认对话框中验证团队名称正确。
3. 点击 **{{t:common.general.yes}}** 按钮。

![团队删除确认对话框](/assets/images/user-guide/20_teams_delete.png)
*（图 20：团队删除确认）*

> **警告**：团队删除不可逆。删除前请检查团队中是否有重要数据。

---

## 2.3 组织 - 访问控制

访问控制允许您通过创建权限组来集中管理用户权限。

### 2.3.1 创建权限组

![Permission group creation walkthrough](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(视频: Creating a permission group)*

1. 转到 **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}** 标签。
2. 点击 **"+"** 按钮。
3. 在 **{{t:organization.access.modals.groupPlaceholder}}** 字段中输入有意义的名称。
4. 点击 **{{t:common.actions.confirm}}** 按钮创建组。

![权限组创建表单](/assets/images/user-guide/21_create_access.png)
*（图 21：创建新的权限组）*

> **提示**：权限组用于组织具有相似权限的用户。保持组名称描述性（例如，"管理员"、"只读"、"仓库管理员"）。

### 2.3.2 权限管理

![Permission management walkthrough](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(视频: Managing permissions for a group)*

1. 选择权限组并点击 **{{t:organization.access.modals.managePermissionsTitle}}** 选项。
2. 在 **{{t:organization.access.modals.currentPermissionsTab}}** 标签页中查看组的访问权限。
3. 您可以通过点击每个操作旁边的红色 **{{t:common.delete}}** 按钮来撤销权限。
4. 点击 **{{t:organization.access.modals.addPermissionsTab}}** 标签页向组添加新权限。

![权限管理面板 - 分配的权限列表](/assets/images/user-guide/22_access_permission.png)
*（图 22：管理权限组的权限）*

> **提示**：根据最小权限原则授予权限。定期审查并删除不必要的权限。

---

## 2.4 机器

机器部分允许您管理服务器和仓库资源。

### 2.4.1 添加机器

![Adding machines walkthrough](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(视频: Adding a new machine)*

1. 从左侧菜单转到 **{{t:common.navigation.machines}}** 标签。
2. 点击右上角的 **{{t:machines.createMachine}}** 按钮。

![机器页面 - "添加机器"按钮](/assets/images/user-guide/23_machines_add.png)
*（图 23：机器管理主页）*

3. 填写打开的表单：
   - **{{t:machines.machineName}}**：输入唯一名称（例如，"server-01"）
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**：输入机器 IP 地址（例如，192.168.111.11）
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**：指定存储目录（例如，/mnt/rediacc）
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**：输入 SSH 用户名
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**：输入端口号（默认：22）
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**：输入密码（可选）

![机器添加表单 - 所有字段](/assets/images/user-guide/24_machine_create.png)
*（图 24：新机器添加表单 - 机器名称、网络设置、SSH 凭证）*

4. 点击 **{{t:common.vaultEditor.testConnection.button}}** 按钮验证连接。
5. 测试成功后，点击 **{{t:common.actions.create}}** 按钮。

> **提示**：如果选中"机器创建后自动开始设置"选项，机器将自动执行其他设置步骤。

![机器创建完成 - 任务追踪窗口](/assets/images/user-guide/25_machine_create_complete.png)
*（图 25：机器成功创建后的任务追踪窗口）*

6. 观察阶段：**{{t:queue.trace.assigned}}** → **处理中** → **{{t:queue.statusCompleted}}**
7. 点击 **{{t:common.actions.close}}** 按钮关闭操作。

> **提示**：点击"{{t:common.actions.refresh}}"按钮手动检查最新状态。

### 2.4.2 连接测试

![Connectivity test walkthrough](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(视频: Running a connectivity test)*

您可以检查现有机器的连接状态。

1. 点击 **{{t:machines.connectivityTest}}** 按钮。

![连接测试按钮](/assets/images/user-guide/26_connectivity_test_button.png)
*（图 26：机器操作工具栏中的连接测试按钮）*

2. 查看要测试的机器列表。
3. 点击 **{{t:machines.runTest}}** 按钮。
4. 成功结果显示为绿色，失败显示为红色。

![连接测试表单 - 机器列表](/assets/images/user-guide/27_connectivity_test_form.png)
*（图 27：连接测试表单 - 选定机器的 ping 功能）*

> **提示**：如果测试失败，请检查机器 IP 地址和 SSH 设置。

### 2.4.3 刷新机器列表

![Machine list refresh walkthrough](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(视频: Refreshing the machine list)*

点击 **{{t:common.actions.refresh}}** 按钮更新机器列表。

![刷新按钮](/assets/images/user-guide/28_refresh.png)
*（图 28：机器操作工具栏中的刷新按钮）*

### 2.4.4 机器详情

![Machine details walkthrough](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(视频: Viewing machine details)*

1. 选择要查看详情的机器。
2. 点击眼睛图标按钮（**{{t:common.viewDetails}}**）。

![查看详情按钮](/assets/images/user-guide/29_view_details_button.png)
*（图 29：机器操作列中的眼睛图标）*

3. 右侧打开机器详情面板：
   - **主机名**：机器名称
   - **运行时间**：系统运行时间
   - **{{t:queue.trace.operatingSystem}}**：操作系统和版本
   - **{{t:queue.trace.kernelVersion}}**：内核版本
   - **处理器**：处理器信息
   - **系统时间**：系统时钟

![机器详情面板 - 系统信息](/assets/images/user-guide/30_machine_view_details.png)
*（图 30：机器详情面板 - 主机名、运行时间、操作系统、内核、CPU 信息）*

> **提示**：定期查看此信息以检查操作系统兼容性和资源可用性。

### 2.4.5 机器编辑

![Machine editing walkthrough](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(视频: Editing machine settings)*

1. 选择要编辑的机器。
2. 点击铅笔图标按钮（**{{t:common.actions.edit}}**）。

![编辑按钮](/assets/images/user-guide/31_edit_button.png)
*（图 31：机器操作列中的铅笔图标）*

3. 进行必要的更改。
4. 点击 **{{t:common.vaultEditor.testConnection.button}}** 按钮。
5. 连接成功后，点击 **{{t:common.save}}** 按钮。

![机器编辑表单](/assets/images/user-guide/32_edit_form.png)
*（图 32：机器编辑表单 - 机器名称、区域和保险库配置）*

> **提示**：更改关键设置后务必运行"测试连接"。

### 2.4.6 机器追踪

![Machine trace walkthrough](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(视频: Viewing machine audit history)*

1. 选择机器并点击时钟图标按钮（**{{t:common.actions.trace}}**）。

![追踪按钮](/assets/images/user-guide/33_trace_button.png)
*（图 33：机器操作列中的时钟图标）*

2. 在审计历史窗口中查看操作：
   - **{{t:resources.audit.action}}**：执行的操作类型
   - **详情**：更改的字段
   - **{{t:resources.audit.performedBy}}**：执行操作的用户
   - **时间戳**：日期和时间

![机器审计历史窗口](/assets/images/user-guide/34_trace_list.png)
*（图 34：审计历史 - 所有更改的列表）*

> **提示**：点击时间戳列按时间顺序查看更改。

### 2.4.7 机器删除

![Machine deletion walkthrough](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(视频: Deleting a machine)*

1. 选择要删除的机器。
2. 点击垃圾桶图标按钮（**{{t:common.delete}}**）。

![删除按钮](/assets/images/user-guide/35_delete_button.png)
*（图 35：机器操作列中的垃圾桶图标）*

3. 在确认窗口中点击 **{{t:common.delete}}** 按钮。

![机器删除确认窗口](/assets/images/user-guide/36_delete_form.png)
*（图 36："您确定要删除此机器吗？"确认窗口）*

> **警告**：删除机器时，其上的所有仓库定义也会被删除。此操作不可逆。

### 2.4.8 远程操作

![Remote operations walkthrough](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(视频: Running remote operations on a machine)*

您可以在机器上执行各种远程操作。

1. 选择机器并点击 **{{t:common.actions.remote}}** 按钮。
2. 在下拉菜单中查看选项：
   - **{{t:machines.runAction}}**：在机器上执行函数
   - **{{t:common.vaultEditor.testConnection.button}}**：Ping 机器

![远程菜单 - 在服务器上运行和测试连接](/assets/images/user-guide/37_remote_button.png)
*（图 37：远程按钮 - 在选定机器上执行函数菜单）*

> **提示**：使用 "{{t:common.vaultEditor.testConnection.button}}" 选项在运行函数前验证机器是否可访问。

#### 设置

1. 选择 **{{t:machines.runAction}}** 选项。
2. 在 **{{t:functions.availableFunctions}}** 列表中找到 **设置** 函数。
3. 点击函数名称选择它。

![机器函数列表 - setup 函数](/assets/images/user-guide/38_server_setup.png)
*（图 38：设置函数 - 使用所需工具和配置准备机器）*

> **提示**：设置新机器时建议首先运行"设置"函数。

#### 连接检查（你好）

1. 选择 **{{t:machines.runAction}}** > **你好** 函数。
2. 点击 **{{t:common.actions.addToQueue}}** 按钮。

![你好函数选择](/assets/images/user-guide/39_remote_hello.png)
*（图 39：你好函数 - 简单测试函数，返回主机名）*

3. 在任务追踪窗口中观察结果。
4. 在 **{{t:queue.trace.responseConsole}}** 部分查看机器的输出。

![你好函数完成](/assets/images/user-guide/40_remote_hello_complete.png)
*（图 40：你好函数成功完成 - 主机名响应）*

> **提示**：Hello 函数是验证机器连接的理想选择。

#### 高级操作

1. 按照 **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}** 路径操作。
2. 查看可用函数：setup、hello、ping、ssh_test、uninstall
3. 选择所需函数并点击 **{{t:common.actions.addToQueue}}** 按钮。

![高级函数列表](/assets/images/user-guide/41_remote_advanced.png)
*（图 41：高级选项 - 高级函数列表）*

> **提示**：使用高级函数前确保机器设置已完成。

#### 快速连接测试

![远程菜单 - 测试连接](/assets/images/user-guide/42_connectivity_test.png)
*（图 42：从远程菜单选择测试连接选项）*

> **提示**：如果机器有 SSH 或网络问题，您可以通过此测试快速识别问题。

---

## 2.5 仓库创建和操作

仓库是存储备份数据的基本单元。

### 2.5.1 创建仓库

![Repository creation walkthrough](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(视频: Creating a new repository)*

1. 从 **{{t:common.navigation.machines}}** 标签中选择机器。
2. 点击右上角的 **{{t:machines.createRepository}}** 按钮。

![创建仓库按钮](/assets/images/user-guide/43_create_repo_add.png)
*（图 43：机器仓库管理屏幕 - 创建仓库按钮）*

3. 填写表单：
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**：输入仓库名称（例如，postgresql）
   - **{{t:resources.repositories.size}}**：输入仓库大小（例如，2GB）
   - **{{t:resources.repositories.repositoryGuid}}**：查看自动生成的凭证
   - **{{t:resources.templates.selectTemplate}}**：选择模板（例如，databases_postgresql）

![仓库创建表单](/assets/images/user-guide/44_repo_form.png)
*（图 44：仓库创建表单 - 仓库名称、大小和模板选择）*

4. 点击 **{{t:common.actions.create}}** 按钮。

> **提示**：凭证 ID 自动生成，不建议手动修改。

5. 在任务追踪窗口中观察阶段：**{{t:queue.trace.assigned}}** → **处理中** → **{{t:queue.statusCompleted}}**

![仓库创建完成](/assets/images/user-guide/45_repo_complete.png)
*（图 45：仓库创建已排队 - 任务监控）*

6. 点击 **{{t:common.actions.close}}** 按钮。

> **提示**：任务通常在 1-2 分钟内完成。

![仓库列表](/assets/images/user-guide/46_repo_list.png)
*（图 46：创建的仓库出现在列表中）*

### 2.5.2 仓库分叉

![Repository fork walkthrough](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(视频: Forking a repository)*

您可以通过复制现有仓库来创建新仓库。

1. 选择要复制的仓库。
2. 点击 **fx**（函数）菜单。
3. 点击 **fork** 选项。

![fx 菜单 - fork 选项](/assets/images/user-guide/47_fork_button.png)
*（图 47：右侧的 fx 菜单 - 仓库操作）*

4. 在 **{{t:functions.functions.fork.params.tag.label}}** 字段中输入新标签（例如，2025-12-06-20-37-08）。
5. 点击 **{{t:common.actions.addToQueue}}** 按钮。

![Fork 配置表单](/assets/images/user-guide/48_fork_form.png)
*（图 48：在 fork 操作中为仓库指定新标签）*

6. 等待 **{{t:queue.statusCompleted}}** 消息并点击 **{{t:common.actions.close}}** 按钮。

![Fork 完成](/assets/images/user-guide/49_repo_completed.png)
*（图 49：Fork 操作成功完成）*

> **提示**：以默认日期时间格式创建标签是良好做法。fork 操作不影响原始仓库。

### 2.5.3 仓库启动

![Repository up walkthrough](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(视频: Starting a repository)*

激活仓库：

1. 选择仓库并按照 **fx** > **up** 路径。

![Up 操作](/assets/images/user-guide/50_repo_up.png)
*（图 50：从 fx 菜单选择"up"选项 - 启动仓库）*

2. 等待 **{{t:queue.statusCompleted}}** 消息。

![Up 完成](/assets/images/user-guide/51_repo_up_complete.png)
*（图 51：仓库启动完成）*

> **提示**："Up"操作启动仓库定义的 Docker 服务。

### 2.5.4 仓库停止

![Repository down walkthrough](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(视频: Stopping a repository)*

停止活动仓库：

1. 选择仓库并按照 **fx** > **down** 路径。

![Down 操作](/assets/images/user-guide/52_down_button.png)
*（图 52：从 fx 菜单选择"down"选项 - 关闭仓库）*

2. 等待 **{{t:queue.statusCompleted}}** 消息。

![Down 完成](/assets/images/user-guide/53_down_completed.png)
*（图 53：仓库关闭完成）*

> **提示**："Down"操作安全地关闭仓库。不会丢失数据，仅停止服务。

### 2.5.5 部署

![Repository deploy walkthrough](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(视频: Deploying a repository)*

将仓库部署到不同位置：

1. 选择仓库并按照 **fx** > **deploy** 路径。

![Deploy 操作](/assets/images/user-guide/54_deploy_button.png)
*（图 54：从 fx 菜单选择"deploy"选项）*

2. 在 **{{t:functions.functions.fork.params.tag.label}}** 字段中输入要部署的版本。
3. 在 **{{t:functions.functions.backup_deploy.params.machines.label}}** 字段中选择目标机器。
4. 勾选 **{{t:functions.checkboxOptions.overrideExistingFile}}** 选项（如适用）。
5. 点击 **{{t:common.actions.addToQueue}}** 按钮。

![Deploy 表单](/assets/images/user-guide/55_deploy_form.png)
*（图 55：配置部署操作 - 标签、目标机器和选项）*

6. 等待 **{{t:queue.statusCompleted}}** 消息。

![Deploy 完成](/assets/images/user-guide/56_deploy_completed.png)
*（图 56：仓库部署完成）*

> **提示**：部署操作完成后，您可以在目标机器上运行"up"命令启动仓库。

### 2.5.6 备份

![Repository backup walkthrough](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(视频: Backing up a repository)*

备份仓库：

1. 选择仓库并按照 **fx** > **backup** 路径。

![Backup 操作](/assets/images/user-guide/57_backup_button.png)
*（图 57：从 fx 菜单选择"backup"选项）*

2. 填写表单：
   - **{{t:functions.functions.fork.params.tag.label}}**：输入描述性名称（例如，backup01012025）
   - **{{t:functions.functions.backup_create.params.storages.label}}**：选择备份位置
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**：启用或禁用该选项
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**：查看设置

![Backup 表单](/assets/images/user-guide/58_backup_form.png)
*（图 58：备份配置表单 - 目标、文件名和选项）*

3. 点击 **{{t:common.actions.addToQueue}}** 按钮。

> **提示**：为备份标签使用描述性名称。对于大型仓库考虑启用检查点。

4. 等待 **{{t:queue.statusCompleted}}** 消息。

![Backup 完成](/assets/images/user-guide/59_backup_completed.png)
*（图 59：备份任务成功完成）*

> **提示**：在达到完成状态前耐心等待；大型备份可能需要几分钟。

### 2.5.7 模板应用

![Template application walkthrough](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(视频: Applying a template to a repository)*

向仓库应用新模板：

1. 选择仓库并按照 **fx** > **{{t:resources.templates.selectTemplate}}** 路径。

![模板操作](/assets/images/user-guide/60_templates_button.png)
*（图 60：从 fx 菜单选择"模板"选项）*

2. 在搜索框中输入以过滤模板。
3. 点击所需模板选择它（选定的模板以粗边框突出显示）。
4. 点击 **{{t:common.actions.addToQueue}}** 按钮。

![模板选择表单](/assets/images/user-guide/61_templates_form.png)
*（图 61：搜索和选择可用模板）*

> **提示**：使用搜索框快速查找模板。使用 "{{t:common.viewDetails}}" 了解模板功能。

5. 等待 **{{t:queue.statusCompleted}}** 消息。

![模板已应用](/assets/images/user-guide/62_templates_completed.png)
*（图 62：模板应用成功完成）*

### 2.5.8 卸载

![Repository unmount walkthrough](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(视频: Unmounting a repository)*

断开仓库连接：

1. 选择仓库并按照 **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}** 路径操作。

![Unmount 操作](/assets/images/user-guide/63_unmount_button.png)
*（图 63：高级菜单中的"Unmount"选项）*

2. 等待 **{{t:queue.statusCompleted}}** 消息。

![Unmount 完成](/assets/images/user-guide/64_unmount_completed.png)
*（图 64：卸载操作完成）*

> **提示**：卸载前确保仓库上没有活动操作。卸载后，仓库变得不可访问。

### 2.5.9 扩展

![Repository expand walkthrough](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(视频: Expanding repository size)*

增加仓库大小：

1. 选择仓库并按照 **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}** 路径操作。

![Expand 操作](/assets/images/user-guide/65_expand_button.png)
*（图 65：高级菜单中的"Expand"选项）*

2. 在 **{{t:functions.functions.repository_expand.params.size.label}}** 字段中输入所需大小。
3. 从右侧下拉菜单中选择单位（GB、TB）。
4. 点击 **{{t:common.actions.addToQueue}}** 按钮。

![Expand 表单](/assets/images/user-guide/66_expand_form.png)
*（图 66：用于增加仓库大小的新大小参数）*

> **提示**：不要输入小于当前大小的值。仓库扩展期间不会中断服务。

5. 等待 **{{t:queue.statusCompleted}}** 消息。

![Expand 完成](/assets/images/user-guide/67_expand_completed.png)
*（图 67：仓库扩展完成）*

### 2.5.10 重命名

![Repository rename walkthrough](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(视频: Renaming a repository)*

更改仓库名称：

1. 选择仓库并按照 **fx** > **{{t:common.actions.rename}}** 路径操作。

![Rename 操作](/assets/images/user-guide/68_rename_button.png)
*（图 68：从 fx 菜单选择"Rename"选项）*

2. 输入新的仓库名称。
3. 点击 **{{t:common.save}}** 按钮。

![Rename 表单](/assets/images/user-guide/69_rename_form.png)
*（图 69：输入新仓库名称的对话框）*

> **提示**：仓库名称应有意义以反映仓库类型和用途。避免使用特殊字符。

### 2.5.11 仓库删除

![Repository deletion walkthrough](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(视频: Deleting a repository)*

永久删除仓库：

1. 选择仓库并按照 **fx** > **{{t:resources.repositories.deleteRepository}}** 路径操作。

![删除仓库操作](/assets/images/user-guide/70_delete_repo_button.png)
*（图 70：从 fx 菜单选择"删除仓库"选项 - 红色）*

2. 在确认窗口中点击 **{{t:common.delete}}** 按钮。

> **警告**：仓库删除不可逆。删除前确保仓库数据已备份。

### 2.5.12 仓库详情

![Repository details walkthrough](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(视频: Viewing repository details)*

获取有关仓库的详细信息：

1. 选择仓库。
2. 点击眼睛图标（**{{t:common.viewDetails}}**）。

![查看详情按钮](/assets/images/user-guide/71_repo_view_button.png)
*（图 71：打开仓库详情的眼睛图标）*

3. 在详情面板中查看信息：
   - **仓库名称** 和类型
   - **团队**：所属团队
   - **机器**：所在机器
   - **保险库版本**：加密版本
   - **仓库 GUID**：唯一标识符
   - **状态**：挂载/卸载状态
   - **镜像大小**：总大小
   - **时间戳**：最后修改日期

![仓库详情面板](/assets/images/user-guide/72_repo_details_view.png)
*（图 72：有关选定仓库的全面信息）*

> **提示**：此面板中显示的所有信息仅供参考。使用 fx 菜单选项进行仓库操作。

---

## 2.6 仓库连接操作

您可以使用不同方法连接到仓库。

### 2.6.1 桌面应用程序连接

![Desktop connection walkthrough](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(视频: Connecting via desktop application)*

1. 点击仓库行中的 **{{t:resources.localActions.local}}** 按钮。

![本地连接按钮](/assets/images/user-guide/73_repo_connection_local.png)
*（图 73：仓库行中的"Local"按钮 - 桌面应用程序访问）*

2. 从下拉菜单中选择访问方法：
   - **{{t:resources.localActions.openInDesktop}}**：使用图形界面访问
   - **{{t:resources.localCommandBuilder.vscodeTab}}**：在代码编辑器中打开
   - **{{t:common.terminal.terminal}}**：通过命令行访问
   - **{{t:resources.localActions.showCLICommands}}**：命令行工具

![连接选项菜单](/assets/images/user-guide/74_repo_connection.png)
*（图 74：仓库连接菜单 - 不同的访问路径）*

> **提示**：如果使用 VS Code 工作，"{{t:resources.localCommandBuilder.vscodeTab}}" 选项提供最快的集成。

3. 当浏览器请求权限时，点击 **{{t:common.vscodeSelection.open}}** 按钮。

![桌面应用程序打开权限](/assets/images/user-guide/75_desktop_open_page.png)
*（图 75：浏览器请求打开桌面应用程序的权限）*

> **提示**：如果您不想每次打开桌面应用程序时都授予权限，请勾选"始终允许"选项。

---

## 2.7 设置

您可以从设置部分管理个人资料和系统设置。

### 2.7.1 更改密码

![Password change walkthrough](/assets/videos/user-guide/02-07-03-password-change.webm)
*(视频: Changing your password)*

1. 从左侧菜单转到 **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}** 标签。

![个人资料设置页面](/assets/images/user-guide/76_profiles_button.png)
*（图 76：设置 → 个人资料页面 - 个人保险库设置）*

2. 点击 **{{t:settings.personal.changePassword.submit}}** 按钮。

![更改密码按钮](/assets/images/user-guide/77_profiles_change_button.png)
*（图 77：个人设置部分中的"更改密码"按钮）*

3. 输入新密码。密码要求：
   - 至少 8 个字符长
   - 必须包含大小写字母
   - 必须包含至少一个数字
   - 必须包含至少一个特殊字符

4. 在 **{{t:settings.personal.changePassword.confirmPasswordLabel}}** 字段中重新输入相同的密码。
5. 点击 **{{t:settings.personal.changePassword.submit}}** 按钮。

![密码更改表单](/assets/images/user-guide/78_profiles_change_form.png)
*（图 78：更改密码表单 - 安全要求可见）*

> **提示**：创建强密码时使用随机组合。

---

## 2.8 存储

存储部分允许您管理备份数据将存储的物理区域。

### 2.8.1 添加存储

![Storage creation walkthrough](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(视频: Adding a storage location)*

1. 从左侧菜单转到 **{{t:common.navigation.storage}}** 标签。
2. 点击 **{{t:resources.storage.createStorage}}** 按钮。

![添加存储按钮](/assets/images/user-guide/79_storage_add_button.png)
*（图 79：存储管理页面 - "添加存储"按钮）*

3. 填写表单：
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**：输入描述性名称
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**：选择（例如，s3）
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**：添加可选描述
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**：可选
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**：rclone 标志（例如，--transfers 4）

![存储创建表单](/assets/images/user-guide/80_storage_form.png)
*（图 80：添加存储表单 - 名称、提供商、描述和参数）*

4. 点击 **{{t:common.actions.create}}** 按钮。

> **提示**：附加参数接受 rclone 标志以优化存储性能。

---

## 2.9 凭证

凭证部分允许您安全地管理仓库的访问信息。

### 2.9.1 凭证编辑

![Credential editing walkthrough](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(视频: Editing credentials)*

1. 从左侧菜单转到 **{{t:common.navigation.credentials}}** 标签。
2. 选择要编辑的记录。
3. 点击 **{{t:common.actions.edit}}** 按钮。

![凭证列表](/assets/images/user-guide/81_credentials.png)
*（图 81：凭证页面 - 仓库名称、团队和管理按钮）*

4. 如需要，更改 **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**。
5. 使用 **{{t:common.save}}** 按钮保存。

![凭证编辑表单](/assets/images/user-guide/82_credentials_form.png)
*（图 82：编辑仓库名称表单 - 保险库配置字段）*

> **提示**：凭证以加密方式存储，仅在部署期间解密。

### 2.9.2 凭证追踪

![Credential trace walkthrough](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(视频: Viewing credential audit history)*

1. 选择要追踪的记录。
2. 点击 **{{t:common.actions.trace}}** 按钮。

![追踪按钮](/assets/images/user-guide/83_credentials_trace_button.png)
*（图 83：凭证表中的"追踪"按钮）*

3. 查看审计历史。
4. 从 **{{t:common.actions.export}}** 按钮选择格式：**{{t:common.exportCSV}}** 或 **{{t:common.exportJSON}}**。

![凭证审计历史](/assets/images/user-guide/84_credentials_list_export.png)
*（图 84：凭证列表 - 导出选项）*

> **提示**：追踪功能为安全审计目的提供凭证使用追踪。

### 2.9.3 凭证删除

![Credential deletion walkthrough](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(视频: Deleting a credential)*

1. 选择要删除的记录。
2. 点击红色 **{{t:common.delete}}** 按钮。

![删除按钮](/assets/images/user-guide/85_credentials_delete.png)
*（图 85：凭证页面上的红色"删除"按钮）*

3. 在确认窗口中点击 **{{t:common.delete}}** 按钮。

![删除确认](/assets/images/user-guide/86_credentials_delete_confirm.png)
*（图 86：删除确认对话框 - 不可逆操作警告）*

> **警告**：删除前，确保凭证未在其他机器或其他操作中使用。删除前确保您有关键凭证的备份。

---

## 2.10 队列

队列部分允许您跟踪系统中的待处理和已完成操作。

### 2.10.1 队列操作

![Queue operations walkthrough](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(视频: Managing queue operations)*

1. 从左侧菜单点击 **{{t:common.navigation.queue}}** 标签。

![队列页面](/assets/images/user-guide/87_queue_button.png)
*（图 87：队列页面 - 过滤选项和状态标签）*

2. 要过滤队列项：
   - 使用 **{{t:queue.trace.team}}**、**{{t:queue.trace.machine}}**、**{{t:queue.trace.region}}** 和 **{{t:queue.trace.bridge}}** 过滤器
   - 指定 **{{t:system.audit.filters.dateRange}}**
   - 勾选 **{{t:queue.filters.onlyStale}}** 选项

3. 在状态标签中查看详情：
   - **{{t:queue.statusActive}}**：正在处理的任务
   - **{{t:queue.statusCompleted}}**：成功完成的任务
   - **{{t:queue.statusCancelled}}**：已取消的任务
   - **{{t:queue.statusFailed}}**：失败的任务

4. 从 **{{t:common.actions.export}}** 按钮选择格式：**{{t:common.exportCSV}}** 或 **{{t:common.exportJSON}}**。

![队列导出](/assets/images/user-guide/88_queue_export.png)
*（图 88：队列列表 - 导出选项）*

> **提示**："{{t:queue.filters.onlyStale}}" 选项有助于查找长时间处理的任务。定期导出队列历史以分析任务执行趋势。

---

## 2.11 审计

审计部分维护系统中执行的所有操作的记录。

### 2.11.1 审计记录

![Audit records walkthrough](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(视频: Viewing system audit records)*

1. 从左侧菜单点击 **{{t:common.navigation.audit}}** 标签。

![审计列表](/assets/images/user-guide/89_audit_list.png)
*（图 89：审计页面 - 所有系统操作的详细记录）*

2. 过滤审计记录：
   - **日期范围**：过滤特定时期
   - **实体类型**：按请求、机器、队列等过滤
   - **搜索**：执行文本搜索

3. 查看每条记录的信息：
   - **时间戳**：操作的日期和时间
   - **操作**：操作类型（创建、编辑、删除等）
   - **实体类型**：受影响对象的类型
   - **实体名称**：特定对象标识符
   - **用户**：执行操作的用户
   - **详情**：有关操作的附加信息

4. 从 **{{t:common.actions.export}}** 按钮选择格式：**{{t:common.exportCSV}}** 或 **{{t:common.exportJSON}}**。

![审计导出](/assets/images/user-guide/90_audit_export.png)
*（图 90：审计记录导出 - CSV 和 JSON 选项）*

> **提示**：审计记录对于跟踪所有系统活动以实现安全和合规目的至关重要。定期导出审计记录并将其存储在安全位置。

---

**© 2025 Rediacc Platform – All Rights Reserved.**
