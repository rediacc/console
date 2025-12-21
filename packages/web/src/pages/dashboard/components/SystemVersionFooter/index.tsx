import { Tag, Tooltip, Typography, Flex } from 'antd';
import React, { useEffect, useState } from 'react';
import { useApiHealth } from '@/api/queries/health';
import { versionService } from '@/services/versionService';
import { ClockCircleOutlined, CloudServerOutlined, DesktopOutlined } from '@ant-design/icons';

const formatUptime = (uptime: { days: number; hours: number; minutes: number }): string => {
  const parts: string[] = [];
  if (uptime.days > 0) parts.push(`${uptime.days}d`);
  if (uptime.hours > 0) parts.push(`${uptime.hours}h`);
  if (uptime.minutes > 0 || parts.length === 0) parts.push(`${uptime.minutes}m`);
  return parts.join(' ');
};

const SystemVersionFooter: React.FC = () => {
  const [uiVersion, setUiVersion] = useState<string>('...');
  const { data: apiHealth, isLoading: apiLoading } = useApiHealth();

  useEffect(() => {
    const fetchUiVersion = async () => {
      try {
        const versionInfo = await versionService.getVersion();
        setUiVersion(versionService.formatVersion(versionInfo.version));
      } catch {
        setUiVersion('Unknown');
      }
    };
    fetchUiVersion();
  }, []);

  // Determine API version display
  let apiVersion: string;
  if (apiHealth?.version) {
    apiVersion = `v${apiHealth.version}`;
  } else if (apiLoading) {
    apiVersion = '...';
  } else {
    apiVersion = 'Unknown';
  }

  const environment = apiHealth?.environment || 'Unknown';
  const isProduction = environment === 'Production';
  const uptime = apiHealth?.uptime;

  return (
    <Flex align="center" justify="center" wrap data-testid="system-version-footer">
      <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
        <DesktopOutlined style={{ color: 'var(--ant-color-text-tertiary)' }} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Console
        </Typography.Text>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 12, fontWeight: 500 }}
          data-testid="ui-version"
        >
          {uiVersion}
        </Typography.Text>
      </Flex>

      <span style={{ fontSize: 14 }}>|</span>

      <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
        <CloudServerOutlined style={{ color: 'var(--ant-color-text-tertiary)' }} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          API
        </Typography.Text>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 12, fontWeight: 500 }}
          data-testid="api-version"
        >
          {apiVersion}
        </Typography.Text>
        <Tag
          bordered={false}
          color={isProduction ? 'success' : 'warning'}
          data-testid="environment-tag"
        >
          {environment}
        </Tag>
      </Flex>

      {uptime && (
        <>
          <span style={{ fontSize: 14 }}>|</span>
          <Tooltip title="API Uptime">
            <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
              <ClockCircleOutlined style={{ color: 'var(--ant-color-text-tertiary)' }} />
              <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="api-uptime">
                {formatUptime(uptime)}
              </Typography.Text>
            </Flex>
          </Tooltip>
        </>
      )}
    </Flex>
  );
};

export default SystemVersionFooter;
