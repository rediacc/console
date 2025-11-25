import React, { type ReactNode } from 'react'
import {
  DatabaseOutlined,
  CloudServerOutlined,
  HddOutlined,
  CopyOutlined,
  HistoryOutlined,
  RightOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { Machine, MachineAssignmentType } from '@/types'
import { useMachineAssignmentStatus } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from '../../MachineAssignmentStatusBadge'
import {
  LoadingState,
  SectionDivider,
  DividerContent,
  SectionTitle,
  SectionCard,
  ContentStack,
  AssignmentLabel,
  AlertWrapper,
  AlertMessage,
  ActionsRow,
  ActionButton,
  ButtonLabel
} from './styles'
import LoadingWrapper from '@/components/common/LoadingWrapper'
import { IconWrapper } from '@/components/ui'

interface DistributedStorageSectionProps {
  machine: Machine
  onViewDetails?: () => void
  onManageAssignment?: () => void
}

const getAssignmentIcon = (assignmentType: MachineAssignmentType): ReactNode => {
  switch (assignmentType) {
    case 'CLUSTER':
      return <DatabaseOutlined />
    case 'IMAGE':
      return <HddOutlined />
    case 'CLONE':
      return <CopyOutlined />
    case 'AVAILABLE':
    default:
      return <CloudServerOutlined />
  }
}

export const DistributedStorageSection: React.FC<DistributedStorageSectionProps> = ({
  machine,
  onViewDetails,
  onManageAssignment,
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines'])

  const hasClusterAssignment = Boolean(machine.distributedStorageClusterName)

  const { data: assignmentData, isLoading } = useMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    !hasClusterAssignment
  )

  const assignmentType: MachineAssignmentType = hasClusterAssignment
    ? 'CLUSTER'
    : ((assignmentData?.assignmentType as MachineAssignmentType) ?? 'AVAILABLE')

  const assignmentDetails = hasClusterAssignment
    ? `Assigned to cluster: ${machine.distributedStorageClusterName}`
    : assignmentData?.assignmentDetails

  if (isLoading) {
    return (
      <LoadingState data-testid="ds-section-loading">
        <LoadingWrapper loading centered minHeight={120}>
          <div />
        </LoadingWrapper>
      </LoadingState>
    )
  }

  const showAssignmentAlert = assignmentType !== 'AVAILABLE' && Boolean(assignmentDetails)

  return (
    <>
      <SectionDivider data-testid="ds-section-divider">
        <DividerContent>
          <IconWrapper $size="lg">
            <CloudServerOutlined />
          </IconWrapper>
          <SectionTitle>{t('machineSection.title')}</SectionTitle>
        </DividerContent>
      </SectionDivider>

      <SectionCard size="small" data-testid="ds-section-card">
        <ContentStack>
          <div>
            <AssignmentLabel data-testid="ds-section-assignment-label">
              {t('assignment.currentAssignment')}
            </AssignmentLabel>
            <MachineAssignmentStatusBadge
              assignmentType={assignmentType}
              assignmentDetails={assignmentDetails}
              size="default"
              data-testid="ds-section-assignment-badge"
            />
          </div>

          {showAssignmentAlert && assignmentDetails && (
            <AlertWrapper
              message={<AlertMessage>{assignmentDetails}</AlertMessage>}
              type="info"
              showIcon
              icon={
                <IconWrapper $size="sm" $tone="info">
                  {getAssignmentIcon(assignmentType)}
                </IconWrapper>
              }
              data-testid="ds-section-assignment-alert"
            />
          )}

          <ActionsRow>
            {onViewDetails && (
              <ActionButton
                icon={
                  <IconWrapper $size="sm" $tone="muted">
                    <HistoryOutlined />
                  </IconWrapper>
                }
                onClick={onViewDetails}
                data-testid="ds-section-history-button"
              >
                <ButtonLabel>{t('assignment.history')}</ButtonLabel>
              </ActionButton>
            )}

            {onManageAssignment && assignmentType !== 'AVAILABLE' && (
              <ActionButton
                type="primary"
                icon={
                  <IconWrapper $size="sm">
                    <RightOutlined />
                  </IconWrapper>
                }
                onClick={onManageAssignment}
                data-testid="ds-section-manage-button"
              >
                <ButtonLabel>{t('machineSection.manageAssignment')}</ButtonLabel>
              </ActionButton>
            )}
          </ActionsRow>

          {assignmentType !== 'AVAILABLE' && (
            <AlertWrapper
              message={<AlertMessage>{t('warnings.exclusivity')}</AlertMessage>}
              type="warning"
              showIcon
              icon={
                <IconWrapper $size="sm" $tone="warning">
                  <CloudServerOutlined />
                </IconWrapper>
              }
              data-testid="ds-section-exclusivity-warning"
            />
          )}
        </ContentStack>
      </SectionCard>
    </>
  )
}
