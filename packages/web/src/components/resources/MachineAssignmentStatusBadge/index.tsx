import React from 'react';
import { Tooltip } from 'antd';
import {
  CloudServerOutlined,
  FileImageOutlined,
  CopyOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { MachineAssignmentType } from '@/types';
import type { StatusVariant } from '@/styles/primitives';
import { AssignmentBadge, AssignmentTag, TooltipText } from './styles';
import { IconWrapper } from '@/components/ui';

interface MachineAssignmentStatusBadgeProps {
  assignmentType: MachineAssignmentType;
  assignmentDetails?: string;
  showIcon?: boolean;
  size?: 'small' | 'default';
}

const MachineAssignmentStatusBadge: React.FC<MachineAssignmentStatusBadgeProps> = ({
  assignmentType,
  assignmentDetails,
  showIcon = true,
  size = 'default',
}) => {
  const { t } = useTranslation('machines');

  const getStatusConfig = () => {
    switch (assignmentType) {
      case 'AVAILABLE':
        return {
          variant: 'success' as StatusVariant,
          icon: <CheckCircleOutlined />,
          text: t('assignmentStatus.available'),
        };
      case 'CLUSTER':
        return {
          variant: 'processing' as StatusVariant,
          icon: <CloudServerOutlined />,
          text: t('assignmentStatus.cluster'),
        };
      case 'IMAGE':
        return {
          variant: 'info' as StatusVariant,
          icon: <FileImageOutlined />,
          text: t('assignmentStatus.image'),
        };
      case 'CLONE':
        return {
          variant: 'warning' as StatusVariant,
          icon: <CopyOutlined />,
          text: t('assignmentStatus.clone'),
        };
      default:
        return {
          variant: 'neutral' as StatusVariant,
          icon: null,
          text: 'Unknown',
        };
    }
  };

  const config = getStatusConfig();

  if (size === 'small') {
    const content = (
      <AssignmentTag
        $variant={config.variant}
        icon={
          showIcon ? (
            <IconWrapper $size="sm" $tone="inherit">
              {config.icon}
            </IconWrapper>
          ) : undefined
        }
        data-testid={`machine-status-badge-tag-${assignmentType.toLowerCase()}`}
      >
        {config.text}
      </AssignmentTag>
    );

    return assignmentDetails ? (
      <Tooltip title={assignmentDetails}>
        <span data-testid="machine-status-badge-tooltip-wrapper">{content}</span>
      </Tooltip>
    ) : (
      content
    );
  }

  return (
    <Tooltip title={assignmentDetails ? <TooltipText>{assignmentDetails}</TooltipText> : undefined}>
      <span data-testid="machine-status-badge-tooltip-wrapper">
        <AssignmentBadge
          $variant={config.variant}
          data-testid={`machine-status-badge-${assignmentType.toLowerCase()}`}
        >
          {showIcon && (
            <IconWrapper $size="sm" $tone="inherit">
              {config.icon}
            </IconWrapper>
          )}
          {config.text}
        </AssignmentBadge>
      </span>
    </Tooltip>
  );
};

export default MachineAssignmentStatusBadge;
