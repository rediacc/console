import React, { useState } from 'react'
import { Button, Tooltip, Modal, List, Popconfirm, Tabs, Card, Space, Tag } from 'antd'
import {
  UserOutlined,
  DeleteOutlined,
  PlusOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import ResourceListView from '@/components/common/ResourceListView'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import { ModalSize } from '@/types/modal'
import { useDropdownData } from '@/api/queries/useDropdownData'
import {
  useTeams,
  useTeamMembers,
  useCreateTeam,
  useUpdateTeamName,
  useDeleteTeam,
  useUpdateTeamVault,
  useAddTeamMember,
  useRemoveTeamMember,
  Team,
  TeamMember,
} from '@/api/queries/teams'
import {
  PageWrapper,
  SectionStack,
  SectionHeading,
  ListTitleRow,
  ListTitle,
  ListSubtitle,
  InlineFormRow,
  ModalStack,
} from '@/components/ui'
import { FullWidthSelect } from '@/pages/system/styles'
import { getTeamColumns } from './data'

const TeamsPage: React.FC = () => {
  const { t } = useTranslation('organization')
  const { t: tSystem } = useTranslation('system')
  const { t: tCommon } = useTranslation('common')

  const { data: dropdownData } = useDropdownData()
  const { data: teams = [], isLoading: teamsLoading } = useTeams()
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null)
  const [isManageTeamModalOpen, setIsManageTeamModalOpen] = useState(false)
  const [selectedMemberEmail, setSelectedMemberEmail] = useState('')
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })
  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    mode: 'create' | 'edit'
    data?: Team | null
  }>({ open: false, mode: 'create' })

  const { data: teamMembers = [], isLoading: membersLoading } = useTeamMembers(selectedTeam?.teamName || '')
  const createTeamMutation = useCreateTeam()
  const updateTeamNameMutation = useUpdateTeamName()
  const deleteTeamMutation = useDeleteTeam()
  const updateTeamVaultMutation = useUpdateTeamVault()
  const addTeamMemberMutation = useAddTeamMember()
  const removeTeamMemberMutation = useRemoveTeamMember()

  const openUnifiedModal = (mode: 'create' | 'edit', data?: Team) => {
    setUnifiedModalState({ open: true, mode, data })
  }

  const closeUnifiedModal = () => {
    setUnifiedModalState({ open: false, mode: 'create', data: null })
  }

  const handleUnifiedModalSubmit = async (data: Partial<Team> & { teamVault?: string }) => {
    try {
      if (unifiedModalState.mode === 'create') {
        if (!data.teamName) {
          throw new Error('Team name is required')
        }
        await createTeamMutation.mutateAsync({ teamName: data.teamName, teamVault: data.teamVault })
      } else if (unifiedModalState.data) {
        if (data.teamName && data.teamName !== unifiedModalState.data.teamName) {
          await updateTeamNameMutation.mutateAsync({
            currentTeamName: unifiedModalState.data.teamName,
            newTeamName: data.teamName,
          })
        }

        if (data.teamVault && data.teamVault !== unifiedModalState.data.vaultContent) {
          await updateTeamVaultMutation.mutateAsync({
            teamName: data.teamName || unifiedModalState.data.teamName,
            teamVault: data.teamVault,
            vaultVersion: unifiedModalState.data.vaultVersion + 1,
          })
        }
      }
      closeUnifiedModal()
    } catch {
      // handled by mutation
    }
  }

  const handleUnifiedVaultUpdate = async (vault: string, version: number) => {
    if (!unifiedModalState.data) return

    try {
      await updateTeamVaultMutation.mutateAsync({
        teamName: unifiedModalState.data.teamName,
        teamVault: vault,
        vaultVersion: version,
      })
    } catch {
      // handled by mutation
    }
  }

  const handleDeleteTeam = async (teamName: string) => {
    try {
      await deleteTeamMutation.mutateAsync(teamName)
    } catch {
      // handled by mutation
    }
  }

  const handleAddTeamMember = async () => {
    if (!selectedTeam || !selectedMemberEmail) return

    try {
      await addTeamMemberMutation.mutateAsync({
        teamName: selectedTeam.teamName,
        newUserEmail: selectedMemberEmail,
      })
      setSelectedMemberEmail('')
    } catch {
      // handled by mutation
    }
  }

  const handleRemoveTeamMember = async (userEmail: string) => {
    if (!selectedTeam) return

    try {
      await removeTeamMemberMutation.mutateAsync({
        teamName: selectedTeam.teamName,
        removeUserEmail: userEmail,
      })
    } catch {
      // handled by mutation
    }
  }

  const teamColumns = getTeamColumns({
    tSystem,
    tCommon,
    onEdit: (team) => openUnifiedModal('edit', team),
    onManageMembers: (team) => {
      setSelectedTeam(team)
      setIsManageTeamModalOpen(true)
    },
    onTrace: (team) =>
      setAuditTraceModal({
        open: true,
        entityType: 'Team',
        entityIdentifier: team.teamName,
        entityName: team.teamName,
      }),
    onDelete: handleDeleteTeam,
    isDeleting: deleteTeamMutation.isPending,
  })

  return (
    <PageWrapper>
      <SectionStack>
        <SectionHeading level={3}>{t('teams.heading', { defaultValue: 'Teams' })}</SectionHeading>
        <ResourceListView<Team>
          title={
            <ListTitleRow>
              <ListTitle>{t('teams.title', { defaultValue: 'Teams' })}</ListTitle>
              <ListSubtitle>{t('teams.subtitle', { defaultValue: 'Manage teams and their members' })}</ListSubtitle>
            </ListTitleRow>
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
                onClick={() => openUnifiedModal('create')}
                data-testid="system-create-team-button"
                aria-label={tSystem('actions.createTeam')}
              />
            </Tooltip>
          }
        />
      </SectionStack>

      <Modal
        title={t('teams.manageMembers.title', {
          defaultValue: `Manage Team Members${selectedTeam ? ` - ${selectedTeam.teamName}` : ''}`,
          teamName: selectedTeam?.teamName,
        })}
        open={isManageTeamModalOpen}
        onCancel={() => {
          setIsManageTeamModalOpen(false)
          setSelectedTeam(null)
          setSelectedMemberEmail('')
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
                    locale={{ emptyText: t('teams.manageMembers.empty', { defaultValue: 'No members in this team' }) }}
                    renderItem={(member: TeamMember) => (
                      <List.Item
                        actions={[
                          <Popconfirm
                            key="remove"
                            title={t('teams.manageMembers.removeTitle', { defaultValue: 'Remove Team Member' })}
                            description={t('teams.manageMembers.removeDescription', {
                              defaultValue: 'Are you sure you want to remove "{{email}}" from this team?',
                              email: member.userEmail,
                            })}
                            onConfirm={() => handleRemoveTeamMember(member.userEmail)}
                            okText={tCommon('general.yes')}
                            cancelText={tCommon('general.no')}
                            okButtonProps={{ danger: true }}
                          >
                            <Tooltip title={tCommon('actions.remove')}>
                              <Button
                                type="primary"
                                danger
                                size="small"
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
                              {member.isMember && <Tag color="green">{t('teams.manageMembers.memberStatus', { defaultValue: 'Member' })}</Tag>}
                              {member.hasAccess && <Tag color="blue">{t('teams.manageMembers.accessStatus', { defaultValue: 'Has Access' })}</Tag>}
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
                <ModalStack>
                  <InlineFormRow>
                    <FullWidthSelect
                      showSearch
                      placeholder={t('teams.manageMembers.selectUser', { defaultValue: 'Select user' })}
                      value={selectedMemberEmail || undefined}
                      onChange={(value) => setSelectedMemberEmail((value as string) || '')}
                      filterOption={(input, option) =>
                        String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                      options={
                        dropdownData?.users
                          ?.filter((user) => user.status === 'active')
                          ?.map((user) => ({
                            value: user.value,
                            label: user.label,
                            disabled: teamMembers.some((member: TeamMember) => member.userEmail === user.value && member.isMember),
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
                  </InlineFormRow>
                </ModalStack>
              ),
            },
          ]}
        />
      </Modal>

      <UnifiedResourceModal
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType="team"
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data ?? undefined}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        isSubmitting={createTeamMutation.isPending || updateTeamNameMutation.isPending}
        isUpdatingVault={updateTeamVaultMutation.isPending}
      />

      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />
    </PageWrapper>
  )
}

export default TeamsPage
