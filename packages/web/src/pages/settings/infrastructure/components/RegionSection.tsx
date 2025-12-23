import React from 'react';
import { Button, Col, Flex, Row, Space, Tooltip, Typography } from 'antd';
import type { Region } from '@/api/queries/regions';
import ResourceListView from '@/components/common/ResourceListView';
import { PlusOutlined } from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

interface RegionSectionProps {
  t: TFunction<'resources'>;
  regionsLoading: boolean;
  regionsList: Region[];
  columns: ColumnsType<Region>;
  mobileRender: (record: Region) => React.ReactNode;
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
            <Space direction="vertical" size={0}>
              <Typography.Text strong>{t('regions.title')}</Typography.Text>
              <Typography.Text>{t('regions.selectRegionPrompt')}</Typography.Text>
            </Space>
          }
          loading={regionsLoading}
          data={regionsList}
          columns={columns}
          mobileRender={mobileRender}
          rowKey="regionName"
          searchPlaceholder={t('regions.searchRegions')}
          data-testid="system-region-table"
          actions={
            <Tooltip title={t('regions.createRegion')}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={onCreateRegion}
                data-testid="system-create-region-button"
                aria-label={t('regions.createRegion')}
              />
            </Tooltip>
          }
          rowSelection={{
            type: 'radio',
            selectedRowKeys: effectiveRegion ? [effectiveRegion] : [],
            onChange: (selectedRowKeys) => {
              const [first] = selectedRowKeys;
              onSelectRegion(typeof first === 'string' ? first : null);
            },
          }}
          onRow={(record: Region) => ({
            onClick: () => onSelectRegion(record.regionName),
            className: ['clickable-row', effectiveRegion === record.regionName ? 'selected-row' : '']
              .filter(Boolean)
              .join(' '),
          })}
        />
      </Flex>
    </Col>
  </Row>
);
