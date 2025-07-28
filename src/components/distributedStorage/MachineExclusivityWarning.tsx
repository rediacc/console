import React from 'react'
import { Alert, Typography } from 'antd'
import { InfoCircleOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'

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
      message={getWarningMessage()}
      description={
        <div>
          <Text>{getDescription()}</Text>
          <br />
          <br />
          <Text strong>{t('distributedStorage:warnings.exclusivityNote')}</Text>
          <ul style={{ marginTop: 8, marginBottom: 0 }}>
            <li>{t('distributedStorage:warnings.oneClusterPerMachine')}</li>
            <li>{t('distributedStorage:warnings.oneImagePerMachine')}</li>
            <li>{t('distributedStorage:warnings.multipleClonesPossible')}</li>
          </ul>
        </div>
      }
      type="warning"
      showIcon
      icon={<InfoCircleOutlined />}
      style={style}
    />
  )
}

// Simplified inline warning component
export const MachineExclusivityInlineWarning: React.FC<{
  message?: string
  style?: React.CSSProperties
}> = ({ message, style }) => {
  const { t } = useTranslation('distributedStorage')
  
  return (
    <Alert
      message={message || t('warnings.machineExclusivity')}
      type="warning"
      showIcon
      banner
      style={{ marginBottom: 16, ...style }}
    />
  )
}