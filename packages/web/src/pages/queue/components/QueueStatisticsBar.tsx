import { Flex, Typography } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  ThunderboltOutlined,
  PlayCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';

interface QueueStatisticsBarProps {
  totalCount: number;
  activeCount: number;
  failedCount: number;
  staleCount: number;
}

export const QueueStatisticsBar: React.FC<QueueStatisticsBarProps> = ({
  totalCount,
  activeCount,
  failedCount,
  staleCount,
}) => {
  const { t } = useTranslation(['queue']);

  return (
    <Flex wrap="wrap" align="center" gap={8}>
      <Flex align="center" gap={4}>
        <span style={{ display: 'inline-flex' }}>
          <ThunderboltOutlined />
        </span>
        <Typography.Text type="secondary">
          {t('queue:statistics.total')}:
        </Typography.Text>
        <Typography.Text>{totalCount}</Typography.Text>
      </Flex>
      <span style={{ width: 1, height: 16, background: 'var(--ant-color-border-secondary)' }} />
      <Flex align="center" gap={4}>
        <span style={{ display: 'inline-flex', color: 'var(--ant-color-info)' }}>
          <PlayCircleOutlined />
        </span>
        <Typography.Text type="secondary">
          {t('queue:statistics.active')}:
        </Typography.Text>
        <Typography.Text style={{ color: 'var(--ant-color-info)' }}>
          {activeCount}
        </Typography.Text>
      </Flex>
      <span style={{ width: 1, height: 16, background: 'var(--ant-color-border-secondary)' }} />
      <Flex align="center" gap={4}>
        <span style={{ display: 'inline-flex', color: 'var(--ant-color-error)' }}>
          <ExclamationCircleOutlined />
        </span>
        <Typography.Text type="secondary">
          {t('queue:statistics.failed')}:
        </Typography.Text>
        <Typography.Text style={{ color: 'var(--ant-color-error)' }}>
          {failedCount}
        </Typography.Text>
      </Flex>
      <span style={{ width: 1, height: 16, background: 'var(--ant-color-border-secondary)' }} />
      <Flex align="center" gap={4}>
        <span style={{ display: 'inline-flex', color: 'var(--ant-color-warning)' }}>
          <WarningOutlined />
        </span>
        <Typography.Text type="secondary">
          {t('queue:statistics.stale')}:
        </Typography.Text>
        <Typography.Text style={{ color: 'var(--ant-color-warning)' }}>
          {staleCount}
        </Typography.Text>
      </Flex>
    </Flex>
  );
};
