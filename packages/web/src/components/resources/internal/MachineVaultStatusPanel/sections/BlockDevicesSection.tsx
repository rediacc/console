import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Card, Flex, List, type ListProps, Tag, Typography } from 'antd';
import React from 'react';
import {
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldStrongValue,
  DetailPanelFieldValue,
  DetailPanelTitleGroup,
} from '@/components/resources/internal/detailPanelPrimitives';
import { CodeOutlined, HddOutlined } from '@/utils/optimizedIcons';
import type { BlockDevice, BlockDevicePartition } from '../types';

interface BlockDevicesSectionProps {
  devices: BlockDevice[];
  t: TypedTFunction;
}

export const BlockDevicesSection: React.FC<BlockDevicesSectionProps> = ({ devices, t }) => (
  <Flex vertical>
    <DetailPanelDivider orientationMargin="left">
      <HddOutlined />
      {t('resources:repositories.blockDevices')}
    </DetailPanelDivider>

    <List
      dataSource={devices}
      data-testid="vault-status-block-devices-list"
      renderItem={
        ((device: BlockDevice) => (
          <Card size="small" data-testid={`vault-status-block-device-${device.name}`}>
            <Flex justify="space-between" align="center">
              <DetailPanelTitleGroup>
                <HddOutlined />
                <DetailPanelFieldStrongValue
                  data-testid={`vault-status-device-path-${device.name}`}
                >
                  {device.path}
                </DetailPanelFieldStrongValue>
              </DetailPanelTitleGroup>
              <Flex>
                <Tag bordered={false} data-testid={`vault-status-device-type-${device.name}`}>
                  {device.type}
                </Tag>
                <Tag bordered={false} data-testid={`vault-status-device-size-${device.name}`}>
                  {device.size_human}
                </Tag>
              </Flex>
            </Flex>

            <Flex vertical>
              {device.model && device.model !== 'Unknown' && (
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldLabel>
                    {t('resources:repositories.model')}:
                  </DetailPanelFieldLabel>
                  <DetailPanelFieldValue>{device.model}</DetailPanelFieldValue>
                </Flex>
              )}

              {device.partitions.length > 0 && (
                <Flex vertical>
                  <DetailPanelFieldLabel>
                    {t('resources:repositories.partitions')}:
                  </DetailPanelFieldLabel>
                  <Flex vertical>
                    {device.partitions.map((part: BlockDevicePartition) => (
                      <Flex key={`${device.name}-${part.name}`} align="center">
                        <CodeOutlined />
                        <Typography.Text>
                          {part.name}: {part.size_human}
                          {part.filesystem && ` (${part.filesystem})`}
                          {part.mountpoint && ` • ${part.mountpoint}`}
                        </Typography.Text>
                      </Flex>
                    ))}
                  </Flex>
                </Flex>
              )}
            </Flex>
          </Card>
        )) as ListProps<unknown>['renderItem']
      }
    />
  </Flex>
);
