import React, { useEffect, useState } from 'react';
import { ClockCircleOutlined, CloudServerOutlined, DesktopOutlined } from '@ant-design/icons';
import { Tag, Tooltip, Typography, Flex } from 'antd';
import { useApiHealth } from '@/api/queries/health';
import { versionService } from '@/services/versionService';

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
  const uptime = apiHealth?.uptime;

  return (
    <Flex align="center" justify="center" gap={8} data-testid="system-version-footer">
      <Flex align="center" gap={8} className="inline-flex">
        <DesktopOutlined />
        <Typography.Text>Console</Typography.Text>
        <Typography.Text data-testid="ui-version">{uiVersion}</Typography.Text>
      </Flex>

      <Typography.Text>|</Typography.Text>

      <Flex align="center" gap={8} className="inline-flex">
        <CloudServerOutlined />
        <Typography.Text>API</Typography.Text>
        <Typography.Text data-testid="api-version">{apiVersion}</Typography.Text>
        <Tag bordered={false} data-testid="environment-tag">
          {environment}
        </Tag>
      </Flex>

      {uptime && (
        <>
          <Typography.Text>|</Typography.Text>
          <Tooltip title="API Uptime">
            <Flex align="center" gap={8} className="inline-flex">
              <ClockCircleOutlined />
              <Typography.Text data-testid="api-uptime">{formatUptime(uptime)}</Typography.Text>
            </Flex>
          </Tooltip>
        </>
      )}
    </Flex>
  );
};

export default SystemVersionFooter;
