import React from 'react';
import { Card, Flex, List, Tag, Typography, type ListProps } from 'antd';
import {
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldStrongValue,
  DetailPanelFieldValue,
  DetailPanelTitleGroup,
} from '@/components/resources/internal/detailPanelPrimitives';
import { ContainerOutlined } from '@/utils/optimizedIcons';
import type { Container } from '../types';
import type { TFunction } from 'i18next';

interface SystemContainersSectionProps {
  containers: Container[];
  t: TFunction;
}

export const SystemContainersSection: React.FC<SystemContainersSectionProps> = ({
  containers,
  t,
}) => (
  <Flex vertical>
    <DetailPanelDivider orientationMargin="left">
      <ContainerOutlined />
      {t('resources:repositories.systemContainers')}
    </DetailPanelDivider>

    <List
      dataSource={containers}
      data-testid="vault-status-containers-list"
      renderItem={
        ((container: Container) => (
          <Card size="small" data-testid={`vault-status-container-${container.id}`}>
            <Flex justify="space-between" align="center">
              <DetailPanelTitleGroup>
                <ContainerOutlined />
                <DetailPanelFieldStrongValue
                  data-testid={`vault-status-container-name-${container.id}`}
                >
                  {container.name}
                </DetailPanelFieldStrongValue>
              </DetailPanelTitleGroup>
              <Tag bordered={false} data-testid={`vault-status-container-state-${container.id}`}>
                {container.state}
              </Tag>
            </Flex>

            <Flex vertical>
              {container.image && <Typography.Text ellipsis>{container.image}</Typography.Text>}
              {container.cpu_percent && (
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldLabel>CPU:</DetailPanelFieldLabel>
                  <DetailPanelFieldValue>{container.cpu_percent}</DetailPanelFieldValue>
                </Flex>
              )}
              {container.memory_usage && (
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldLabel>
                    {t('resources:repositories.memory')}:
                  </DetailPanelFieldLabel>
                  <DetailPanelFieldValue>{container.memory_usage}</DetailPanelFieldValue>
                </Flex>
              )}
            </Flex>
          </Card>
        )) as ListProps<unknown>['renderItem']
      }
    />
  </Flex>
);
