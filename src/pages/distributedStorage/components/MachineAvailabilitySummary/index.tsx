import React from 'react'
import { Row, Col } from 'antd'
import {
  DesktopOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  HddOutlined,
  CopyOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useTheme as useStyledTheme } from 'styled-components'
import { useMachines } from '@/api/queries/machines'
import {
  MachineAvailabilitySummaryProps,
  MachineStats,
} from './types'
import {
  SummaryCard,
  LoadingCard,
  LoadingContent,
  RefreshButton,
  RefreshIcon,
  StatCard,
  SummaryStatistic,
  PercentageSuffix,
} from './styles'
import LoadingWrapper from '@/components/common/LoadingWrapper'

export const MachineAvailabilitySummary: React.FC<MachineAvailabilitySummaryProps> = ({
  teamFilter,
  onRefresh,
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines'])
  const styledTheme = useStyledTheme()
  const { data: machines = [], isLoading, refetch } = useMachines(teamFilter)

  const stats = React.useMemo<MachineStats>(() => {
    const result: MachineStats = {
      total: machines.length,
      available: 0,
      cluster: 0,
      image: 0,
      clone: 0,
    }

    machines.forEach((machine) => {
      if (machine.distributedStorageClusterName) {
        result.cluster += 1
      } else {
        result.available += 1
      }
    })

    return result
  }, [machines])

  const handleRefresh = () => {
    refetch()
    onRefresh?.()
  }

  const getPercentage = (value: number) =>
    stats.total > 0 ? Math.round((value / stats.total) * 100) : 0

  if (isLoading) {
    return (
      <LoadingCard>
        <LoadingWrapper loading centered minHeight={160}>
          <LoadingContent />
        </LoadingWrapper>
      </LoadingCard>
    )
  }

  const statCards = [
    {
      key: 'total',
      label: t('machines.summary.total'),
      value: stats.total,
      icon: <DesktopOutlined />,
      accent: styledTheme.colors.primary,
      testId: 'ds-machines-summary-total',
      col: { xs: 24, sm: 12, md: 8, lg: 4 },
      suffix: null,
    },
    {
      key: 'available',
      label: t('machines.summary.available'),
      value: stats.available,
      icon: <CheckCircleOutlined />,
      accent: styledTheme.colors.success,
      testId: 'ds-machines-summary-available',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: (
        <PercentageSuffix>
          ({getPercentage(stats.available)}%)
        </PercentageSuffix>
      ),
    },
    {
      key: 'clusters',
      label: t('machines.summary.assignedToClusters'),
      value: stats.cluster,
      icon: <CloudServerOutlined />,
      accent: styledTheme.colors.info,
      testId: 'ds-machines-summary-clusters',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: (
        <PercentageSuffix>
          ({getPercentage(stats.cluster)}%)
        </PercentageSuffix>
      ),
    },
    {
      key: 'images',
      label: t('machines.summary.assignedToImages'),
      value: stats.image,
      icon: <HddOutlined />,
      accent: styledTheme.colors.warning,
      testId: 'ds-machines-summary-images',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: (
        <PercentageSuffix>
          ({getPercentage(stats.image)}%)
        </PercentageSuffix>
      ),
    },
    {
      key: 'clones',
      label: t('machines.summary.assignedToClones'),
      value: stats.clone,
      icon: <CopyOutlined />,
      accent: styledTheme.colors.accent,
      testId: 'ds-machines-summary-clones',
      col: { xs: 24, sm: 12, md: 8, lg: 5 },
      suffix: (
        <PercentageSuffix>
          ({getPercentage(stats.clone)}%)
        </PercentageSuffix>
      ),
    },
  ]

  return (
    <SummaryCard
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
            <StatCard size="small" data-testid={item.testId}>
              <SummaryStatistic
                title={item.label}
                value={item.value}
                prefix={item.icon}
                suffix={item.suffix}
                $accent={item.accent}
              />
            </StatCard>
          </Col>
        ))}
      </Row>
    </SummaryCard>
  )
}

export default MachineAvailabilitySummary
