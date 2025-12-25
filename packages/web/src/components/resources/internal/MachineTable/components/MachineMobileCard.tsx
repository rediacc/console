import React, { useCallback } from 'react';
import { Flex, Space, Tag, Typography, type MenuProps } from 'antd';
import { useNavigate } from 'react-router-dom';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import type { Machine } from '@/types';
import {
  DeleteOutlined,
  DesktopOutlined,
  EditOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  FunctionOutlined,
  HistoryOutlined,
} from '@/utils/optimizedIcons';
import type { TFunction } from 'i18next';

interface MachineMobileCardProps {
  record: Machine;
  onEditMachine?: (machine: Machine) => void;
  onFunctionsMachine?: (machine: Machine, functionName?: string) => void;
  onDeleteMachine?: (machine: Machine) => void;
  onViewDetails: (machine: Machine) => void;
  onAuditTrace: (machine: Machine) => void;
  t: TFunction;
}

const MachineMobileCard: React.FC<MachineMobileCardProps> = ({
  record,
  onEditMachine,
  onFunctionsMachine,
  onDeleteMachine,
  onViewDetails,
  onAuditTrace,
  t,
}) => {
  const navigate = useNavigate();

  const menuItems: MenuProps['items'] = [
    {
      key: 'viewRepositories',
      label: t('resources:repositories.repositories'),
      icon: <FolderOpenOutlined />,
      onClick: () =>
        navigate(`/machines/${record.machineName}/repositories`, {
          state: { machine: record },
        }),
    },
    {
      key: 'viewDetails',
      label: t('resources:audit.details'),
      icon: <EyeOutlined />,
      onClick: () => onViewDetails(record),
    },
    { type: 'divider' as const },
    ...(onEditMachine
      ? [
          {
            key: 'edit',
            label: t('common:actions.edit'),
            icon: <EditOutlined />,
            onClick: () => onEditMachine(record),
          },
        ]
      : []),
    ...(onFunctionsMachine
      ? [
          {
            key: 'functions',
            label: t('machines:functions'),
            icon: <FunctionOutlined />,
            onClick: () => onFunctionsMachine(record),
          },
        ]
      : []),
    {
      key: 'trace',
      label: t('resources:audit.trace'),
      icon: <HistoryOutlined />,
      onClick: () => onAuditTrace(record),
    },
    ...(onDeleteMachine
      ? [
          { type: 'divider' as const },
          {
            key: 'delete',
            label: t('common:actions.delete'),
            icon: <DeleteOutlined />,
            danger: true,
            onClick: () => onDeleteMachine(record),
          },
        ]
      : []),
  ];

  return (
    <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
      <Space>
        <DesktopOutlined />
        <Typography.Text strong className="truncate">
          {record.machineName}
        </Typography.Text>
      </Space>
      <Flex gap={8} wrap>
        <Tag>{record.teamName}</Tag>
        {record.bridgeName && <Tag>{record.bridgeName}</Tag>}
        {record.regionName && <Tag>{record.regionName}</Tag>}
      </Flex>
    </MobileCard>
  );
};

interface UseMachineMobileRenderProps {
  onEditMachine?: (machine: Machine) => void;
  onFunctionsMachine?: (machine: Machine, functionName?: string) => void;
  onDeleteMachine?: (machine: Machine) => void;
  onViewDetails: (machine: Machine) => void;
  onAuditTrace: (machine: Machine) => void;
  t: TFunction;
}

export function useMachineMobileRender({
  onEditMachine,
  onFunctionsMachine,
  onDeleteMachine,
  onViewDetails,
  onAuditTrace,
  t,
}: UseMachineMobileRenderProps) {
  return useCallback(
    (record: Machine) => (
      <MachineMobileCard
        record={record}
        onEditMachine={onEditMachine}
        onFunctionsMachine={onFunctionsMachine}
        onDeleteMachine={onDeleteMachine}
        onViewDetails={onViewDetails}
        onAuditTrace={onAuditTrace}
        t={t}
      />
    ),
    [onEditMachine, onFunctionsMachine, onDeleteMachine, onViewDetails, onAuditTrace, t]
  );
}
