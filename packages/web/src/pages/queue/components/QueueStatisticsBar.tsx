import React from 'react';
import { Divider, Flex, Typography } from 'antd';
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
        <Typography.Text className="inline-flex">
          <ThunderboltOutlined />
        </Typography.Text>
        <Typography.Text>{t('queue:statistics.total')}:</Typography.Text>
        <Typography.Text>{totalCount}</Typography.Text>
      </Flex>
      <Divider type="vertical" />
      <Flex align="center" gap={4}>
        <Typography.Text className="inline-flex">
          <PlayCircleOutlined />
        </Typography.Text>
        <Typography.Text>{t('queue:statistics.active')}:</Typography.Text>
        <Typography.Text>{activeCount}</Typography.Text>
      </Flex>
      <Divider type="vertical" />
      <Flex align="center" gap={4}>
        <Typography.Text className="inline-flex">
          <ExclamationCircleOutlined />
        </Typography.Text>
        <Typography.Text>{t('queue:statistics.failed')}:</Typography.Text>
        <Typography.Text>{failedCount}</Typography.Text>
      </Flex>
      <Divider type="vertical" />
      <Flex align="center" gap={4}>
        <Typography.Text className="inline-flex">
          <WarningOutlined />
        </Typography.Text>
        <Typography.Text>{t('queue:statistics.stale')}:</Typography.Text>
        <Typography.Text>{staleCount}</Typography.Text>
      </Flex>
    </Flex>
  );
};
