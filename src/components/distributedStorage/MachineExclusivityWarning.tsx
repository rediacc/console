import React from 'react'
import { Alert, Typography } from 'antd'
import { InfoCircleOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useComponentStyles } from '@/hooks/useComponentStyles'

const { Text } = Typography

interface MachineExclusivityWarningProps {
  type?: 'cluster' | 'image' | 'clone' | 'general'
  machineName?: string
  currentAssignment?: {
    type: string
    name: string
  }
  style?: React.CSSProperties
}

export const MachineExclusivityWarning: React.FC<MachineExclusivityWarningProps> = ({
  type = 'general',
  machineName,
  currentAssignment,
  style
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines'])
  const styles = useComponentStyles()
  
  const getWarningMessage = () => {
    if (currentAssignment && machineName) {
      return t('machines:validation.alreadyAssigned', {
        resourceType: t(`distributedStorage:${currentAssignment.type}s.${currentAssignment.type}`),
        resourceName: currentAssignment.name
      })
    }
    
    switch (type) {
      case 'cluster':
        return t('distributedStorage:warnings.machineClusterExclusivity')
      case 'image':
        return t('distributedStorage:warnings.machineImageExclusivity')
      case 'clone':
        return t('distributedStorage:warnings.machineCloneExclusivity')
      default:
        return t('distributedStorage:warnings.machineExclusivity')
    }
  }
  
  const getDescription = () => {
    switch (type) {
      case 'cluster':
        return t('distributedStorage:warnings.clusterExclusivityDescription')
      case 'image':
        return t('distributedStorage:warnings.imageExclusivityDescription')
      case 'clone':
        return t('distributedStorage:warnings.cloneExclusivityDescription')
      default:
        return t('distributedStorage:warnings.exclusivityDescription')
    }
  }
  
  return (
    <Alert
      message={
        <span style={styles.body}>{getWarningMessage()}</span>
      }
      description={
        <div data-testid="exclusivity-warning-description" style={styles.spacer}>
          <Text 
            data-testid="exclusivity-warning-description-text"
            style={styles.body}
          >
            {getDescription()}
          </Text>
          <br />
          <br />
          <Text 
            strong 
            data-testid="exclusivity-warning-note"
            style={styles.label}
          >
            {t('distributedStorage:warnings.exclusivityNote')}
          </Text>
          <ul 
            style={{ 
              ...styles.marginBottom.sm,
              marginTop: '8px',
              paddingLeft: '20px'
            }} 
            data-testid="exclusivity-warning-list"
          >
            <li data-testid="exclusivity-warning-cluster-rule">
              <span style={styles.body}>{t('distributedStorage:warnings.oneClusterPerMachine')}</span>
            </li>
            <li data-testid="exclusivity-warning-image-rule">
              <span style={styles.body}>{t('distributedStorage:warnings.oneImagePerMachine')}</span>
            </li>
            <li data-testid="exclusivity-warning-clone-rule">
              <span style={styles.body}>{t('distributedStorage:warnings.multipleClonesPossible')}</span>
            </li>
          </ul>
        </div>
      }
      type="warning"
      showIcon
      icon={<InfoCircleOutlined style={styles.icon.medium} />}
      style={{
        borderRadius: 'var(--border-radius-lg)',
        ...style
      }}
      data-testid={`exclusivity-warning-${type}`}
    />
  )
}

// Simplified inline warning component
export const MachineExclusivityInlineWarning: React.FC<{
  message?: string
  style?: React.CSSProperties
}> = ({ message, style }) => {
  const { t } = useTranslation('distributedStorage')
  const styles = useComponentStyles()
  
  return (
    <Alert
      message={
        <span style={styles.body}>
          {message || t('warnings.machineExclusivity')}
        </span>
      }
      type="warning"
      showIcon
      banner
      style={{ 
        ...styles.marginBottom.md,
        borderRadius: 'var(--border-radius-md)',
        ...style 
      }}
      data-testid="exclusivity-warning-inline"
    />
  )
}