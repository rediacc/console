---
title: 웹 애플리케이션
description: Rediacc를 활용한 웹 애플리케이션 아키텍처 및 배포 이해
category: Reference
order: 1
language: ko
---

# Rediacc 플랫폼 사용자 가이드

## 개요

**Rediacc**는 AI 기반 백업 서비스를 제공하는 클라우드 플랫폼입니다.

이 가이드는 [https://www.rediacc.com/](https://www.rediacc.com/) 웹 인터페이스의 기본 사용법을 설명합니다.

### 이 가이드의 목적

- 새로운 사용자가 플랫폼에 빠르게 적응할 수 있도록 안내
- 기본 기능(리소스 관리, 백업)을 단계별로 설명

---

## 1. 계정 생성 및 로그인

### 1.1 회원 가입

![회원 가입 절차 안내](/assets/videos/user-guide/01-01-registration.webm)
*(동영상: 시작부터 완료까지 전체 회원 가입 흐름)*

Rediacc 플랫폼 사용을 시작하려면 먼저 계정을 만들어야 합니다.

![Rediacc 로그인 페이지 - 상시 운영 인프라](/assets/images/user-guide/01_login.png)
*(그림 1: 메인 로그인 페이지, Rediacc 플랫폼의 주요 기능 표시)*

1. 브라우저에서 [https://www.rediacc.com/](https://www.rediacc.com/)으로 이동합니다.
2. 페이지 오른쪽 상단의 **{{t:auth.login.signIn}}** 버튼을 클릭합니다.
3. 무료 이용을 원하시면 **Get Started**, 데모 요청은 **Request Demo**를 선택합니다.

> **팁**: 신용카드 없이도 무료 계정을 만들 수 있습니다. 무제한 팀이 포함됩니다.

![Rediacc 로그인 폼 - 이메일 및 비밀번호 필드](/assets/images/user-guide/02_register.png)
*(그림 2: 기존 사용자를 위한 로그인 화면)*

4. 계정이 없으시면 **{{t:auth.login.register}}** 링크를 클릭하여 새 계정을 만드세요.

5. 열리는 양식에 다음 정보를 입력합니다:
   - **{{t:auth.registration.organizationName}}**: 조직 이름을 입력합니다
   - **{{t:auth.login.email}}**: 유효한 이메일 주소를 입력합니다
   - **{{t:auth.login.password}}**: 8자 이상의 비밀번호를 만듭니다
   - **{{t:auth.registration.passwordConfirm}}**: 동일한 비밀번호를 다시 입력합니다

![계정 만들기 모달 - 등록, 인증, 완료 단계](/assets/images/user-guide/03_create_account.png)
*(그림 3: 신규 사용자 회원 가입 단계별 양식 - 등록 > 인증 > 완료)*

6. 이용 약관 및 개인정보 처리방침에 동의하는 체크박스를 선택합니다.
7. **{{t:auth.registration.createAccount}}** 버튼을 클릭합니다.

> **팁**: 비밀번호는 최소 8자 이상이어야 하며 강력한 비밀번호를 사용하시기 바랍니다. 모든 필드는 필수 항목입니다.

8. 이메일로 발송된 6자리 인증 코드를 순서대로 입력란에 입력합니다.
9. **{{t:auth.registration.verifyAccount}}** 버튼을 클릭합니다.

![인증 코드 입력 - 6자리 활성화 코드](/assets/images/user-guide/04_verification_code.png)
*(그림 4: 관리자에게 발송된 활성화 코드 입력 창)*

> **팁**: 인증 코드는 제한된 시간 동안만 유효합니다. 코드를 받지 못하셨다면 스팸 폴더를 확인해 주세요.

---

### 1.2 로그인

![로그인 절차 안내](/assets/videos/user-guide/01-02-login.webm)
*(동영상: 전체 로그인 흐름)*

계정을 만든 후 플랫폼에 로그인할 수 있습니다.

1. **{{t:auth.login.email}}** 필드를 입력합니다(빨간 경고가 표시되면 필수 입력).
2. **{{t:auth.login.password}}** 필드를 입력합니다.
3. **{{t:auth.login.signIn}}** 버튼을 클릭합니다.

![로그인 폼 - 오류 경고가 표시된 필수 필드](/assets/images/user-guide/05_sign_in.png)
*(그림 5: 로그인 폼 - 오류 메시지는 빨간 테두리로 표시됩니다)*

> **팁**: "이 필드는 필수 항목입니다"라는 오류 메시지가 표시되면 빈 필드를 채워 주세요. 비밀번호를 잊으셨다면 관리자에게 문의하시기 바랍니다.

4. 로그인 성공 후 **{{t:common.navigation.dashboard}}** 화면으로 이동합니다.

![Rediacc 대시보드 - 머신 목록 및 사이드바 메뉴](/assets/images/user-guide/06_dashboard.png)
*(그림 6: 로그인 성공 후 메인 대시보드 - 왼쪽 사이드바에 조직, 머신, 설정 메뉴)*

> **팁**: 대시보드는 자동으로 새로 고쳐집니다. F5 키로 페이지를 새로 고치면 최신 정보를 확인할 수 있습니다.

---

## 2. 인터페이스 개요

로그인 후 보이는 화면은 다음과 같은 주요 섹션으로 구성됩니다:

- **{{t:common.navigation.organization}}**: 사용자, 팀, 접근 제어
- **{{t:common.navigation.machines}}**: 서버 및 저장소 관리
- **{{t:common.navigation.settings}}**: 프로필 및 시스템 설정
- **{{t:common.navigation.storage}}**: 스토리지 영역 관리
- **{{t:common.navigation.credentials}}**: 접근 자격 증명
- **{{t:common.navigation.queue}}**: 작업 대기열 관리
- **{{t:common.navigation.audit}}**: 시스템 감사 로그

---

## 2.1 조직 - 사용자

사용자 관리를 통해 조직 내 구성원의 플랫폼 접근 권한을 제어할 수 있습니다.

### 2.1.1 사용자 추가

![사용자 추가 안내](/assets/videos/user-guide/02-01-01-user-create.webm)
*(동영상: 새 사용자 만들기)*

1. 왼쪽 사이드바에서 **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** 옵션을 클릭합니다.
2. 테이블 형식으로 모든 사용자 목록을 확인합니다.
3. 각 사용자 행에는 이메일, 상태({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), 권한 그룹, 마지막 활동 시간이 표시됩니다.

![사용자 관리 페이지 - 활성 사용자 목록](/assets/images/user-guide/07_users.png)
*(그림 7: 조직 내 사용자 섹션 - 모든 사용자 정보가 표시됩니다)*

4. 오른쪽 상단의 **"+"** 아이콘을 클릭합니다.
5. **{{t:organization.users.modals.createTitle}}** 버튼을 클릭하고 열리는 양식을 작성합니다:
   - **{{t:organization.users.form.emailLabel}}**: 사용자의 이메일 주소를 입력합니다
   - **{{t:organization.users.form.passwordLabel}}**: 임시 비밀번호를 입력합니다

![사용자 생성 모달 - 이메일 및 비밀번호 필드](/assets/images/user-guide/08_user_add.png)
*(그림 8: 새 사용자 추가 모달 창 - 간단하고 빠른 사용자 생성 양식)*

6. **{{t:common.actions.create}}** 버튼을 클릭합니다.

> **팁**: 로그인 자격 증명은 생성된 사용자에게 안전하게 전달해야 합니다. 첫 로그인 시 비밀번호 변경을 권장합니다.

![사용자 목록 - 세 명의 사용자가 있는 전체 테이블 보기](/assets/images/user-guide/09_user_list.png)
*(그림 9: 사용자 관리 페이지의 모든 활성 및 비활성 사용자)*

> **팁**: 페이지에는 기본적으로 20개의 레코드가 표시됩니다. 더 많은 레코드를 보려면 페이지 매김을 사용하세요.

### 2.1.2 사용자 권한 할당

![사용자 권한 안내](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(동영상: 사용자에게 권한 그룹 할당)*

특정 권한 그룹을 사용자에게 할당하여 접근 권한을 관리할 수 있습니다.

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** 탭에서 사용자를 선택합니다.
2. 작업 열의 방패 아이콘(**{{t:organization.access.tabs.permissions}}**)을 클릭합니다.

![권한 관리 - 방패, 톱니바퀴, 삭제 아이콘](/assets/images/user-guide/10_users_permissions.png)
*(그림 10: 사용자 작업 아이콘 표시 - 각 아이콘은 다른 작업을 나타냅니다)*

3. 열리는 양식에서 **{{t:organization.users.modals.permissionGroupLabel}}**를 선택합니다.
4. 그룹의 사용자 수와 권한이 사용자 옆에 표시됩니다.
5. **{{t:organization.users.modals.assignTitle}}** 버튼을 클릭하여 변경 사항을 저장합니다.

![권한 할당 모달 - 관리자 그룹](/assets/images/user-guide/11_user_permissions_form.png)
*(그림 11: 선택한 사용자에게 권한 그룹을 할당하는 모달 - 사용 가능한 그룹 드롭다운)*

> **팁**: 일부 권한 그룹은 시스템에 의해 고정되어 변경할 수 없습니다.

### 2.1.3 사용자 활성화

![사용자 활성화 안내](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(동영상: 비활성 사용자 활성화)*

비활성화된 사용자를 다시 활성화할 수 있습니다.

1. **사용자** 목록에서 비활성 상태의 사용자를 찾습니다.
2. 작업 열의 빨간 아이콘을 클릭합니다.

![사용자 활성화 - "활성화" 툴팁 보기](/assets/images/user-guide/12_users_activation.png)
*(그림 12: 비활성 사용자 활성화)*

3. 확인 창에서 **{{t:common.general.yes}}** 버튼을 클릭합니다.

![활성화 확인 모달](/assets/images/user-guide/13_users_activation_confirm.png)
*(그림 13: 사용자 활성화 확인 모달 창)*

> **팁**: 이 작업은 되돌릴 수 있습니다. 같은 방법으로 사용자를 비활성화할 수도 있습니다.

### 2.1.4 사용자 추적

![사용자 추적 안내](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(동영상: 사용자 활동 추적 보기)*

추적 기능을 사용하여 사용자 활동을 모니터링할 수 있습니다.

1. 사용자를 선택하고 작업 열의 톱니바퀴 아이콘을 클릭합니다.
2. **{{t:common.actions.trace}}** 옵션을 클릭하여 사용자의 활동 내역을 엽니다.

![사용자 추적 - 작업 버튼이 있는 "추적" 툴팁](/assets/images/user-guide/14_users_trace.png)
*(그림 14: 사용자 활동 추적 옵션)*

3. 열린 화면에 사용자의 과거 활동이 목록으로 표시됩니다.
4. 상단에 통계가 표시됩니다: 총 레코드, 조회된 레코드, 마지막 활동.
5. **{{t:common.actions.export}}** 버튼을 클릭하고 형식을 선택합니다: **{{t:common.exportCSV}}** 또는 **{{t:common.exportJSON}}**.

![감사 내역 - 내보내기 옵션](/assets/images/user-guide/15_user_trace_export.png)
*(그림 15: 사용자의 전체 활동 내역 - 통계, 세부 정보, 내보내기 옵션)*

> **팁**: 보안 및 규정 준수 기록을 유지하기 위해 감사 데이터를 정기적으로 내보내세요. CSV 형식은 Excel에서 열 수 있습니다.

---

## 2.2 조직 - 팀

팀을 통해 사용자를 그룹화하고 리소스에 대한 일괄 접근 권한을 제공할 수 있습니다.

### 2.2.1 팀 만들기

![팀 만들기 안내](/assets/videos/user-guide/02-02-01-team-create.webm)
*(동영상: 새 팀 만들기)*

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}** 탭으로 이동합니다.
2. **"+"** 버튼을 클릭합니다.
3. **{{t:common.vaultEditor.fields.TEAM.name.label}}** 필드에 팀 이름을 입력합니다.
4. **{{t:common.vaultEditor.vaultConfiguration}}** 섹션에서 **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** 및 **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** 필드를 입력합니다.

![새 팀 생성 양식 - 팀 이름 및 SSH 키](/assets/images/user-guide/16_teams_create.png)
*(그림 16: "Private Team" 내에 새 팀 만들기)*

5. **{{t:common.actions.create}}** 버튼을 클릭하여 팀을 저장합니다.

> **팁**: SSH 키는 Bridge SSH 인증에 필요합니다. 키 누락 경고가 표시되면 두 키를 모두 입력해 주세요.

### 2.2.2 팀 편집

![팀 편집 안내](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(동영상: 팀 정보 편집)*

1. 팀 목록에서 편집하려는 팀 옆의 연필 아이콘을 클릭합니다.
2. 필요한 경우 **{{t:common.vaultEditor.fields.TEAM.name.label}}** 필드에서 팀 이름을 변경합니다.
3. **{{t:common.vaultEditor.vaultConfiguration}}** 섹션에서 SSH 키를 업데이트합니다.
4. **{{t:common.save}}** 버튼을 클릭하여 변경 사항을 적용합니다.

![팀 편집 양식 - 파란색 안내 메시지](/assets/images/user-guide/17_teams_edit_form.png)
*(그림 17: 기존 팀 정보 편집)*

> **팁**: 팀 구성은 조직 구조에 사용됩니다. 변경 사항은 모든 팀 구성원에게 적용됩니다.

### 2.2.3 팀 구성원 관리

![팀 구성원 관리 안내](/assets/videos/user-guide/02-02-03-team-members.webm)
*(동영상: 팀 구성원 관리)*

1. 팀을 선택하고 사용자 아이콘을 클릭합니다.
2. **{{t:organization.teams.manageMembers.currentTab}}** 탭에서 팀에 이미 할당된 구성원을 확인합니다.
3. **{{t:organization.teams.manageMembers.addTab}}** 탭으로 전환합니다.
4. 이메일 주소를 입력하거나 드롭다운에서 사용자를 선택합니다.
5. **"+"** 버튼을 클릭하여 구성원을 팀에 추가합니다.

![팀 구성원 관리 양식 - "현재 구성원" 및 "구성원 추가" 탭](/assets/images/user-guide/18_teams_members_form.png)
*(그림 18: 팀 구성원 관리 패널)*

> **팁**: 동일한 구성원을 여러 팀에 할당할 수 있습니다.

### 2.2.4 팀 추적

![팀 추적 안내](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(동영상: 팀 감사 내역 보기)*

1. 추적할 팀을 선택합니다.
2. 시계/내역 아이콘을 클릭합니다.
3. **{{t:resources.audit.title}}** 모달에서 총 레코드, 조회된 레코드, 마지막 활동 수를 검토합니다.
4. **{{t:common.actions.export}}** 버튼을 클릭하여 {{t:common.exportCSV}} 또는 {{t:common.exportJSON}} 형식으로 내보냅니다.

![감사 내역 모달 - DataBassTeam 팀](/assets/images/user-guide/19_teams_trace.png)
*(그림 19: 팀 감사 내역 보기)*

> **팁**: 감사 내역은 규정 준수 및 보안 통제에 중요합니다.

### 2.2.5 팀 삭제

![팀 삭제 안내](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(동영상: 팀 삭제)*

1. 삭제하려는 팀 옆의 휴지통(빨간색) 아이콘을 클릭합니다.
2. 확인 대화상자에서 팀 이름이 올바른지 확인합니다.
3. **{{t:common.general.yes}}** 버튼을 클릭합니다.

![팀 삭제 확인 대화상자](/assets/images/user-guide/20_teams_delete.png)
*(그림 20: 팀 삭제 확인)*

> **경고**: 팀 삭제는 되돌릴 수 없습니다. 삭제 전에 팀 내에 중요한 데이터가 있는지 확인하세요.

---

## 2.3 조직 - 접근 제어

접근 제어를 통해 권한 그룹을 만들어 사용자 권한을 중앙에서 관리할 수 있습니다.

### 2.3.1 권한 그룹 만들기

![권한 그룹 생성 안내](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(동영상: 권한 그룹 만들기)*

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}** 탭으로 이동합니다.
2. **"+"** 버튼을 클릭합니다.
3. **{{t:organization.access.modals.groupPlaceholder}}** 필드에 의미 있는 이름을 입력합니다.
4. **{{t:common.actions.confirm}}** 버튼을 클릭하여 그룹을 만듭니다.

![권한 그룹 생성 양식](/assets/images/user-guide/21_create_access.png)
*(그림 21: 새 권한 그룹 만들기)*

> **팁**: 권한 그룹은 유사한 권한을 가진 사용자를 구성하는 데 사용됩니다. 그룹 이름을 설명적으로 유지하세요(예: "Admin", "Read Only", "Repository Manager").

### 2.3.2 권한 관리

![권한 관리 안내](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(동영상: 그룹의 권한 관리)*

1. 권한 그룹을 선택하고 **{{t:organization.access.modals.managePermissionsTitle}}** 옵션을 클릭합니다.
2. **{{t:organization.access.modals.currentPermissionsTab}}** 탭에서 그룹의 접근 권한을 확인합니다.
3. 각 작업 옆의 빨간 **{{t:common.delete}}** 버튼을 클릭하여 권한을 철회할 수 있습니다.
4. **{{t:organization.access.modals.addPermissionsTab}}** 탭을 클릭하여 그룹에 새 권한을 추가합니다.

![권한 관리 패널 - 할당된 권한 목록](/assets/images/user-guide/22_access_permission.png)
*(그림 22: 권한 그룹의 권한 관리)*

> **팁**: 최소 권한 원칙에 따라 권한을 부여하세요. 정기적으로 검토하고 불필요한 권한을 제거하세요.

---

## 2.4 머신

머신 섹션에서 서버 및 저장소 리소스를 관리할 수 있습니다.

### 2.4.1 머신 추가

![머신 추가 안내](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(동영상: 새 머신 추가)*

1. 왼쪽 메뉴에서 **{{t:common.navigation.machines}}** 탭으로 이동합니다.
2. 오른쪽 상단의 **{{t:machines.createMachine}}** 버튼을 클릭합니다.

![머신 페이지 - "머신 추가" 버튼](/assets/images/user-guide/23_machines_add.png)
*(그림 23: 머신 관리 홈 페이지)*

3. 열리는 양식을 작성합니다:
   - **{{t:machines.machineName}}**: 고유한 이름을 입력합니다(예: "server-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: 머신 IP 주소를 입력합니다(예: 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: 스토리지 디렉토리를 지정합니다(예: /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: SSH 사용자 이름을 입력합니다
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: 포트 번호를 입력합니다(기본값: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: 비밀번호를 입력합니다(선택 사항)

![머신 추가 양식 - 모든 필드](/assets/images/user-guide/24_machine_create.png)
*(그림 24: 새 머신 추가 양식 - 머신 이름, 네트워크 설정, SSH 자격 증명)*

4. **{{t:common.vaultEditor.testConnection.button}}** 버튼을 클릭하여 연결을 확인합니다.
5. 테스트 성공 후 **{{t:common.actions.create}}** 버튼을 클릭합니다.

> **팁**: "머신 생성 후 자동으로 설정 시작" 옵션이 선택되어 있으면 머신이 자동으로 추가 설정 단계를 수행합니다.

![머신 생성 완료 - 작업 추적 창](/assets/images/user-guide/25_machine_create_complete.png)
*(그림 25: 머신이 성공적으로 생성된 후 작업 추적 창)*

6. 단계를 확인합니다: **{{t:queue.trace.assigned}}** → **Processing** → **{{t:queue.statusCompleted}}**
7. **{{t:common.actions.close}}** 버튼을 클릭하여 작업을 닫습니다.

> **팁**: "{{t:common.actions.refresh}}" 버튼을 클릭하여 최신 상태를 수동으로 확인하세요.

### 2.4.2 연결 테스트

![연결 테스트 안내](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(동영상: 연결 테스트 실행)*

기존 머신의 연결 상태를 확인할 수 있습니다.

1. **{{t:machines.connectivityTest}}** 버튼을 클릭합니다.

![연결 테스트 버튼](/assets/images/user-guide/26_connectivity_test_button.png)
*(그림 26: 머신 작업 도구 모음의 연결 테스트 버튼)*

2. 테스트할 머신 목록을 확인합니다.
3. **{{t:machines.runTest}}** 버튼을 클릭합니다.
4. 성공 결과는 녹색, 실패는 빨간색으로 표시됩니다.

![연결 테스트 양식 - 머신 목록](/assets/images/user-guide/27_connectivity_test_form.png)
*(그림 27: 연결 테스트 양식 - 선택된 머신에 대한 핑 기능)*

> **팁**: 테스트가 실패하면 머신 IP 주소와 SSH 설정을 확인하세요.

### 2.4.3 머신 목록 새로 고침

![머신 목록 새로 고침 안내](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(동영상: 머신 목록 새로 고침)*

**{{t:common.actions.refresh}}** 버튼을 클릭하여 머신 목록을 업데이트합니다.

![새로 고침 버튼](/assets/images/user-guide/28_refresh.png)
*(그림 28: 머신 작업 도구 모음의 새로 고침 버튼)*

### 2.4.4 머신 세부 정보

![머신 세부 정보 안내](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(동영상: 머신 세부 정보 보기)*

1. 세부 정보를 보려는 머신을 선택합니다.
2. 눈 아이콘 버튼(**{{t:common.viewDetails}}**)을 클릭합니다.

![세부 정보 보기 버튼](/assets/images/user-guide/29_view_details_button.png)
*(그림 29: 머신 작업 열의 눈 아이콘)*

3. 오른쪽에 머신 세부 정보 패널이 열립니다:
   - **Hostname**: 머신 이름
   - **Uptime**: 실행 시간
   - **{{t:queue.trace.operatingSystem}}**: 운영 체제 및 버전
   - **{{t:queue.trace.kernelVersion}}**: 커널 버전
   - **CPU**: 프로세서 정보
   - **System Time**: 시스템 시계

![머신 세부 정보 패널 - 시스템 정보](/assets/images/user-guide/30_machine_view_details.png)
*(그림 30: 머신 세부 정보 패널 - 호스트 이름, 가동 시간, OS, 커널, CPU 정보)*

> **팁**: OS 호환성 및 리소스 가용성을 확인하기 위해 이 정보를 정기적으로 검토하세요.

### 2.4.5 머신 편집

![머신 편집 안내](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(동영상: 머신 설정 편집)*

1. 편집하려는 머신을 선택합니다.
2. 연필 아이콘 버튼(**{{t:common.actions.edit}}**)을 클릭합니다.

![편집 버튼](/assets/images/user-guide/31_edit_button.png)
*(그림 31: 머신 작업 열의 연필 아이콘)*

3. 필요한 변경 사항을 적용합니다.
4. **{{t:common.vaultEditor.testConnection.button}}** 버튼을 클릭합니다.
5. 연결이 성공하면 **{{t:common.save}}** 버튼을 클릭합니다.

![머신 편집 양식](/assets/images/user-guide/32_edit_form.png)
*(그림 32: 머신 편집 양식 - 머신 이름, 지역, 볼트 구성)*

> **팁**: 중요한 설정을 변경한 후에는 항상 "연결 테스트"를 실행하세요.

### 2.4.6 머신 추적

![머신 추적 안내](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(동영상: 머신 감사 내역 보기)*

1. 머신을 선택하고 시계 아이콘 버튼(**{{t:common.actions.trace}}**)을 클릭합니다.

![추적 버튼](/assets/images/user-guide/33_trace_button.png)
*(그림 33: 머신 작업 열의 시계 아이콘)*

2. 감사 내역 창에서 작업을 검토합니다:
   - **{{t:resources.audit.action}}**: 수행된 작업 유형
   - **Details**: 변경된 필드
   - **{{t:resources.audit.performedBy}}**: 작업을 수행한 사용자
   - **Timestamp**: 날짜 및 시간

![머신 감사 내역 창](/assets/images/user-guide/34_trace_list.png)
*(그림 34: 감사 내역 - 모든 변경 사항 목록)*

> **팁**: Timestamp 열을 클릭하여 변경 사항을 시간순으로 확인하세요.

### 2.4.7 머신 삭제

![머신 삭제 안내](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(동영상: 머신 삭제)*

1. 삭제하려는 머신을 선택합니다.
2. 휴지통 아이콘 버튼(**{{t:common.delete}}**)을 클릭합니다.

![삭제 버튼](/assets/images/user-guide/35_delete_button.png)
*(그림 35: 머신 작업 열의 휴지통 아이콘)*

3. 확인 창에서 **{{t:common.delete}}** 버튼을 클릭합니다.

![머신 삭제 확인 창](/assets/images/user-guide/36_delete_form.png)
*(그림 36: "이 머신을 삭제하시겠습니까?" 확인 창)*

> **경고**: 머신을 삭제하면 해당 머신의 모든 저장소 정의도 함께 삭제됩니다. 이 작업은 되돌릴 수 없습니다.

### 2.4.8 원격 작업

![원격 작업 안내](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(동영상: 머신에서 원격 작업 실행)*

머신에서 다양한 원격 작업을 수행할 수 있습니다.

1. 머신을 선택하고 **{{t:common.actions.remote}}** 버튼을 클릭합니다.
2. 드롭다운 메뉴에서 옵션을 확인합니다:
   - **{{t:machines.runAction}}**: 머신에서 함수 실행
   - **{{t:common.vaultEditor.testConnection.button}}**: 머신에 핑 전송

![원격 메뉴 - 서버에서 실행 및 연결 테스트](/assets/images/user-guide/37_remote_button.png)
*(그림 37: 원격 버튼 - 선택된 머신의 함수 실행 메뉴)*

> **팁**: 함수를 실행하기 전에 "{{t:common.vaultEditor.testConnection.button}}" 옵션을 사용하여 머신에 접근 가능한지 확인하세요.

#### 설정

1. **{{t:machines.runAction}}** 옵션을 선택합니다.
2. **{{t:functions.availableFunctions}}** 목록에서 **Setup** 함수를 찾습니다.
3. 함수 이름을 클릭하여 선택합니다.

![머신 함수 목록 - 설정 함수](/assets/images/user-guide/38_server_setup.png)
*(그림 38: 설정 함수 - 필요한 도구 및 구성으로 머신을 준비합니다)*

> **팁**: 새 머신을 설정할 때 먼저 "setup" 함수를 실행하는 것을 권장합니다.

#### 연결 확인 (Hello)

1. **{{t:machines.runAction}}** > **Hello** 함수를 선택합니다.
2. **{{t:common.actions.addToQueue}}** 버튼을 클릭합니다.

![Hello 함수 선택](/assets/images/user-guide/39_remote_hello.png)
*(그림 39: Hello 함수 - 호스트 이름을 반환하는 간단한 테스트 함수)*

3. 작업 추적 창에서 결과를 확인합니다.
4. **{{t:queue.trace.responseConsole}}** 섹션에서 머신의 출력을 확인합니다.

![Hello 함수 완료](/assets/images/user-guide/40_remote_hello_complete.png)
*(그림 40: Hello 함수 성공적으로 완료 - 호스트 이름 응답)*

> **팁**: hello 함수는 머신 연결성을 확인하는 데 이상적입니다.

#### 고급 작업

1. **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}** 경로를 따라갑니다.
2. 사용 가능한 함수를 확인합니다: setup, hello, ping, ssh_test, uninstall
3. 필요한 함수를 선택하고 **{{t:common.actions.addToQueue}}** 버튼을 클릭합니다.

![고급 함수 목록](/assets/images/user-guide/41_remote_advanced.png)
*(그림 41: 고급 옵션 - 고급 함수 목록)*

> **팁**: 고급 함수를 사용하기 전에 머신 설정이 완료되었는지 확인하세요.

#### 빠른 연결 테스트

![원격 메뉴 - 연결 테스트](/assets/images/user-guide/42_connectivity_test.png)
*(그림 42: 원격 메뉴의 연결 테스트 옵션)*

> **팁**: 머신에 SSH 또는 네트워크 문제가 있는 경우 이 테스트로 문제를 빠르게 파악할 수 있습니다.

---

## 2.5 저장소 생성 및 작업

저장소는 백업 데이터가 저장되는 기본 단위입니다.

### 2.5.1 저장소 만들기

![저장소 생성 안내](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(동영상: 새 저장소 만들기)*

1. **{{t:common.navigation.machines}}** 탭에서 머신을 선택합니다.
2. 오른쪽 상단의 **{{t:machines.createRepository}}** 버튼을 클릭합니다.

![저장소 만들기 버튼](/assets/images/user-guide/43_create_repo_add.png)
*(그림 43: 머신 저장소 관리 화면 - 저장소 만들기 버튼)*

3. 양식을 작성합니다:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: 저장소 이름을 입력합니다(예: postgresql)
   - **{{t:resources.repositories.size}}**: 저장소 크기를 입력합니다(예: 2GB)
   - **{{t:resources.repositories.repositoryGuid}}**: 자동으로 생성된 자격 증명을 확인합니다
   - **{{t:resources.templates.selectTemplate}}**: 템플릿을 선택합니다(예: databases_postgresql)

![저장소 생성 양식](/assets/images/user-guide/44_repo_form.png)
*(그림 44: 저장소 생성 양식 - 저장소 이름, 크기, 템플릿 선택)*

4. **{{t:common.actions.create}}** 버튼을 클릭합니다.

> **팁**: 자격 증명 ID는 자동으로 생성되며 수동 수정은 권장하지 않습니다.

5. 작업 추적 창에서 단계를 확인합니다: **{{t:queue.trace.assigned}}** → **Processing** → **{{t:queue.statusCompleted}}**

![저장소 생성 완료](/assets/images/user-guide/45_repo_complete.png)
*(그림 45: 저장소 생성 대기열 등록 - 작업 모니터링)*

6. **{{t:common.actions.close}}** 버튼을 클릭합니다.

> **팁**: 작업은 일반적으로 1-2분 내에 완료됩니다.

![저장소 목록](/assets/images/user-guide/46_repo_list.png)
*(그림 46: 생성된 저장소가 목록에 표시됩니다)*

### 2.5.2 저장소 포크

![저장소 포크 안내](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(동영상: 저장소 포크)*

기존 저장소를 복사하여 새 저장소를 만들 수 있습니다.

1. 복사하려는 저장소를 선택합니다.
2. **fx**(함수) 메뉴를 클릭합니다.
3. **fork** 옵션을 클릭합니다.

![fx 메뉴 - fork 옵션](/assets/images/user-guide/47_fork_button.png)
*(그림 47: 오른쪽의 fx 메뉴 - 저장소 작업)*

4. **{{t:functions.functions.fork.params.tag.label}}** 필드에 새 태그를 입력합니다(예: 2025-12-06-20-37-08).
5. **{{t:common.actions.addToQueue}}** 버튼을 클릭합니다.

![포크 구성 양식](/assets/images/user-guide/48_fork_form.png)
*(그림 48: 포크 작업에서 저장소의 새 태그를 지정합니다)*

6. **{{t:queue.statusCompleted}}** 메시지를 기다린 후 **{{t:common.actions.close}}** 버튼을 클릭합니다.

![포크 완료](/assets/images/user-guide/49_repo_completed.png)
*(그림 49: 포크 작업이 성공적으로 완료되었습니다)*

> **팁**: 기본 날짜-시간 형식으로 태그를 만드는 것이 좋은 관행입니다. 포크 작업은 원본 저장소에 영향을 주지 않습니다.

### 2.5.3 저장소 시작 (Up)

![저장소 시작 안내](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(동영상: 저장소 시작)*

저장소를 활성화하려면:

1. 저장소를 선택하고 **fx** > **up** 경로를 따라갑니다.

![Up 작업](/assets/images/user-guide/50_repo_up.png)
*(그림 50: fx 메뉴의 "up" 옵션 - 저장소 시작)*

2. **{{t:queue.statusCompleted}}** 메시지를 기다립니다.

![Up 완료](/assets/images/user-guide/51_repo_up_complete.png)
*(그림 51: 저장소 시작 완료)*

> **팁**: "Up" 작업은 저장소에 정의된 Docker 서비스를 시작합니다.

### 2.5.4 저장소 중지 (Down)

![저장소 중지 안내](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(동영상: 저장소 중지)*

활성 저장소를 중지하려면:

1. 저장소를 선택하고 **fx** > **down** 경로를 따라갑니다.

![Down 작업](/assets/images/user-guide/52_down_button.png)
*(그림 52: fx 메뉴의 "down" 옵션 - 저장소 종료)*

2. **{{t:queue.statusCompleted}}** 메시지를 기다립니다.

![Down 완료](/assets/images/user-guide/53_down_completed.png)
*(그림 53: 저장소 종료 완료)*

> **팁**: "Down" 작업은 저장소를 안전하게 종료합니다. 데이터는 손실되지 않으며 서비스만 중지됩니다.

### 2.5.5 배포 (Deploy)

![저장소 배포 안내](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(동영상: 저장소 배포)*

저장소를 다른 위치에 배포하려면:

1. 저장소를 선택하고 **fx** > **deploy** 경로를 따라갑니다.

![배포 작업](/assets/images/user-guide/54_deploy_button.png)
*(그림 54: fx 메뉴의 "deploy" 옵션)*

2. **{{t:functions.functions.fork.params.tag.label}}** 필드에 배포할 버전을 입력합니다.
3. **{{t:functions.functions.backup_deploy.params.machines.label}}** 필드에서 대상 머신을 선택합니다.
4. **{{t:functions.checkboxOptions.overrideExistingFile}}** 옵션을 선택합니다(해당하는 경우).
5. **{{t:common.actions.addToQueue}}** 버튼을 클릭합니다.

![배포 양식](/assets/images/user-guide/55_deploy_form.png)
*(그림 55: 배포 작업 구성 - 태그, 대상 머신, 옵션)*

6. **{{t:queue.statusCompleted}}** 메시지를 기다립니다.

![배포 완료](/assets/images/user-guide/56_deploy_completed.png)
*(그림 56: 저장소 배포 완료)*

> **팁**: 배포 작업이 완료된 후 "up" 명령을 실행하여 대상 머신에서 저장소를 시작할 수 있습니다.

### 2.5.6 백업 (Backup)

![저장소 백업 안내](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(동영상: 저장소 백업)*

저장소를 백업하려면:

1. 저장소를 선택하고 **fx** > **backup** 경로를 따라갑니다.

![백업 작업](/assets/images/user-guide/57_backup_button.png)
*(그림 57: fx 메뉴의 "backup" 옵션)*

2. 양식을 작성합니다:
   - **{{t:functions.functions.fork.params.tag.label}}**: 설명적인 이름을 입력합니다(예: backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}**: 백업 위치를 선택합니다
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: 옵션을 활성화하거나 비활성화합니다
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: 설정을 검토합니다

![백업 양식](/assets/images/user-guide/58_backup_form.png)
*(그림 58: 백업 구성 양식 - 대상, 파일 이름, 옵션)*

3. **{{t:common.actions.addToQueue}}** 버튼을 클릭합니다.

> **팁**: 백업 태그에 설명적인 이름을 사용하세요. 대용량 저장소의 경우 체크포인트 활성화를 고려하세요.

4. **{{t:queue.statusCompleted}}** 메시지를 기다립니다.

![백업 완료](/assets/images/user-guide/59_backup_completed.png)
*(그림 59: 백업 작업이 성공적으로 완료되었습니다)*

> **팁**: 완료 상태에 도달하기 전에 인내심을 가지고 기다리세요. 대용량 백업은 수 분이 소요될 수 있습니다.

### 2.5.7 템플릿 적용

![템플릿 적용 안내](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(동영상: 저장소에 템플릿 적용)*

저장소에 새 템플릿을 적용하려면:

1. 저장소를 선택하고 **fx** > **{{t:resources.templates.selectTemplate}}** 경로를 따라갑니다.

![템플릿 작업](/assets/images/user-guide/60_templates_button.png)
*(그림 60: fx 메뉴의 "Templates" 옵션)*

2. 검색 상자에 입력하여 템플릿을 필터링합니다.
3. 원하는 템플릿을 클릭하여 선택합니다(선택된 템플릿은 굵은 테두리로 강조 표시됩니다).
4. **{{t:common.actions.addToQueue}}** 버튼을 클릭합니다.

![템플릿 선택 양식](/assets/images/user-guide/61_templates_form.png)
*(그림 61: 사용 가능한 템플릿 검색 및 선택)*

> **팁**: 검색 상자를 사용하여 템플릿을 빠르게 찾으세요. "{{t:common.viewDetails}}"를 사용하여 템플릿 기능에 대해 알아보세요.

5. **{{t:queue.statusCompleted}}** 메시지를 기다립니다.

![템플릿 적용됨](/assets/images/user-guide/62_templates_completed.png)
*(그림 62: 템플릿이 성공적으로 적용되었습니다)*

### 2.5.8 마운트 해제 (Unmount)

![저장소 마운트 해제 안내](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(동영상: 저장소 마운트 해제)*

저장소 연결을 해제하려면:

1. 저장소를 선택하고 **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}** 경로를 따라갑니다.

![마운트 해제 작업](/assets/images/user-guide/63_unmount_button.png)
*(그림 63: 고급 메뉴의 "Unmount" 옵션)*

2. **{{t:queue.statusCompleted}}** 메시지를 기다립니다.

![마운트 해제 완료](/assets/images/user-guide/64_unmount_completed.png)
*(그림 64: 마운트 해제 작업 완료)*

> **팁**: 마운트를 해제하기 전에 저장소에 활성 작업이 없는지 확인하세요. 마운트 해제 후 저장소에 접근할 수 없게 됩니다.

### 2.5.9 확장 (Expand)

![저장소 확장 안내](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(동영상: 저장소 크기 확장)*

저장소 크기를 늘리려면:

1. 저장소를 선택하고 **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}** 경로를 따라갑니다.

![확장 작업](/assets/images/user-guide/65_expand_button.png)
*(그림 65: 고급 메뉴의 "Expand" 옵션)*

2. **{{t:functions.functions.repository_expand.params.size.label}}** 필드에 원하는 크기를 입력합니다.
3. 오른쪽 드롭다운에서 단위를 선택합니다(GB, TB).
4. **{{t:common.actions.addToQueue}}** 버튼을 클릭합니다.

![확장 양식](/assets/images/user-guide/66_expand_form.png)
*(그림 66: 저장소 크기를 늘리기 위한 새 크기 파라미터)*

> **팁**: 현재 크기보다 작은 값을 입력하지 마세요. 저장소 확장 중에 서비스가 중단되지 않습니다.

5. **{{t:queue.statusCompleted}}** 메시지를 기다립니다.

![확장 완료](/assets/images/user-guide/67_expand_completed.png)
*(그림 67: 저장소 확장 완료)*

### 2.5.10 이름 변경 (Rename)

![저장소 이름 변경 안내](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(동영상: 저장소 이름 변경)*

저장소 이름을 변경하려면:

1. 저장소를 선택하고 **fx** > **{{t:common.actions.rename}}** 경로를 따라갑니다.

![이름 변경 작업](/assets/images/user-guide/68_rename_button.png)
*(그림 68: fx 메뉴의 "Rename" 옵션)*

2. 새 저장소 이름을 입력합니다.
3. **{{t:common.save}}** 버튼을 클릭합니다.

![이름 변경 양식](/assets/images/user-guide/69_rename_form.png)
*(그림 69: 새 저장소 이름을 입력하는 대화상자)*

> **팁**: 저장소 유형과 목적을 반영하는 의미 있는 이름을 사용하세요. 특수 문자는 사용하지 마세요.

### 2.5.11 저장소 삭제

![저장소 삭제 안내](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(동영상: 저장소 삭제)*

저장소를 영구적으로 삭제하려면:

1. 저장소를 선택하고 **fx** > **{{t:resources.repositories.deleteRepository}}** 경로를 따라갑니다.

![저장소 삭제 작업](/assets/images/user-guide/70_delete_repo_button.png)
*(그림 70: fx 메뉴의 "Delete Repository" 옵션 - 빨간색)*

2. 확인 창에서 **{{t:common.delete}}** 버튼을 클릭합니다.

> **경고**: 저장소 삭제는 되돌릴 수 없습니다. 삭제 전에 저장소 데이터가 백업되어 있는지 확인하세요.

### 2.5.12 저장소 세부 정보

![저장소 세부 정보 안내](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(동영상: 저장소 세부 정보 보기)*

저장소에 대한 자세한 정보를 얻으려면:

1. 저장소를 선택합니다.
2. 눈 아이콘(**{{t:common.viewDetails}}**)을 클릭합니다.

![세부 정보 보기 버튼](/assets/images/user-guide/71_repo_view_button.png)
*(그림 71: 저장소 세부 정보를 여는 눈 아이콘)*

3. 세부 정보 패널에서 정보를 검토합니다:
   - **저장소 이름** 및 유형
   - **Team**: 속한 팀
   - **Machine**: 저장된 머신
   - **Vault Version**: 암호화 버전
   - **Repository GUID**: 고유 식별자
   - **Status**: 마운트됨/마운트 해제됨 상태
   - **Image Size**: 전체 크기
   - **Last Modified**: 마지막 수정 날짜

![저장소 세부 정보 패널](/assets/images/user-guide/72_repo_details_view.png)
*(그림 72: 선택된 저장소에 대한 종합 정보)*

> **팁**: 이 패널에 표시된 모든 정보는 참조용입니다. 저장소 작업에는 fx 메뉴 옵션을 사용하세요.

---

## 2.6 저장소 연결 작업

다양한 방법으로 저장소에 연결할 수 있습니다.

### 2.6.1 데스크톱 애플리케이션 연결

![데스크톱 연결 안내](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(동영상: 데스크톱 애플리케이션으로 연결)*

1. 저장소 행의 **{{t:resources.localActions.local}}** 버튼을 클릭합니다.

![로컬 연결 버튼](/assets/images/user-guide/73_repo_connection_local.png)
*(그림 73: 저장소 행의 "Local" 버튼 - 데스크톱 애플리케이션 접근)*

2. 드롭다운 메뉴에서 접근 방법을 선택합니다:
   - **{{t:resources.localActions.openInDesktop}}**: 그래픽 인터페이스로 접근
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: 코드 편집기에서 열기
   - **{{t:common.terminal.terminal}}**: 명령줄로 접근
   - **{{t:resources.localActions.showCLICommands}}**: 명령줄 도구

![연결 옵션 메뉴](/assets/images/user-guide/74_repo_connection.png)
*(그림 74: 저장소 연결 메뉴 - 다양한 접근 경로)*

> **팁**: VS Code로 작업하는 경우 "{{t:resources.localCommandBuilder.vscodeTab}}" 옵션이 가장 빠른 통합을 제공합니다.

3. 브라우저에서 권한을 요청하면 **{{t:common.vscodeSelection.open}}** 버튼을 클릭합니다.

![데스크톱 애플리케이션 열기 권한](/assets/images/user-guide/75_desktop_open_page.png)
*(그림 75: 브라우저에서 데스크톱 애플리케이션을 열도록 권한 요청)*

> **팁**: 데스크톱 애플리케이션을 열 때마다 권한을 부여하지 않으려면 "항상 허용" 옵션을 선택하세요.

---

## 2.7 설정

설정 섹션에서 프로필 및 시스템 설정을 관리할 수 있습니다.

### 2.7.1 비밀번호 변경

![비밀번호 변경 안내](/assets/videos/user-guide/02-07-03-password-change.webm)
*(동영상: 비밀번호 변경)*

1. 왼쪽 메뉴에서 **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}** 탭으로 이동합니다.

![프로필 설정 페이지](/assets/images/user-guide/76_profiles_button.png)
*(그림 76: 설정 - 프로필 페이지 - 개인 볼트 설정)*

2. **{{t:settings.personal.changePassword.submit}}** 버튼을 클릭합니다.

![비밀번호 변경 버튼](/assets/images/user-guide/77_profiles_change_button.png)
*(그림 77: 개인 설정 섹션의 "비밀번호 변경" 버튼)*

3. 새 비밀번호를 입력합니다. 비밀번호 요구 사항:
   - 최소 8자 이상
   - 대문자와 소문자를 포함해야 합니다
   - 최소 하나의 숫자를 포함해야 합니다
   - 최소 하나의 특수 문자를 포함해야 합니다

4. **{{t:settings.personal.changePassword.confirmPasswordLabel}}** 필드에 동일한 비밀번호를 다시 입력합니다.
5. **{{t:settings.personal.changePassword.submit}}** 버튼을 클릭합니다.

![비밀번호 변경 양식](/assets/images/user-guide/78_profiles_change_form.png)
*(그림 78: 비밀번호 변경 양식 - 보안 요구 사항이 표시됩니다)*

> **팁**: 강력한 비밀번호를 만들 때 무작위 조합을 사용하세요.

---

## 2.8 스토리지

스토리지 섹션에서 백업 데이터가 저장될 물리적 공간을 관리할 수 있습니다.

### 2.8.1 스토리지 추가

![스토리지 생성 안내](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(동영상: 스토리지 위치 추가)*

1. 왼쪽 메뉴에서 **{{t:common.navigation.storage}}** 탭으로 이동합니다.
2. **{{t:resources.storage.createStorage}}** 버튼을 클릭합니다.

![스토리지 추가 버튼](/assets/images/user-guide/79_storage_add_button.png)
*(그림 79: 스토리지 관리 페이지 - "스토리지 추가" 버튼)*

3. 양식을 작성합니다:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: 설명적인 이름을 입력합니다
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: 선택합니다(예: s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: 선택적 설명을 추가합니다
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: 선택 사항
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: rclone 플래그(예: --transfers 4)

![스토리지 생성 양식](/assets/images/user-guide/80_storage_form.png)
*(그림 80: 스토리지 추가 양식 - 이름, 공급자, 설명, 파라미터)*

4. **{{t:common.actions.create}}** 버튼을 클릭합니다.

> **팁**: 추가 파라미터는 스토리지 성능을 최적화하는 rclone 플래그를 허용합니다.

---

## 2.9 자격 증명

자격 증명 섹션에서 저장소의 접근 정보를 안전하게 관리할 수 있습니다.

### 2.9.1 자격 증명 편집

![자격 증명 편집 안내](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(동영상: 자격 증명 편집)*

1. 왼쪽 메뉴에서 **{{t:common.navigation.credentials}}** 탭으로 이동합니다.
2. 편집하려는 레코드를 선택합니다.
3. **{{t:common.actions.edit}}** 버튼을 클릭합니다.

![자격 증명 목록](/assets/images/user-guide/81_credentials.png)
*(그림 81: 자격 증명 페이지 - 저장소 이름, 팀, 관리 버튼)*

4. 필요한 경우 **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**를 변경합니다.
5. **{{t:common.save}}** 버튼으로 저장합니다.

![자격 증명 편집 양식](/assets/images/user-guide/82_credentials_form.png)
*(그림 82: 저장소 이름 편집 양식 - 볼트 구성 필드)*

> **팁**: 자격 증명은 암호화되어 저장되며 배포 중에만 복호화됩니다.

### 2.9.2 자격 증명 추적

![자격 증명 추적 안내](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(동영상: 자격 증명 감사 내역 보기)*

1. 추적하려는 레코드를 선택합니다.
2. **{{t:common.actions.trace}}** 버튼을 클릭합니다.

![추적 버튼](/assets/images/user-guide/83_credentials_trace_button.png)
*(그림 83: 자격 증명 테이블의 "추적" 버튼)*

3. 감사 내역을 검토합니다.
4. **{{t:common.actions.export}}** 버튼에서 형식을 선택합니다: **{{t:common.exportCSV}}** 또는 **{{t:common.exportJSON}}**.

![자격 증명 감사 내역](/assets/images/user-guide/84_credentials_list_export.png)
*(그림 84: 자격 증명 목록 - 내보내기 옵션)*

> **팁**: 추적 기능은 보안 감사 목적으로 자격 증명의 사용 현황을 추적합니다.

### 2.9.3 자격 증명 삭제

![자격 증명 삭제 안내](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(동영상: 자격 증명 삭제)*

1. 삭제하려는 레코드를 선택합니다.
2. 빨간 **{{t:common.delete}}** 버튼을 클릭합니다.

![삭제 버튼](/assets/images/user-guide/85_credentials_delete.png)
*(그림 85: 자격 증명 페이지의 빨간 "삭제" 버튼)*

3. 확인 창에서 **{{t:common.delete}}** 버튼을 클릭합니다.

![삭제 확인](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(그림 86: 삭제 확인 대화상자 - 되돌릴 수 없는 작업 경고)*

> **경고**: 삭제 전에 다른 머신이나 다른 작업에서 해당 자격 증명이 사용 중인지 확인하세요. 중요한 자격 증명은 삭제 전에 백업이 있는지 확인하세요.

---

## 2.10 대기열 (Queue)

대기열 섹션에서 시스템의 대기 중인 작업과 완료된 작업을 추적할 수 있습니다.

### 2.10.1 대기열 작업

![대기열 작업 안내](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(동영상: 대기열 작업 관리)*

1. 왼쪽 메뉴에서 **{{t:common.navigation.queue}}** 탭을 클릭합니다.

![대기열 페이지](/assets/images/user-guide/87_queue_button.png)
*(그림 87: 대기열 페이지 - 필터링 옵션 및 상태 탭)*

2. 대기열 항목을 필터링하려면:
   - **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}**, **{{t:queue.trace.bridge}}** 필터 사용
   - **{{t:system.audit.filters.dateRange}}** 지정
   - **{{t:queue.filters.onlyStale}}** 옵션 선택

3. 상태 탭에서 세부 정보를 확인합니다:
   - **{{t:queue.statusActive}}**: 처리 중인 작업
   - **{{t:queue.statusCompleted}}**: 성공적으로 완료된 작업
   - **{{t:queue.statusCancelled}}**: 취소된 작업
   - **{{t:queue.statusFailed}}**: 실패한 작업

4. **{{t:common.actions.export}}** 버튼에서 형식을 선택합니다: **{{t:common.exportCSV}}** 또는 **{{t:common.exportJSON}}**.

![대기열 내보내기](/assets/images/user-guide/88_queue_export.png)
*(그림 88: 대기열 목록 - 내보내기 옵션)*

> **팁**: "{{t:queue.filters.onlyStale}}" 옵션은 오랫동안 처리 중인 작업을 찾는 데 도움이 됩니다. 작업 실행 추세를 분석하기 위해 대기열 내역을 정기적으로 내보내세요.

---

## 2.11 감사 (Audit)

감사 섹션은 시스템에서 수행된 모든 작업의 기록을 유지합니다.

### 2.11.1 감사 레코드

![감사 레코드 안내](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(동영상: 시스템 감사 레코드 보기)*

1. 왼쪽 메뉴에서 **{{t:common.navigation.audit}}** 탭을 클릭합니다.

![감사 목록](/assets/images/user-guide/89_audit_list.png)
*(그림 89: 감사 페이지 - 모든 시스템 작업의 상세 기록)*

2. 감사 레코드를 필터링합니다:
   - **날짜 범위**: 특정 기간으로 필터링
   - **엔티티 유형**: Request, Machine, Queue 등으로 필터링
   - **검색**: 텍스트 검색 수행

3. 각 레코드의 정보를 검토합니다:
   - **Timestamp**: 작업의 날짜 및 시간
   - **Action**: 작업 유형(생성, 편집, 삭제 등)
   - **Entity Type**: 영향받은 객체의 유형
   - **Entity Name**: 특정 객체 식별자
   - **User**: 작업을 수행한 사용자
   - **Details**: 작업에 대한 추가 정보

4. **{{t:common.actions.export}}** 버튼에서 형식을 선택합니다: **{{t:common.exportCSV}}** 또는 **{{t:common.exportJSON}}**.

![감사 내보내기](/assets/images/user-guide/90_audit_export.png)
*(그림 90: 감사 레코드 내보내기 - CSV 및 JSON 옵션)*

> **팁**: 감사 레코드는 보안 및 규정 준수 목적으로 모든 시스템 활동을 추적하는 데 매우 중요합니다. 감사 레코드를 정기적으로 내보내고 안전한 위치에 보관하세요.

---

**© 2025 Rediacc Platform - All Rights Reserved.**
