import React from 'react';
import {
  CheckCircleOutlined,
  CloudServerOutlined,
  CopyOutlined,
  FileImageOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { IconWrapper, RediaccTooltip } from '@/components/ui';
import type { TagVariant } from '@/components/ui/Tag';
import type { MachineAssignmentType } from '@/types';
import { AssignmentBadge, AssignmentTag, TooltipText } from './styles';

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

  const STATUS_CONFIG_MAP: Record<
    MachineAssignmentType,
    { variant: TagVariant; icon: React.ReactNode; textKey: string }
  > = {
    AVAILABLE: {
      variant: 'success',
      icon: <CheckCircleOutlined />,
      textKey: 'assignmentStatus.available',
    },
    CLUSTER: {
      variant: 'primary',
      icon: <CloudServerOutlined />,
      textKey: 'assignmentStatus.cluster',
    },
    IMAGE: {
      variant: 'info',
      icon: <FileImageOutlined />,
      textKey: 'assignmentStatus.image',
    },
    CLONE: {
      variant: 'warning',
      icon: <CopyOutlined />,
      textKey: 'assignmentStatus.clone',
    },
  };

  const getStatusConfig = () => {
    const config = STATUS_CONFIG_MAP[assignmentType];
    if (config) {
      return {
        ...config,
        text: t(config.textKey),
      };
    }
    return {
      variant: 'neutral' as TagVariant,
      icon: null,
      text: 'Unknown',
    };
  };

  const config = getStatusConfig();

  if (size === 'small') {
    const content = (
      <AssignmentTag
        variant={config.variant}
        size="sm"
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
      <RediaccTooltip title={assignmentDetails}>
        <span data-testid="machine-status-badge-tooltip-wrapper">{content}</span>
      </RediaccTooltip>
    ) : (
      content
    );
  }

  return (
    <RediaccTooltip title={assignmentDetails ? <TooltipText>{assignmentDetails}</TooltipText> : undefined}>
      <span data-testid="machine-status-badge-tooltip-wrapper">
        <AssignmentBadge
          variant={config.variant}
          icon={
            showIcon ? (
              <IconWrapper $size="sm" $tone="inherit">
                {config.icon}
              </IconWrapper>
            ) : undefined
          }
          data-testid={`machine-status-badge-${assignmentType.toLowerCase()}`}
        >
          {config.text}
        </AssignmentBadge>
      </span>
    </RediaccTooltip>
  );
};

export default MachineAssignmentStatusBadge;
