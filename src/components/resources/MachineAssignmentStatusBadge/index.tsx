import React from 'react'
import { Badge, Tooltip } from 'antd'
import {
  CloudServerOutlined,
  FileImageOutlined,
  CopyOutlined,
  CheckCircleOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import type { MachineAssignmentType } from '@/types'
import { StyledTag, StyledBadgeWrapper } from './styles'

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
  const styles = useComponentStyles()

  const getStatusConfig = () => {
    switch (assignmentType) {
      case 'AVAILABLE':
        return {
          opacity: 1.0, // Solid - available/active state
          icon: <CheckCircleOutlined style={styles.icon.small} />,
          text: t('assignmentStatus.available'),
          badgeStatus: 'default' as const
        }
      case 'CLUSTER':
        return {
          opacity: 0.7, // Medium - processing/in-use state
          icon: <CloudServerOutlined style={styles.icon.small} />,
          text: t('assignmentStatus.cluster'),
          badgeStatus: 'default' as const
        }
      case 'IMAGE':
        return {
          opacity: 0.7, // Medium - processing/in-use state
          icon: <FileImageOutlined style={styles.icon.small} />,
          text: t('assignmentStatus.image'),
          badgeStatus: 'default' as const
        }
      case 'CLONE':
        return {
          opacity: 0.7, // Medium - processing/in-use state
          icon: <CopyOutlined style={styles.icon.small} />,
          text: t('assignmentStatus.clone'),
          badgeStatus: 'default' as const
        }
      default:
        return {
          opacity: 0.5, // Light - inactive/unknown state
          icon: null,
          text: 'Unknown',
          badgeStatus: 'default' as const
        }
    }
  }

  const config = getStatusConfig()

  if (size === 'small') {
    const content = (
      <StyledTag
        $opacity={config.opacity}
        icon={showIcon ? config.icon : undefined}
        data-testid={`machine-status-badge-tag-${assignmentType.toLowerCase()}`}
      >
        <span style={styles.caption}>{config.text}</span>
      </StyledTag>
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
    <Tooltip
      title={assignmentDetails ? (
        <span style={styles.caption}>{assignmentDetails}</span>
      ) : undefined}
    >
      <StyledBadgeWrapper
        $opacity={config.opacity}
        data-testid="machine-status-badge-tooltip-wrapper"
      >
        <Badge
          status={config.badgeStatus}
          text={
            <span
              style={{
                ...styles.flexStart,
                gap: '4px'
              }}
              data-testid={`machine-status-badge-${assignmentType.toLowerCase()}`}
            >
              {showIcon && config.icon}
              <span style={styles.caption}>{config.text}</span>
            </span>
          }
        />
      </StyledBadgeWrapper>
    </Tooltip>
  )
}

export default MachineAssignmentStatusBadge