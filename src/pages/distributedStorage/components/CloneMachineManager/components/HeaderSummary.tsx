import React from 'react'
import { Col } from 'antd'
import type { TFunction } from 'i18next'
import {
  HeaderRow,
  HeaderContent,
  TitleRow,
  TitleIcon,
  TitleText,
  CloneName,
  MetadataText,
  StatsRow,
  StatCard,
  StatIcon,
} from '../styles'

interface HeaderSummaryProps {
  cloneName: string
  poolName: string
  imageName: string
  snapshotName: string
  totalMachines: number
  selectedMachines: number
  t: TFunction<'distributedStorage' | 'machines' | 'common'>
}

export const HeaderSummary: React.FC<HeaderSummaryProps> = ({
  cloneName,
  poolName,
  imageName,
  snapshotName,
  totalMachines,
  selectedMachines,
  t,
}) => (
  <HeaderRow gutter={16}>
    <Col span={16}>
      <HeaderContent>
        <TitleRow>
          <TitleIcon />
          <TitleText>
            {t('distributedStorage:clones.clone')}:{' '}
            <CloneName>{cloneName}</CloneName>
          </TitleText>
        </TitleRow>
        <MetadataText>
          {t('distributedStorage:pools.pool')}: {poolName} {' | '}
          {t('distributedStorage:images.image')}: {imageName} {' | '}
          {t('distributedStorage:snapshots.snapshot')}: {snapshotName}
        </MetadataText>
      </HeaderContent>
    </Col>
    <Col span={8}>
      <StatsRow gutter={16}>
        <Col span={12}>
          <StatCard
            data-testid="clone-manager-statistic-total"
            title={t('machines:totalMachines')}
            value={totalMachines}
            prefix={<StatIcon />}
          />
        </Col>
        <Col span={12}>
          <StatCard
            data-testid="clone-manager-statistic-selected"
            title={t('machines:bulkActions.selected')}
            value={selectedMachines}
            $highlight={selectedMachines > 0}
          />
        </Col>
      </StatsRow>
    </Col>
  </HeaderRow>
)
