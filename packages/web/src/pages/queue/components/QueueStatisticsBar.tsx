import React from 'react';
import { useTranslation } from 'react-i18next';
import { RediaccStack, RediaccText } from '@/components/ui';
import { StatDivider, StatIcon, StatValue } from '@/styles/primitives';
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
    <RediaccStack variant="wrap-grid" align="center" gap="sm">
      <RediaccStack variant="tight-row" align="center" gap="xs">
        <StatIcon>
          <ThunderboltOutlined />
        </StatIcon>
        <RediaccText variant="caption" color="secondary">
          {t('queue:statistics.total')}:
        </RediaccText>
        <StatValue>{totalCount}</StatValue>
      </RediaccStack>
      <StatDivider />
      <RediaccStack variant="tight-row" align="center" gap="xs">
        <StatIcon $color="var(--color-info)">
          <PlayCircleOutlined />
        </StatIcon>
        <RediaccText variant="caption" color="secondary">
          {t('queue:statistics.active')}:
        </RediaccText>
        <StatValue $color="var(--color-info)">{activeCount}</StatValue>
      </RediaccStack>
      <StatDivider />
      <RediaccStack variant="tight-row" align="center" gap="xs">
        <StatIcon $color="var(--color-error)">
          <ExclamationCircleOutlined />
        </StatIcon>
        <RediaccText variant="caption" color="secondary">
          {t('queue:statistics.failed')}:
        </RediaccText>
        <StatValue $color="var(--color-error)">{failedCount}</StatValue>
      </RediaccStack>
      <StatDivider />
      <RediaccStack variant="tight-row" align="center" gap="xs">
        <StatIcon $color="var(--color-warning)">
          <WarningOutlined />
        </StatIcon>
        <RediaccText variant="caption" color="secondary">
          {t('queue:statistics.stale')}:
        </RediaccText>
        <StatValue $color="var(--color-warning)">{staleCount}</StatValue>
      </RediaccStack>
    </RediaccStack>
  );
};
