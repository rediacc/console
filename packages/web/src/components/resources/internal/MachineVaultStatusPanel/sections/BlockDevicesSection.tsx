import React from 'react';
import { Card, Flex, List, type ListProps, Tag, Typography } from 'antd';
import {
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldStrongValue,
  DetailPanelFieldValue,
  DetailPanelTitleGroup,
} from '@/components/resources/internal/detailPanelPrimitives';
import { CodeOutlined, HddOutlined } from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { BlockDevice, BlockDevicePartition } from '../types';

interface BlockDevicesSectionProps {
  devices: BlockDevice[];
  t: TypedTFunction;
}

export const BlockDevicesSection: React.FC<BlockDevicesSectionProps> = ({ devices, t }) => (
  <Flex vertical className="gap-4 !mb-6">
    <DetailPanelDivider orientation="center" className="[&_.ant-divider-inner-text]:px-0">
      <Flex align="center" className="gap-2">
        <HddOutlined />
        {t('resources:repositories.blockDevices')}
      </Flex>
    </DetailPanelDivider>

    <List
      dataSource={devices}
      data-testid="vault-status-block-devices-list"
      className="[&_.ant-list-items]:flex [&_.ant-list-items]:flex-col [&_.ant-list-items]:gap-4 [&_.ant-list-item]:p-0 [&_.ant-list-item]:border-0"
      renderItem={
        ((device: BlockDevice) => (
          <Card size="small" data-testid={`vault-status-block-device-${device.name}`}>
            <Flex justify="space-between" align="center">
              <DetailPanelTitleGroup className="gap-2">
                <HddOutlined />
                <DetailPanelFieldStrongValue
                  data-testid={`vault-status-device-path-${device.name}`}
                >
                  {device.path}
                </DetailPanelFieldStrongValue>
              </DetailPanelTitleGroup>
              <Flex className="gap-2">
                <Tag bordered={false} data-testid={`vault-status-device-type-${device.name}`}>
                  {device.type}
                </Tag>
                <Tag bordered={false} data-testid={`vault-status-device-size-${device.name}`}>
                  {device.size_human}
                </Tag>
              </Flex>
            </Flex>

            <Flex vertical className="gap-2">
              {device.model && device.model !== 'Unknown' && (
                <Flex justify="space-between" align="center">
                  <DetailPanelFieldLabel>
                    {t('resources:repositories.model')}:
                  </DetailPanelFieldLabel>
                  <DetailPanelFieldValue>{device.model}</DetailPanelFieldValue>
                </Flex>
              )}

              {device.partitions.length > 0 && (
                <Flex vertical className="gap-1">
                  <DetailPanelFieldLabel>
                    {t('resources:repositories.partitions')}:
                  </DetailPanelFieldLabel>
                  <Flex vertical className="gap-1">
                    {device.partitions.map((part: BlockDevicePartition) => (
                      <Flex key={`${device.name}-${part.name}`} align="center" className="gap-2">
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
