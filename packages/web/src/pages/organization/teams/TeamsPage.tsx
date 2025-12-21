import React, { useState } from 'react';
import {
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
import ResourceListView from '@/components/common/ResourceListView';
import UnifiedResourceModal, {
  type ExistingResourceData,
} from '@/components/common/UnifiedResourceModal';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { useFormModal } from '@/hooks/useFormModal';
import { ModalSize } from '@/types/modal';
import { DeleteOutlined, PlusOutlined, UserOutlined } from '@/utils/optimizedIcons';
import { getTeamColumns } from './data';

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
    manageTeamModal.state.data?.teamName || ''
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
            teamName: data.teamName || existingData.teamName,
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

  const handleDeleteTeam = async (teamName: string) => {
    try {
      await deleteTeamMutation.mutateAsync({ teamName });
    } catch {
      // handled by mutation
    }
  };

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

  const teamColumns = getTeamColumns({
    tSystem,
    tCommon,
    onEdit: (team) => unifiedModal.openEdit(team as ExistingResourceData),
    onManageMembers: (team) => {
      manageTeamModal.open(team);
    },
    onTrace: (team) =>
      auditTrace.open({
        entityType: 'Team',
        entityIdentifier: team.teamName,
        entityName: team.teamName,
      }),
    onDelete: handleDeleteTeam,
    isDeleting: deleteTeamMutation.isPending,
  });

  return (
    <Flex vertical>
      <ResourceListView<Team>
        title={
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{t('teams.title', { defaultValue: 'Teams' })}</Typography.Text>
            <Typography.Text type="secondary">
              {t('teams.subtitle', { defaultValue: 'Manage teams and their members' })}
            </Typography.Text>
          </Space>
        }
        loading={teamsLoading}
        data={teams}
        columns={teamColumns}
        rowKey="teamName"
        searchPlaceholder={t('teams.searchPlaceholder', { defaultValue: 'Search teams...' })}
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
        title={t('teams.manageMembers.title', {
          defaultValue: `Manage Team Members${manageTeamModal.state.data ? ` - ${manageTeamModal.state.data.teamName}` : ''}`,
          teamName: manageTeamModal.state.data?.teamName,
        })}
        open={manageTeamModal.isOpen}
        onCancel={() => {
          manageTeamModal.close();
          setSelectedMemberEmail('');
        }}
        footer={null}
        className={ModalSize.Large}
      >
        <Tabs
          items={[
            {
              key: 'current',
              label: t('teams.manageMembers.currentTab', { defaultValue: 'Current Members' }),
              children: (
                <Card>
                  <List
                    dataSource={teamMembers}
                    loading={membersLoading}
                    locale={{
                      emptyText: t('teams.manageMembers.empty', {
                        defaultValue: 'No members in this team',
                      }),
                    }}
                    renderItem={(member: TeamMember) => (
                      <List.Item
                        actions={[
                          <Popconfirm
                            key="remove"
                            title={t('teams.manageMembers.removeTitle', {
                              defaultValue: 'Remove Team Member',
                            })}
                            description={t('teams.manageMembers.removeDescription', {
                              defaultValue:
                                'Are you sure you want to remove "{{email}}" from this team?',
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
                                <Tag color="success">
                                  {t('teams.manageMembers.memberStatus', {
                                    defaultValue: 'Member',
                                  })}
                                </Tag>
                              )}
                              {member.hasAccess && (
                                <Tag color="processing">
                                  {t('teams.manageMembers.accessStatus', {
                                    defaultValue: 'Has Access',
                                  })}
                                </Tag>
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
              label: t('teams.manageMembers.addTab', { defaultValue: 'Add Member' }),
              children: (
                <Flex vertical gap={16}>
                  <Flex gap={12} align="center" wrap>
                    <Select
                      showSearch
                      placeholder={t('teams.manageMembers.selectUser', {
                        defaultValue: 'Select user',
                      })}
                      value={selectedMemberEmail ?? undefined}
                      onChange={(value) => setSelectedMemberEmail((value as string) || '')}
                      style={{ flex: 1, minWidth: 260 }}
                      filterOption={(input, option) =>
                        String(option?.label ?? '')
                          .toLowerCase()
                          .includes(input.toLowerCase())
                      }
                      options={
                        dropdownData?.users
                          ?.filter((user) => user.status === 'active')
                          ?.map((user) => ({
                            value: user.value,
                            label: user.label,
                            disabled: teamMembers.some(
                              (member: TeamMember) =>
                                member.userEmail === user.value && member.isMember
                            ),
                          })) || []
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
