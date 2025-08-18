import React from 'react'
import { 
  Card, 
  Space, 
  Typography, 
  Divider, 
  Empty, 
  Button, 
  Timeline,
  Tag,
  Spin,
  Alert
} from 'antd'
import { 
  DatabaseOutlined,
  CloudServerOutlined,
  HddOutlined,
  CopyOutlined,
  HistoryOutlined,
  RightOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { Machine } from '@/types'
import { useGetMachineAssignmentStatus } from '@/api/queries/distributedStorage'
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge'
import { useComponentStyles } from '@/hooks/useComponentStyles'

const { Text, Title } = Typography

interface DistributedStorageSectionProps {
  machine: Machine
  onViewDetails?: () => void
  onManageAssignment?: () => void
}

export const DistributedStorageSection: React.FC<DistributedStorageSectionProps> = ({ 
  machine,
  onViewDetails,
  onManageAssignment
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines'])
  const styles = useComponentStyles()
  
  // If machine already has distributedStorageClusterName, we know it's assigned to a cluster
  const hasClusterAssignment = !!machine.distributedStorageClusterName
  
  // Fetch assignment status only if not already known
  const { data: assignmentData, isLoading } = useGetMachineAssignmentStatus(
    machine.machineName,
    machine.teamName,
    !hasClusterAssignment // Only fetch if we don't already know it's assigned to a cluster
  )
  
  // Determine assignment status
  const assignmentType = hasClusterAssignment ? 'CLUSTER' : (assignmentData?.assignmentType || 'AVAILABLE')
  const assignmentDetails = hasClusterAssignment 
    ? `Assigned to cluster: ${machine.distributedStorageClusterName}`
    : assignmentData?.assignmentDetails
  
  if (isLoading) {
    return (
      <div 
        style={{ 
          ...styles.flexCenter,
          ...styles.padding.lg
        }} 
        data-testid="ds-section-loading"
      >
        <Spin />
      </div>
    )
  }
  
  return (
    <>
      <Divider 
        style={styles.marginBottom.lg} 
        data-testid="ds-section-divider"
      >
        <Space style={styles.flexCenter}>
          <CloudServerOutlined style={styles.icon.medium} />
          <span style={styles.heading5}>{t('machineSection.title')}</span>
        </Space>
      </Divider>
      
      <Card 
        size="small" 
        data-testid="ds-section-card"
        style={{
          ...styles.card,
          border: '1px solid var(--color-border-secondary)'
        }}
      >
        <Space 
          direction="vertical" 
          style={{ width: '100%' }} 
          size="middle"
        >
          {/* Current Assignment Status */}
          <div>
            <Text 
              type="secondary" 
              style={{ 
                display: 'block',
                ...styles.marginBottom.xs,
                ...styles.label
              }} 
              data-testid="ds-section-assignment-label"
            >
              {t('assignment.currentAssignment')}
            </Text>
            <MachineAssignmentStatusBadge 
              assignmentType={assignmentType}
              assignmentDetails={assignmentDetails}
              size="default"
              data-testid="ds-section-assignment-badge"
            />
          </div>
          
          {/* Assignment Details */}
          {assignmentType !== 'AVAILABLE' && assignmentDetails && (
            <Alert
              message={<span style={styles.body}>{assignmentDetails}</span>}
              type="info"
              icon={
                assignmentType === 'CLUSTER' ? <DatabaseOutlined style={styles.icon.small} /> :
                assignmentType === 'IMAGE' ? <HddOutlined style={styles.icon.small} /> :
                assignmentType === 'CLONE' ? <CopyOutlined style={styles.icon.small} /> :
                <CloudServerOutlined style={styles.icon.small} />
              }
              showIcon
              style={{
                borderRadius: 'var(--border-radius-lg)'
              }}
              data-testid="ds-section-assignment-alert"
            />
          )}
          
          {/* Action Buttons */}
          <Space>
            {onViewDetails && (
              <Button 
                size="small" 
                icon={<HistoryOutlined style={styles.icon.small} />}
                onClick={onViewDetails}
                style={{
                  ...styles.buttonSecondary,
                  ...styles.touchTargetSmall
                }}
                data-testid="ds-section-history-button"
              >
                <span style={styles.caption}>{t('assignment.history')}</span>
              </Button>
            )}
            {onManageAssignment && assignmentType !== 'AVAILABLE' && (
              <Button 
                size="small" 
                type="primary"
                icon={<RightOutlined style={styles.icon.small} />}
                onClick={onManageAssignment}
                style={{
                  ...styles.buttonPrimary,
                  ...styles.touchTargetSmall
                }}
                data-testid="ds-section-manage-button"
              >
                <span style={styles.caption}>{t('machineSection.manageAssignment')}</span>
              </Button>
            )}
          </Space>
          
          {/* Exclusivity Warning if assigned */}
          {assignmentType !== 'AVAILABLE' && (
            <Alert
              message={<span style={styles.body}>{t('warnings.exclusivity')}</span>}
              type="warning"
              showIcon
              style={{ 
                ...styles.marginBottom.xs,
                borderRadius: 'var(--border-radius-lg)'
              }}
              data-testid="ds-section-exclusivity-warning"
            />
          )}
        </Space>
      </Card>
    </>
  )
}