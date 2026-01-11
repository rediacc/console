import React from 'react';
import { Col, Empty, Flex, Row, Typography } from 'antd';
import { TooltipButton } from '@/components/common/buttons';
import { PageHeader } from '@/components/common/PageHeader';
import ResourceListView from '@/components/common/ResourceListView';
import { PlusOutlined } from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetRegionBridges_ResultSet1 } from '@rediacc/shared/types';
import type { ColumnsType } from 'antd/es/table';

interface BridgeSectionProps {
  t: TypedTFunction;
  bridgesLoading: boolean;
  bridgesList: GetRegionBridges_ResultSet1[];
  columns: ColumnsType<GetRegionBridges_ResultSet1>;
  mobileRender: (record: GetRegionBridges_ResultSet1) => React.ReactNode;
  effectiveRegion: string | null;
  onCreateBridge: (regionName: string) => void;
}

export const BridgeSection: React.FC<BridgeSectionProps> = ({
  t,
  bridgesLoading,
  bridgesList,
  columns,
  mobileRender,
  effectiveRegion,
  onCreateBridge,
}) => (
  <Row gutter={[24, 24]}>
    <Col span={24}>
      {effectiveRegion ? (
        <Flex vertical>
          <ResourceListView
            title={
              <Typography.Title level={4} className="mb-0">
                {t('regions.bridgesInRegion', { region: effectiveRegion })}
              </Typography.Title>
            }
            loading={bridgesLoading}
            data={bridgesList}
            columns={columns}
            mobileRender={mobileRender}
            rowKey="bridgeName"
            searchPlaceholder={t('bridges.searchBridges')}
            emptyDescription={t('bridges.noBridges')}
            data-testid="system-bridge-table"
            actions={
              <TooltipButton
                tooltip={t('bridges.createBridge')}
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => onCreateBridge(effectiveRegion)}
                data-testid="system-create-bridge-button"
              />
            }
          />
        </Flex>
      ) : (
        <Flex vertical>
          <PageHeader title={t('bridges.title')} subtitle={t('regions.selectRegionToView')} />
          <Empty description={t('regions.selectRegionPrompt')} />
        </Flex>
      )}
    </Col>
  </Row>
);
