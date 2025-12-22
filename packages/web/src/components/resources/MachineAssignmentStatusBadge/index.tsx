import React from 'react';
import {
  CheckCircleOutlined,
  CloudServerOutlined,
  CopyOutlined,
  FileImageOutlined,
} from '@ant-design/icons';
import { Tag, Tooltip, Typography } from 'antd';
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
      icon: React.ReactNode;
      textKey: string;
    }
  > = {
    AVAILABLE: {
      icon: <CheckCircleOutlined />,
      textKey: 'assignmentStatus.available',
    },
    CLUSTER: {
      icon: <CloudServerOutlined />,
      textKey: 'assignmentStatus.cluster',
    },
    IMAGE: {
      icon: <FileImageOutlined />,
      textKey: 'assignmentStatus.image',
    },
    CLONE: {
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
      icon: null,
      text: 'Unknown',
    };
  };

  const config = getStatusConfig();

  if (size === 'small') {
    const content = (
      <Tag
        // eslint-disable-next-line no-restricted-syntax
        style={{ fontSize: 12, textTransform: 'none' }}
        icon={showIcon ? config.icon : undefined}
        data-testid={`machine-status-badge-tag-${assignmentType.toLowerCase()}`}
      >
        {config.text}
      </Tag>
    );

    return assignmentDetails ? (
      <Tooltip title={assignmentDetails}>
        <Typography.Text data-testid="machine-status-badge-tooltip-wrapper">
          {content}
        </Typography.Text>
      </Tooltip>
    ) : (
      content
    );
  }

  return (
    <Tooltip
      title={
        assignmentDetails ? (
          <Typography.Text
            // eslint-disable-next-line no-restricted-syntax
            style={{ fontSize: 12 }}
          >
            {assignmentDetails}
          </Typography.Text>
        ) : undefined
      }
    >
      <Typography.Text data-testid="machine-status-badge-tooltip-wrapper">
        <Tag
          icon={showIcon ? config.icon : undefined}
          // eslint-disable-next-line no-restricted-syntax
          style={{ textTransform: 'none' }}
          data-testid={`machine-status-badge-${assignmentType.toLowerCase()}`}
        >
          {config.text}
        </Tag>
      </Typography.Text>
    </Tooltip>
  );
};

export default MachineAssignmentStatusBadge;
