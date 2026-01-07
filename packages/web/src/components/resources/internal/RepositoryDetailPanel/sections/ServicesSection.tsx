import React from 'react';
import { Card, Col, Flex, Row, Tag, Typography } from 'antd';
import {
  DetailPanelDivider,
  DetailPanelFieldValue,
} from '@/components/resources/internal/detailPanelPrimitives';
import { CodeOutlined } from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import type { RepositoryPanelData } from '../types';

interface ServicesSectionProps {
  repository: GetTeamRepositories_ResultSet1;
  panelData: RepositoryPanelData;
  t: TypedTFunction;
}

export const ServicesSection: React.FC<ServicesSectionProps> = ({ repository, panelData, t }) => (
  <Flex vertical>
    <DetailPanelDivider data-testid="repository-detail-services-divider">
      <CodeOutlined />
      {t('resources:repositories.servicesSection')}
    </DetailPanelDivider>

    <Flex vertical data-testid="repository-detail-services-list">
      {panelData.services.map((service, index) => {
        return (
          <Card
            key={`${service.name}-${index}`}
            size="small"
            data-testid={`repo-detail-service-card-${repository.repositoryName}-${service.name}`}
          >
            <Row gutter={[16, 8]}>
              <Col span={24}>
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldValue
                    strong
                    data-testid={`repo-detail-service-name-${repository.repositoryName}-${service.name}`}
                  >
                    {service.name}
                  </DetailPanelFieldValue>
                  <Tag
                    bordered={false}
                    data-testid={`repo-detail-service-status-${repository.repositoryName}-${service.name}`}
                  >
                    {service.active_state}
                  </Tag>
                </Flex>
              </Col>
              {(service.memory_human ??
                service.main_pid ??
                service.uptime_human ??
                service.restarts !== undefined) && (
                <Col span={24}>
                  <Flex wrap>
                    {service.memory_human && (
                      <Flex vertical>
                        <Typography.Text>{t('resources:repositories.memoryLabel')}</Typography.Text>
                        <Typography.Text>{service.memory_human}</Typography.Text>
                      </Flex>
                    )}
                    {service.main_pid && (
                      <Flex vertical>
                        <Typography.Text>{t('resources:repositories.pidLabel')}</Typography.Text>
                        <Typography.Text>{service.main_pid}</Typography.Text>
                      </Flex>
                    )}
                    {service.uptime_human && (
                      <Flex vertical>
                        <Typography.Text>{t('resources:repositories.uptimeLabel')}</Typography.Text>
                        <Typography.Text>{service.uptime_human}</Typography.Text>
                      </Flex>
                    )}
                    {service.restarts !== undefined && (
                      <Flex vertical>
                        <Typography.Text>
                          {t('resources:repositories.restartsLabel')}
                        </Typography.Text>
                        <Typography.Text>{service.restarts}</Typography.Text>
                      </Flex>
                    )}
                  </Flex>
                </Col>
              )}
            </Row>
          </Card>
        );
      })}
    </Flex>
  </Flex>
);
