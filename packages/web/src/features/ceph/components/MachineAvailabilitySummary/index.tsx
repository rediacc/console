import { Button, Card, Col, Flex, Row, Statistic, Typography } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { useGetTeamMachines } from '@/api/api-hooks.generated';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import {
  CheckCircleOutlined,
  CloudServerOutlined,
  CopyOutlined,
  DesktopOutlined,
  HddOutlined,
  ReloadOutlined,
} from '@/utils/optimizedIcons';
import { MachineAvailabilitySummaryProps, MachineStats } from './types';

export const MachineAvailabilitySummary: React.FC<MachineAvailabilitySummaryProps> = ({
  teamFilter,
  onRefresh,
}) => {
  const { t } = useTranslation(['ceph', 'machines']);
  const { data: machines = [], isLoading, refetch } = useGetTeamMachines(teamFilter?.[0]);

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
    void refetch();
    onRefresh?.();
  };

  const getPercentage = (value: number) =>
    stats.total > 0 ? Math.round((value / stats.total) * 100) : 0;

  if (isLoading) {
    return (
      <Card>
        <LoadingWrapper loading centered minHeight={160}>
          <Flex justify="center" />
        </LoadingWrapper>
      </Card>
    );
  }

  const statCards = [
    {
      key: 'total',
      label: t('machines.summary.total'),
      value: stats.total,
      icon: <DesktopOutlined />,
      testId: 'ds-machines-summary-total',
      col: { xs: 24, sm: 12, md: 8, lg: 4 },
      suffix: null,
    },
    {
      key: 'available',
      label: t('machines.summary.available'),
      value: stats.available,
      icon: <CheckCircleOutlined />,
      testId: 'ds-machines-summary-available',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: <Typography.Text>({getPercentage(stats.available)}%)</Typography.Text>,
    },
    {
      key: 'clusters',
      label: t('machines.summary.assignedToClusters'),
      value: stats.cluster,
      icon: <CloudServerOutlined />,
      testId: 'ds-machines-summary-clusters',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: <Typography.Text>({getPercentage(stats.cluster)}%)</Typography.Text>,
    },
    {
      key: 'images',
      label: t('machines.summary.assignedToImages'),
      value: stats.image,
      icon: <HddOutlined />,
      testId: 'ds-machines-summary-images',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: <Typography.Text>({getPercentage(stats.image)}%)</Typography.Text>,
    },
    {
      key: 'clones',
      label: t('machines.summary.assignedToClones'),
      value: stats.clone,
      icon: <CopyOutlined />,
      testId: 'ds-machines-summary-clones',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: <Typography.Text>({getPercentage(stats.clone)}%)</Typography.Text>,
    },
  ];

  return (
    <Card
      title={t('machines.summary.title')}
      extra={
        <Button
          type="text"
          icon={<ReloadOutlined spin={isLoading} />}
          onClick={handleRefresh}
          data-testid="ds-machines-summary-refresh"
          aria-label={t('common:actions.refresh')}
        />
      }
      data-testid="ds-machines-summary-card"
    >
      <Row gutter={16}>
        {statCards.map((item) => (
          <Col key={item.key} {...item.col}>
            <Card size="small" data-testid={item.testId}>
              <Statistic
                title={item.label}
                value={item.value}
                prefix={item.icon}
                suffix={item.suffix}
              />
            </Card>
          </Col>
        ))}
      </Row>
    </Card>
  );
};
