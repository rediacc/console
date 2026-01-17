import React from 'react';
import { Card, Flex, List, Tag, type ListProps } from 'antd';
import {
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldRow,
  DetailPanelFieldStrongValue,
  DetailPanelFieldValue,
  DetailPanelTitleGroup,
} from '@/components/resources/internal/detailPanelPrimitives';
import { CompassOutlined, WifiOutlined } from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { NetworkInterface, VaultNetwork } from '../types';

interface NetworkSectionProps {
  network: VaultNetwork;
  t: TypedTFunction;
}

export const NetworkSection: React.FC<NetworkSectionProps> = ({ network, t }) => {
  const interfaces = network.interfaces.filter(
    (iface) => iface.state !== 'unknown' && iface.name !== 'lo'
  );

  return (
    <Flex vertical className="gap-4">
      <DetailPanelDivider orientation="center" className="[&_.ant-divider-inner-text]:px-0">
        <Flex align="center" className="gap-2">
          <WifiOutlined />
          {t('resources:repositories.networkInfo')}
        </Flex>
      </DetailPanelDivider>

      {network.default_gateway && (
        <Card size="small" data-testid="vault-status-gateway-card">
          <Flex vertical className="w-full gap-sm">
            <DetailPanelFieldRow>
              <DetailPanelFieldLabel>
                {t('resources:repositories.defaultGateway')}:
              </DetailPanelFieldLabel>
              <DetailPanelFieldValue data-testid="vault-status-gateway">
                {network.default_gateway}
              </DetailPanelFieldValue>
            </DetailPanelFieldRow>
            {network.default_interface && (
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>
                  {t('resources:repositories.defaultInterface')}:
                </DetailPanelFieldLabel>
                <DetailPanelFieldValue data-testid="vault-status-interface">
                  {network.default_interface}
                </DetailPanelFieldValue>
              </DetailPanelFieldRow>
            )}
          </Flex>
        </Card>
      )}

      <List
        dataSource={interfaces}
        data-testid="vault-status-network-list"
        className="[&_.ant-list-items]:flex [&_.ant-list-items]:flex-col [&_.ant-list-items]:gap-4 [&_.ant-list-item]:p-0 [&_.ant-list-item]:border-0"
        renderItem={
          ((iface: NetworkInterface) => (
            <Card size="small" data-testid={`vault-status-network-${iface.name}`}>
              <Flex justify="space-between" align="center">
                <DetailPanelTitleGroup className="gap-2">
                  <CompassOutlined />
                  <DetailPanelFieldStrongValue
                    data-testid={`vault-status-network-name-${iface.name}`}
                  >
                    {iface.name}
                  </DetailPanelFieldStrongValue>
                </DetailPanelTitleGroup>
                <Tag bordered={false} data-testid={`vault-status-network-state-${iface.name}`}>
                  {iface.state}
                </Tag>
              </Flex>
              <Flex vertical className="gap-2">
                {iface.ipv4_addresses.length > 0 && (
                  <Flex vertical className="gap-1">
                    <DetailPanelFieldLabel>
                      {t('resources:repositories.ipAddresses')}:
                    </DetailPanelFieldLabel>
                    <Flex className="flex-wrap gap-2">
                      {iface.ipv4_addresses.map((ip: string) => (
                        <Tag key={ip} bordered={false} data-testid={`vault-status-ip-${ip}`}>
                          {ip}
                        </Tag>
                      ))}
                    </Flex>
                  </Flex>
                )}
                {iface.mac_address && iface.mac_address !== 'unknown' && (
                  <Flex justify="space-between" align="center">
                    <DetailPanelFieldLabel>
                      {t('resources:repositories.macAddress')}:
                    </DetailPanelFieldLabel>
                    <DetailPanelFieldValue>{iface.mac_address}</DetailPanelFieldValue>
                  </Flex>
                )}
                {iface.mtu > 0 && (
                  <Flex justify="space-between" align="center">
                    <DetailPanelFieldLabel>
                      {t('resources:repositories.mtu')}:
                    </DetailPanelFieldLabel>
                    <DetailPanelFieldValue>{iface.mtu}</DetailPanelFieldValue>
                  </Flex>
                )}
              </Flex>
            </Card>
          )) as ListProps<unknown>['renderItem']
        }
      />
    </Flex>
  );
};
