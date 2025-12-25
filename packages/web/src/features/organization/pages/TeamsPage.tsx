import React, { useCallback, useMemo, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Flex,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  type MenuProps,
} from 'antd';
import { useTranslation } from 'react-i18next';
import {
  Team,
  TeamMember,
  useAddTeamMember,
  useCreateTeam,
  useDeleteTeam,
  useRemoveTeamMember,
  useTeamMembers,
  useTeams,
  useUpdateTeamName,
  useUpdateTeamVault,
} from '@/api/queries/teams';
import { useDropdownData } from '@/api/queries/useDropdownData';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { buildTeamColumns } from '@/components/common/columns/builders/teamColumns';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import UnifiedResourceModal, {
  type ExistingResourceData,
} from '@/components/common/UnifiedResourceModal';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { useFormModal } from '@/hooks/useFormModal';
import { ModalSize } from '@/types/modal';
import {
  CloudServerOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DesktopOutlined,
  PlusOutlined,
  TeamOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';

const TeamsPage: React.FC = () => {
  const { t } = useTranslation('organization');
  const { t: tSystem } = useTranslation('system');
  const { t: tCommon } = useTranslation('common');

  const { data: dropdownData } = useDropdownData();
  const { data: teams = [], isLoading: teamsLoading } = useTeams();
  const manageTeamModal = useDialogState<Team>();
  const [selectedMemberEmail, setSelectedMemberEmail] = useState('');
  const auditTrace = useTraceModal();
  const unifiedModal = useFormModal<ExistingResourceData>();

  const { data: teamMembers = [], isLoading: membersLoading } = useTeamMembers(
    manageTeamModal.state.data?.teamName ?? ''
  );
  const createTeamMutation = useCreateTeam();
  const updateTeamNameMutation = useUpdateTeamName();
  const deleteTeamMutation = useDeleteTeam();
  const updateTeamVaultMutation = useUpdateTeamVault();
  const addTeamMemberMutation = useAddTeamMember();
  const removeTeamMemberMutation = useRemoveTeamMember();

  const handleUnifiedModalSubmit = async (data: Partial<Team> & { vaultContent?: string }) => {
    try {
      if (unifiedModal.mode === 'create') {
        if (!data.teamName) {
          throw new Error('Team name is required');
        }
        await createTeamMutation.mutateAsync({
          teamName: data.teamName,
          vaultContent: data.vaultContent,
        });
      } else if (unifiedModal.state.data) {
        const existingData = unifiedModal.state.data;
        if (!existingData.teamName) {
          throw new Error('Team name is required');
        }

        if (data.teamName && data.teamName !== existingData.teamName) {
          await updateTeamNameMutation.mutateAsync({
            currentTeamName: existingData.teamName,
            newTeamName: data.teamName,
          });
        }

        if (data.vaultContent && data.vaultContent !== existingData.vaultContent) {
          await updateTeamVaultMutation.mutateAsync({
            teamName: data.teamName ?? existingData.teamName,
            vaultContent: data.vaultContent,
            vaultVersion: (existingData.vaultVersion ?? 0) + 1,
          });
        }
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
    tSystem,
    tCommon,
    onEdit: (team: Team) => unifiedModal.openEdit(team as ExistingResourceData),
    onManageMembers: (team: Team) => {
      manageTeamModal.open(team);
    },
    onTrace: (team: Team) =>
      auditTrace.open({
        entityType: 'Team',
        entityIdentifier: team.teamName,
        entityName: team.teamName,
      }),
    onDelete: handleDeleteTeam,
    isDeleting: deleteTeamMutation.isPending,
  };

  const teamColumns = buildTeamColumns(columnParams);

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: Team) => {
      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(tCommon, () => unifiedModal.openEdit(record as ExistingResourceData)),
        {
          key: 'members',
          label: tSystem('actions.members'),
          icon: <UserOutlined />,
          onClick: () => manageTeamModal.open(record),
        },
        buildTraceMenuItem(tCommon, () =>
          auditTrace.open({
            entityType: 'Team',
            entityIdentifier: record.teamName,
            entityName: record.teamName,
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(tCommon, () => handleDeleteTeam(record.teamName)),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <TeamOutlined />
            <Typography.Text strong className="truncate">
              {record.teamName}
            </Typography.Text>
          </Space>
          <Flex gap={16} wrap>
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
    [tSystem, tCommon, unifiedModal, manageTeamModal, auditTrace, handleDeleteTeam]
  );

  return (
    <Flex vertical>
      <ResourceListView<Team>
        title={
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{t('teams.title')}</Typography.Text>
            <Typography.Text>{t('teams.subtitle')}</Typography.Text>
          </Space>
        }
        loading={teamsLoading}
        data={teams}
        columns={teamColumns}
        mobileRender={mobileRender}
        rowKey="teamName"
        searchPlaceholder={t('teams.searchPlaceholder')}
        data-testid="system-team-table"
        actions={
          <Tooltip title={tSystem('actions.createTeam')}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => unifiedModal.openCreate()}
              data-testid="system-create-team-button"
              aria-label={tSystem('actions.createTeam')}
            />
          </Tooltip>
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
                    renderItem={(member: TeamMember) => (
                      <List.Item
                        actions={[
                          <Popconfirm
                            key="remove"
                            title={t('teams.manageMembers.removeTitle')}
                            description={t('teams.manageMembers.removeDescription', {
                              email: member.userEmail,
                            })}
                            onConfirm={() => handleRemoveTeamMember(member.userEmail)}
                            okText={tCommon('general.yes')}
                            cancelText={tCommon('general.no')}
                            okButtonProps={{ danger: true }}
                          >
                            <Tooltip title={tCommon('actions.remove')}>
                              <Button
                                type="text"
                                danger
                                loading={removeTeamMemberMutation.isPending}
                                icon={<DeleteOutlined />}
                                aria-label={tCommon('actions.remove')}
                              />
                            </Tooltip>
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
                <Flex vertical gap={16}>
                  <Flex gap={12} align="center" wrap>
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
                      options={
                        dropdownData?.users
                          .filter((user) => user.status === 'active')
                          .map((user) => ({
                            value: user.value,
                            label: user.label,
                            disabled: teamMembers.some(
                              (member: TeamMember) =>
                                member.userEmail === user.value && member.isMember
                            ),
                          })) ?? []
                      }
                    />
                    <Tooltip title={tSystem('actions.addMember')}>
                      <Button
                        type="primary"
                        onClick={handleAddTeamMember}
                        loading={addTeamMemberMutation.isPending}
                        disabled={!selectedMemberEmail}
                        icon={<PlusOutlined />}
                        aria-label={tSystem('actions.addMember')}
                      />
                    </Tooltip>
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
        isSubmitting={createTeamMutation.isPending || updateTeamNameMutation.isPending}
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
