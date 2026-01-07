import React from 'react';
import { Col, Flex, Progress, Row, Space, Typography } from 'antd';
import {
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldRow,
  DetailPanelFieldValue,
  DetailPanelSectionCard,
} from '@/components/resources/internal/detailPanelPrimitives';
import { DatabaseOutlined, InfoCircleOutlined } from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import type { RepositoryPanelData } from '../types';

interface StorageSectionProps {
  repository: GetTeamRepositories_ResultSet1;
  panelData: RepositoryPanelData;
  t: TypedTFunction;
}

export const StorageSection: React.FC<StorageSectionProps> = ({ repository, panelData, t }) => {
  const { repositoryData } = panelData;
  const diskPercent = repositoryData.disk_space?.use_percent
    ? parseInt(repositoryData.disk_space.use_percent, 10)
    : 0;

  return (
    <Flex vertical>
      <DetailPanelDivider data-testid="repository-detail-storage-divider">
        <InfoCircleOutlined />
        {t('resources:repositories.storageInfo')}
      </DetailPanelDivider>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <DetailPanelSectionCard
            size="small"
            data-testid={`repo-detail-storage-info-card-${repository.repositoryName}`}
          >
            <Flex vertical className="w-full">
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>
                  {t('resources:repositories.imageSize')}:
                </DetailPanelFieldLabel>
                <DetailPanelFieldValue>{repositoryData.size_human}</DetailPanelFieldValue>
              </DetailPanelFieldRow>
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>
                  {t('resources:repositories.lastModified')}:
                </DetailPanelFieldLabel>
                <DetailPanelFieldValue>{repositoryData.modified_human}</DetailPanelFieldValue>
              </DetailPanelFieldRow>
            </Flex>
          </DetailPanelSectionCard>
        </Col>

        {repositoryData.mounted && repositoryData.disk_space && (
          <Col span={24}>
            <DetailPanelSectionCard
              size="small"
              data-testid={`repo-detail-disk-usage-card-${repository.repositoryName}`}
            >
              <Flex vertical className="w-full">
                <DetailPanelFieldRow>
                  <Space>
                    <DatabaseOutlined />
                    <DetailPanelFieldValue strong>
                      {t('resources:repositories.diskUsage')}
                    </DetailPanelFieldValue>
                  </Space>
                </DetailPanelFieldRow>
                <DetailPanelFieldValue>
                  {repositoryData.disk_space.used} / {repositoryData.disk_space.total}
                </DetailPanelFieldValue>
                <Progress
                  percent={diskPercent}
                  status={diskPercent > 90 ? 'exception' : 'normal'}
                  data-testid={`repo-detail-disk-usage-progress-${repository.repositoryName}`}
                />
                <Typography.Text>
                  {t('resources:repositories.available')}: {repositoryData.disk_space.available}
                </Typography.Text>
              </Flex>
            </DetailPanelSectionCard>
          </Col>
        )}
      </Row>
    </Flex>
  );
};
