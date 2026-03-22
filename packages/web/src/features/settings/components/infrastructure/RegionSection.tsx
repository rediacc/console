import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetOrganizationRegions_ResultSet1 } from '@rediacc/shared/types';
import { Col, Flex, Row } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React from 'react';
import { TooltipButton } from '@/components/common/buttons';
import { PageHeader } from '@/components/common/PageHeader';
import ResourceListView from '@/components/common/ResourceListView';
import { PlusOutlined } from '@/utils/optimizedIcons';

interface RegionSectionProps {
  t: TypedTFunction;
  regionsLoading: boolean;
  regionsList: GetOrganizationRegions_ResultSet1[];
  columns: ColumnsType<GetOrganizationRegions_ResultSet1>;
  mobileRender: (record: GetOrganizationRegions_ResultSet1) => React.ReactNode;
  effectiveRegion: string | null;
  onSelectRegion: (regionName: string | null) => void;
  onCreateRegion: () => void;
}

export const RegionSection: React.FC<RegionSectionProps> = ({
  t,
  regionsLoading,
  regionsList,
  columns,
  mobileRender,
  effectiveRegion,
  onSelectRegion,
  onCreateRegion,
}) => (
  <Row gutter={[24, 24]}>
    <Col span={24}>
      <Flex vertical>
        <ResourceListView
          title={
            <PageHeader title={t('regions.title')} subtitle={t('regions.selectRegionPrompt')} />
          }
          loading={regionsLoading}
          data={regionsList}
          columns={columns}
          mobileRender={mobileRender}
          rowKey="regionName"
          searchPlaceholder={t('regions.searchRegions')}
          data-testid="system-region-table"
          actions={
            <TooltipButton
              tooltip={t('regions.createRegion')}
              type="primary"
              icon={<PlusOutlined />}
              onClick={onCreateRegion}
              data-testid="system-create-region-button"
            />
          }
          rowSelection={{
            type: 'radio',
            selectedRowKeys: effectiveRegion ? [effectiveRegion] : [],
            onChange: (selectedRowKeys) => {
              const [first] = selectedRowKeys;
              onSelectRegion(typeof first === 'string' ? first : null);
            },
          }}
          onRow={(record: GetOrganizationRegions_ResultSet1) => ({
            onClick: () => onSelectRegion(record.regionName),
            className: [
              'clickable-row',
              effectiveRegion === record.regionName ? 'selected-row' : '',
            ]
              .filter(Boolean)
              .join(' '),
          })}
        />
      </Flex>
    </Col>
  </Row>
);
