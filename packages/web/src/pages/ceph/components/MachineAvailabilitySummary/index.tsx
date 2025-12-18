import React from 'react';
import { Col, Row } from 'antd';
import { useTranslation } from 'react-i18next';
import { useMachines } from '@/api/queries/machines';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccStatistic } from '@/components/ui';
import {
  CheckCircleOutlined,
  CloudServerOutlined,
  CopyOutlined,
  DesktopOutlined,
  HddOutlined,
} from '@/utils/optimizedIcons';
import {
  LoadingContent,
  PercentageSuffix,
  RefreshButton,
  RefreshIcon,
  StatCard,
  StyledRediaccCard,
} from './styles';
import { MachineAvailabilitySummaryProps, MachineStats } from './types';

export const MachineAvailabilitySummary: React.FC<MachineAvailabilitySummaryProps> = ({
  teamFilter,
  onRefresh,
}) => {
  const { t } = useTranslation(['ceph', 'machines']);
  const { data: machines = [], isLoading, refetch } = useMachines(teamFilter);

  // Get accent colors from CSS variables
  const accentColors = {
    primary: 'var(--color-primary)',
    success: 'var(--color-success)',
    info: 'var(--color-info)',
    warning: 'var(--color-warning)',
    accent: 'var(--color-text-tertiary)', // Was var(--color-accent), now using text-tertiary
  };

  const stats = React.useMemo<MachineStats>(() => {
    const result: MachineStats = {
      total: machines.length,
      available: 0,
      cluster: 0,
      image: 0,
      clone: 0,
    };

    machines.forEach((machine) => {
      if (machine.cephClusterName) {
        result.cluster += 1;
      } else {
        result.available += 1;
      }
    });

    return result;
  }, [machines]);

  const handleRefresh = () => {
    refetch();
    onRefresh?.();
  };

  const getPercentage = (value: number) =>
    stats.total > 0 ? Math.round((value / stats.total) * 100) : 0;

  if (isLoading) {
    return (
      <StyledRediaccCard>
        <LoadingWrapper loading centered minHeight={160}>
          <LoadingContent />
        </LoadingWrapper>
      </StyledRediaccCard>
    );
  }

  const statCards = [
    {
      key: 'total',
      label: t('machines.summary.total'),
      value: stats.total,
      icon: <DesktopOutlined />,
      accent: accentColors.primary,
      testId: 'ds-machines-summary-total',
      col: { xs: 24, sm: 12, md: 8, lg: 4 },
      suffix: null,
    },
    {
      key: 'available',
      label: t('machines.summary.available'),
      value: stats.available,
      icon: <CheckCircleOutlined />,
      accent: accentColors.success,
      testId: 'ds-machines-summary-available',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: <PercentageSuffix>({getPercentage(stats.available)}%)</PercentageSuffix>,
    },
    {
      key: 'clusters',
      label: t('machines.summary.assignedToClusters'),
      value: stats.cluster,
      icon: <CloudServerOutlined />,
      accent: accentColors.info,
      testId: 'ds-machines-summary-clusters',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: <PercentageSuffix>({getPercentage(stats.cluster)}%)</PercentageSuffix>,
    },
    {
      key: 'images',
      label: t('machines.summary.assignedToImages'),
      value: stats.image,
      icon: <HddOutlined />,
      accent: accentColors.warning,
      testId: 'ds-machines-summary-images',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: <PercentageSuffix>({getPercentage(stats.image)}%)</PercentageSuffix>,
    },
    {
      key: 'clones',
      label: t('machines.summary.assignedToClones'),
      value: stats.clone,
      icon: <CopyOutlined />,
      accent: accentColors.accent,
      testId: 'ds-machines-summary-clones',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: <PercentageSuffix>({getPercentage(stats.clone)}%)</PercentageSuffix>,
    },
  ];

  return (
    <StyledRediaccCard
      title={t('machines.summary.title')}
      extra={
        <RefreshButton
          type="button"
          onClick={handleRefresh}
          data-testid="ds-machines-summary-refresh"
          aria-label={t('common:actions.refresh')}
        >
          <RefreshIcon spin={isLoading} />
        </RefreshButton>
      }
      data-testid="ds-machines-summary-card"
    >
      <Row gutter={16}>
        {statCards.map((item) => (
          <Col key={item.key} {...item.col}>
            <StatCard size="sm" data-testid={item.testId}>
              <RediaccStatistic
                title={item.label}
                value={item.value}
                prefix={item.icon}
                suffix={item.suffix}
                color={item.accent}
              />
            </StatCard>
          </Col>
        ))}
      </Row>
    </StyledRediaccCard>
  );
};

export default MachineAvailabilitySummary;
