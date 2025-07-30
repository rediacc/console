import React from 'react'
import { Badge, Tag, Tooltip } from 'antd'
import { 
  CloudServerOutlined, 
  FileImageOutlined, 
  CopyOutlined,
  CheckCircleOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import type { MachineAssignmentType } from '@/types'

interface MachineAssignmentStatusBadgeProps {
  assignmentType: MachineAssignmentType
  assignmentDetails?: string
  showIcon?: boolean
  size?: 'small' | 'default'
}

const MachineAssignmentStatusBadge: React.FC<MachineAssignmentStatusBadgeProps> = ({
  assignmentType,
  assignmentDetails,
  showIcon = true,
  size = 'default'
}) => {
  const { t } = useTranslation('machines')

  const getStatusConfig = () => {
    switch (assignmentType) {
      case 'AVAILABLE':
        return {
          color: 'green',
          icon: <CheckCircleOutlined />,
          text: t('assignmentStatus.available'),
          badgeStatus: 'success' as const
        }
      case 'CLUSTER':
        return {
          color: 'blue',
          icon: <CloudServerOutlined />,
          text: t('assignmentStatus.cluster'),
          badgeStatus: 'processing' as const
        }
      case 'IMAGE':
        return {
          color: 'purple',
          icon: <FileImageOutlined />,
          text: t('assignmentStatus.image'),
          badgeStatus: 'processing' as const
        }
      case 'CLONE':
        return {
          color: 'orange',
          icon: <CopyOutlined />,
          text: t('assignmentStatus.clone'),
          badgeStatus: 'processing' as const
        }
      default:
        return {
          color: 'default',
          icon: null,
          text: 'Unknown',
          badgeStatus: 'default' as const
        }
    }
  }

  const config = getStatusConfig()

  if (size === 'small') {
    const content = (
      <Tag 
        color={config.color} 
        icon={showIcon ? config.icon : undefined}
        style={{ margin: 0 }}
        data-testid={`machine-status-badge-tag-${assignmentType.toLowerCase()}`}
      >
        {config.text}
      </Tag>
    )

    return assignmentDetails ? (
      <Tooltip title={assignmentDetails}>
        <span data-testid="machine-status-badge-tooltip-wrapper">
          {content}
        </span>
      </Tooltip>
    ) : content
  }

  return (
    <Tooltip title={assignmentDetails}>
      <span data-testid="machine-status-badge-tooltip-wrapper">
        <Badge 
          status={config.badgeStatus} 
          text={
            <span 
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
              data-testid={`machine-status-badge-${assignmentType.toLowerCase()}`}
            >
              {showIcon && config.icon}
              {config.text}
            </span>
          }
        />
      </span>
    </Tooltip>
  )
}

export default MachineAssignmentStatusBadge