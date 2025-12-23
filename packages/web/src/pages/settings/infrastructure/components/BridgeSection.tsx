import React from 'react';
import { Button, Card, Col, Empty, Flex, Row, Table, Tooltip, Typography } from 'antd';
import type { Bridge } from '@/api/queries/bridges';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { PlusOutlined } from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

interface BridgeSectionProps {
  t: TFunction<'resources'>;
  tCommon: TFunction<'common'>;
  bridgesLoading: boolean;
  bridgesList: Bridge[];
  columns: ColumnsType<Bridge>;
  effectiveRegion: string | null;
  onCreateBridge: (regionName: string) => void;
}

export const BridgeSection: React.FC<BridgeSectionProps> = ({
  t,
  tCommon,
  bridgesLoading,
  bridgesList,
  columns,
  effectiveRegion,
  onCreateBridge,
}) => (
  <Row gutter={[24, 24]}>
    <Col span={24}>
      <Card>
        <Flex wrap align="center" justify="space-between" gap={8}>
          <Flex vertical>
            <Typography.Title level={4}>
              {effectiveRegion
                ? t('regions.bridgesInRegion', { region: effectiveRegion })
                : t('bridges.title')}
            </Typography.Title>
            {!effectiveRegion && (
              <Typography.Text>{t('regions.selectRegionToView')}</Typography.Text>
            )}
          </Flex>
          {effectiveRegion && (
            <Tooltip title={t('bridges.createBridge')}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => onCreateBridge(effectiveRegion)}
                data-testid="system-create-bridge-button"
                aria-label={t('bridges.createBridge')}
              />
            </Tooltip>
          )}
        </Flex>

        {!effectiveRegion ? (
          <Flex>
            <Empty description={t('regions.selectRegionPrompt')} />
          </Flex>
        ) : (
          <LoadingWrapper loading={bridgesLoading} centered minHeight={200} tip={tCommon('general.loading')}>
            <Table
              columns={columns}
              dataSource={bridgesList}
              rowKey="bridgeName"
              pagination={{
                total: bridgesList.length || 0,
                pageSize: 10,
                showSizeChanger: true,
                showTotal: (total) => t('bridges.totalBridges', { total }),
              }}
              locale={{ emptyText: t('bridges.noBridges') }}
              data-testid="system-bridge-table"
            />
          </LoadingWrapper>
        )}
      </Card>
    </Col>
  </Row>
);
