import React from 'react';
import { Button, Flex, Space, Tooltip, Typography } from 'antd';
import { CloudServerOutlined, InfoCircleOutlined } from '@/utils/optimizedIcons';
import type { TFunction } from 'i18next';

interface BulkActionsToolbarProps {
  selectedRowKeys: string[];
  setSelectedRowKeys: (keys: string[]) => void;
  canAssignToCluster: boolean;
  onAssignToCluster: () => void;
  onRemoveFromCluster: () => void;
  onViewAssignmentStatus: () => void;
  t: TFunction;
}

export const BulkActionsToolbar: React.FC<BulkActionsToolbarProps> = ({
  selectedRowKeys,
  setSelectedRowKeys,
  canAssignToCluster,
  onAssignToCluster,
  onRemoveFromCluster,
  onViewAssignmentStatus,
  t,
}) => {
  if (!canAssignToCluster || selectedRowKeys.length === 0) return null;

  return (
    <Flex align="center" justify="space-between" wrap>
      <Space size="middle">
        <Typography.Text>
          {t('machines:bulkActions.selected', { count: selectedRowKeys.length })}
        </Typography.Text>
        <Tooltip title={t('common:actions.clearSelection')}>
          <Button
            onClick={() => setSelectedRowKeys([])}
            data-testid="machine-bulk-clear-selection"
            aria-label={t('common:actions.clearSelection')}
          >
            Clear
          </Button>
        </Tooltip>
      </Space>
      <Space size="middle">
        <Tooltip title={t('machines:bulkActions.assignToCluster')}>
          <Button
            type="primary"
            icon={<CloudServerOutlined />}
            onClick={onAssignToCluster}
            data-testid="machine-bulk-assign-cluster"
            aria-label={t('machines:bulkActions.assignToCluster')}
          />
        </Tooltip>
        <Tooltip title={t('machines:bulkActions.removeFromCluster')}>
          <Button
            icon={<CloudServerOutlined />}
            onClick={onRemoveFromCluster}
            data-testid="machine-bulk-remove-cluster"
            aria-label={t('machines:bulkActions.removeFromCluster')}
          />
        </Tooltip>
        <Tooltip title={t('machines:bulkActions.viewAssignmentStatus')}>
          <Button
            icon={<InfoCircleOutlined />}
            onClick={onViewAssignmentStatus}
            data-testid="machine-bulk-view-status"
            aria-label={t('machines:bulkActions.viewAssignmentStatus')}
          />
        </Tooltip>
      </Space>
    </Flex>
  );
};
