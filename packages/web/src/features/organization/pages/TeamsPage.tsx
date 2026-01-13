import React, { useCallback, useMemo, useState } from 'react';
import {
  Badge,
  Card,
  Flex,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
  type MenuProps,
} from 'antd';
import { useTranslation } from 'react-i18next';
import {
  useCreateTeamMembership,
  useCreateTeam,
  useDeleteTeam,
  useDeleteUserFromTeam,
  useGetTeamMembers,
  useGetOrganizationTeams,
  useUpdateTeamName,
  useUpdateTeamVault,
} from '@/api/api-hooks.generated';
import { useDropdownData } from '@/api/queries/useDropdownData';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { TooltipButton } from '@/components/common/buttons';
import { buildTeamColumns } from '@/components/common/columns/builders/teamColumns';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildMembersMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { PageHeader } from '@/components/common/PageHeader';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import UnifiedResourceModal, {
  type ExistingResourceData,
} from '@/components/common/UnifiedResourceModal';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { useFormModal } from '@/hooks/useFormModal';
import { ModalSize } from '@/types/modal';
import { minifyJSON } from '@/platform/utils/json';
import {
  CloudServerOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DesktopOutlined,
  PlusOutlined,
  TeamOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type {
  GetOrganizationTeams_ResultSet1,
  GetTeamMembers_ResultSet1,
} from '@rediacc/shared/types';

const TeamsPage: React.FC = () => {
  const { t } = useTranslation('organization');
  const { t: tSystem } = useTranslation('system');
  const { t: tCommon } = useTranslation('common');

  const { data: dropdownData } = useDropdownData();
  const { data: teams = [], isLoading: teamsLoading } = useGetOrganizationTeams();
  const manageTeamModal = useDialogState<GetOrganizationTeams_ResultSet1>();
  const [selectedMemberEmail, setSelectedMemberEmail] = useState('');
  const auditTrace = useTraceModal();
  const unifiedModal = useFormModal<ExistingResourceData>();

  const { data: teamMembers = [], isLoading: membersLoading } = useGetTeamMembers(
    manageTeamModal.state.data?.teamName ?? ''
  );
  const createTeamMutation = useCreateTeam();
  const updateTeamNameMutation = useUpdateTeamName();
  const deleteTeamMutation = useDeleteTeam();
  const updateTeamVaultMutation = useUpdateTeamVault();
  const addTeamMemberMutation = useCreateTeamMembership();
  const removeTeamMemberMutation = useDeleteUserFromTeam();

  const handleCreateTeam = async (
    data: Partial<GetOrganizationTeams_ResultSet1> & { vaultContent?: string }
  ) => {
    if (!data.teamName) {
      throw new Error('Team name is required');
    }
    await createTeamMutation.mutateAsync({
      teamName: data.teamName,
      vaultContent: data.vaultContent ?? '{}',
    });
  };

  const handleEditTeam = async (
    data: Partial<GetOrganizationTeams_ResultSet1> & { vaultContent?: string },
    existingData: GetOrganizationTeams_ResultSet1
  ) => {
    if (!existingData.teamName) {
      throw new Error('Team name is required');
    }

    if (data.teamName && data.teamName !== existingData.teamName) {
      await updateTeamNameMutation.mutateAsync({
        currentTeamName: existingData.teamName,
        newTeamName: data.teamName,
      });
    }

    const nextVault = data.vaultContent ?? '{}';
    const currentVault = existingData.vaultContent ?? '{}';
    const vaultHasChanges = minifyJSON(nextVault) !== minifyJSON(currentVault);

    if (data.vaultContent && vaultHasChanges) {
      await updateTeamVaultMutation.mutateAsync({
        teamName: data.teamName ?? existingData.teamName,
        vaultContent: nextVault,
        vaultVersion: (existingData.vaultVersion ?? 0) + 1,
      });
    }
  };

  const handleUnifiedModalSubmit = async (
    data: Partial<GetOrganizationTeams_ResultSet1> & { vaultContent?: string }
  ) => {
    try {
      if (unifiedModal.mode === 'create') {
        await handleCreateTeam(data);
      } else if (unifiedModal.state.data) {
        await handleEditTeam(data, unifiedModal.state.data as GetOrganizationTeams_ResultSet1);
      }
      unifiedModal.close();
    } catch {
      // handled by mutation
    }
  };

  const handleUnifiedVaultUpdate = async (vault: string, version: number) => {
    if (!unifiedModal.state.data?.teamName) return;

    try {
      await updateTeamVaultMutation.mutateAsync({
        teamName: unifiedModal.state.data.teamName,
        vaultContent: vault,
        vaultVersion: version,
      });
    } catch {
      // handled by mutation
    }
  };

  const handleDeleteTeam = useCallback(
    async (teamName: string) => {
      try {
        await deleteTeamMutation.mutateAsync({ teamName });
      } catch {
        // handled by mutation
      }
    },
    [deleteTeamMutation]
  );

  const handleAddTeamMember = async () => {
    if (!manageTeamModal.state.data || !selectedMemberEmail) return;

    try {
      await addTeamMemberMutation.mutateAsync({
        teamName: manageTeamModal.state.data.teamName,
        newUserEmail: selectedMemberEmail,
      });
      setSelectedMemberEmail('');
    } catch {
      // handled by mutation
    }
  };

  const handleRemoveTeamMember = async (userEmail: string) => {
    if (!manageTeamModal.state.data) return;

    try {
      await removeTeamMemberMutation.mutateAsync({
        teamName: manageTeamModal.state.data.teamName,
        removeUserEmail: userEmail,
      });
    } catch {
      // handled by mutation
    }
  };

  const columnParams = {
    t,
    onEdit: (team: GetOrganizationTeams_ResultSet1) =>
      unifiedModal.openEdit({
        ...team,
        teamName: team.teamName ?? undefined,
      } as ExistingResourceData),
    onManageMembers: (team: GetOrganizationTeams_ResultSet1) => {
      manageTeamModal.open(team);
    },
    onTrace: (team: GetOrganizationTeams_ResultSet1) =>
      auditTrace.open({
        entityType: 'Team',
        entityIdentifier: team.teamName ?? '',
        entityName: team.teamName ?? undefined,
      }),
    onDelete: handleDeleteTeam,
    isDeleting: deleteTeamMutation.isPending,
  };

  const teamColumns = buildTeamColumns(columnParams);

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetOrganizationTeams_ResultSet1) => {
      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(tCommon, () =>
          unifiedModal.openEdit({
            ...record,
            teamName: record.teamName ?? undefined,
          } as ExistingResourceData)
        ),
        buildMembersMenuItem(tCommon, () => manageTeamModal.open(record)),
        buildTraceMenuItem(tCommon, () =>
          auditTrace.open({
            entityType: 'Team',
            entityIdentifier: record.teamName ?? '',
            entityName: record.teamName ?? undefined,
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(tCommon, () => handleDeleteTeam(record.teamName ?? '')),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <TeamOutlined />
            <Typography.Text strong className="truncate">
              {record.teamName}
            </Typography.Text>
          </Space>
          <Flex className="gap-sm" wrap>
            <Space size="small">
              <Badge count={record.memberCount} showZero size="small">
                <UserOutlined />
              </Badge>
            </Space>
            <Space size="small">
              <DesktopOutlined />
              <Typography.Text>{record.machineCount}</Typography.Text>
            </Space>
            <Space size="small">
              <DatabaseOutlined />
              <Typography.Text>{record.repositoryCount ?? 0}</Typography.Text>
            </Space>
            <Space size="small">
              <CloudServerOutlined />
              <Typography.Text>{record.storageCount ?? 0}</Typography.Text>
            </Space>
          </Flex>
        </MobileCard>
      );
    },
    [tCommon, unifiedModal, manageTeamModal, auditTrace, handleDeleteTeam]
  );

  return (
    <Flex vertical>
      <ResourceListView<GetOrganizationTeams_ResultSet1>
        title={<PageHeader title={t('teams.title')} subtitle={t('teams.subtitle')} />}
        loading={teamsLoading}
        data={teams}
        columns={teamColumns}
        mobileRender={mobileRender}
        rowKey="teamName"
        searchPlaceholder={t('teams.searchPlaceholder')}
        data-testid="system-team-table"
        actions={
          <TooltipButton
            tooltip={tSystem('actions.createTeam')}
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => unifiedModal.openCreate()}
            data-testid="system-create-team-button"
          />
        }
      />

      <Modal
        title={`${t('teams.manageMembers.title')}${manageTeamModal.state.data ? ` - ${manageTeamModal.state.data.teamName}` : ''}`}
        open={manageTeamModal.isOpen}
        onCancel={() => {
          manageTeamModal.close();
          setSelectedMemberEmail('');
        }}
        footer={null}
        className={ModalSize.Large}
        centered
        data-testid="teams-manage-members-modal"
      >
        <Tabs
          items={[
            {
              key: 'current',
              label: t('teams.manageMembers.currentTab'),
              children: (
                <Card>
                  <List
                    dataSource={teamMembers}
                    loading={membersLoading}
                    locale={{
                      emptyText: t('teams.manageMembers.empty'),
                    }}
                    renderItem={(member: GetTeamMembers_ResultSet1) => (
                      <List.Item
                        actions={[
                          <Popconfirm
                            key="remove"
                            title={t('teams.manageMembers.removeTitle')}
                            description={t('teams.manageMembers.removeDescription', {
                              email: member.userEmail,
                            })}
                            onConfirm={() => handleRemoveTeamMember(member.userEmail ?? '')}
                            okText={tCommon('general.yes')}
                            cancelText={tCommon('general.no')}
                            okButtonProps={{ danger: true }}
                          >
                            <TooltipButton
                              tooltip={tCommon('actions.remove')}
                              type="text"
                              danger
                              loading={removeTeamMemberMutation.isPending}
                              icon={<DeleteOutlined />}
                            />
                          </Popconfirm>,
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<UserOutlined />}
                          title={member.userEmail}
                          description={
                            <Space size="small">
                              {member.isMember && (
                                <Tag>{t('teams.manageMembers.memberStatus')}</Tag>
                              )}
                              {member.hasAccess && (
                                <Tag>{t('teams.manageMembers.accessStatus')}</Tag>
                              )}
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              ),
            },
            {
              key: 'add',
              label: t('teams.manageMembers.addTab'),
              children: (
                <Flex vertical>
                  <Flex align="center" wrap>
                    <Select
                      showSearch
                      placeholder={t('teams.manageMembers.selectUser')}
                      value={selectedMemberEmail || undefined}
                      onChange={(value) => setSelectedMemberEmail(value || '')}
                      className="flex-1"
                      filterOption={(input, option) =>
                        String(option?.label ?? '')
                          .toLowerCase()
                          .includes(input.toLowerCase())
                      }
                      options={(dropdownData?.users ?? [])
                        .filter((user) => user.status === 'active')
                        .map((user) => ({
                          value: user.value,
                          label: user.label,
                          disabled: teamMembers.some(
                            (member: GetTeamMembers_ResultSet1) =>
                              member.userEmail === user.value && member.isMember
                          ),
                        }))}
                    />
                    <TooltipButton
                      tooltip={tSystem('actions.addMember')}
                      type="primary"
                      onClick={handleAddTeamMember}
                      loading={addTeamMemberMutation.isPending}
                      disabled={!selectedMemberEmail}
                      icon={<PlusOutlined />}
                    />
                  </Flex>
                </Flex>
              ),
            },
          ]}
        />
      </Modal>

      <UnifiedResourceModal
        open={unifiedModal.isOpen}
        onCancel={unifiedModal.close}
        resourceType="team"
        mode={unifiedModal.mode}
        existingData={unifiedModal.state.data ?? undefined}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModal.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        isSubmitting={[createTeamMutation.isPending, updateTeamNameMutation.isPending].some(
          Boolean
        )}
        isUpdatingVault={updateTeamVaultMutation.isPending}
      />

      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />
    </Flex>
  );
};

export default TeamsPage;
