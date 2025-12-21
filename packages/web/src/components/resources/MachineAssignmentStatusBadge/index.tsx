import React from 'react';
import {
  CheckCircleOutlined,
  CloudServerOutlined,
  CopyOutlined,
  FileImageOutlined,
} from '@ant-design/icons';
import { Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import type { MachineAssignmentType } from '@/types';

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
    {
      color: 'success' | 'processing' | 'warning' | 'default';
      icon: React.ReactNode;
      textKey: string;
    }
  > = {
    AVAILABLE: {
      color: 'success',
      icon: <CheckCircleOutlined />,
      textKey: 'assignmentStatus.available',
    },
    CLUSTER: {
      color: 'processing',
      icon: <CloudServerOutlined />,
      textKey: 'assignmentStatus.cluster',
    },
    IMAGE: {
      color: 'processing',
      icon: <FileImageOutlined />,
      textKey: 'assignmentStatus.image',
    },
    CLONE: {
      color: 'warning',
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
      color: 'default' as const,
      icon: null,
      text: 'Unknown',
    };
  };

  const config = getStatusConfig();

  if (size === 'small') {
    const content = (
      <Tag
        color={config.color}
        style={{ fontSize: 12, textTransform: 'none' }}
        icon={showIcon ? config.icon : undefined}
        data-testid={`machine-status-badge-tag-${assignmentType.toLowerCase()}`}
      >
        {config.text}
      </Tag>
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
    <Tooltip
      title={
        assignmentDetails ? <span style={{ fontSize: 12 }}>{assignmentDetails}</span> : undefined
      }
    >
      <span data-testid="machine-status-badge-tooltip-wrapper">
        <Tag
          color={config.color}
          icon={showIcon ? config.icon : undefined}
          style={{ textTransform: 'none' }}
          data-testid={`machine-status-badge-${assignmentType.toLowerCase()}`}
        >
          {config.text}
        </Tag>
      </span>
    </Tooltip>
  );
};

export default MachineAssignmentStatusBadge;
