import React, { useState, useEffect } from 'react';
import { Tooltip } from 'antd';
import { useApiHealth } from '@/api/queries/health';
import { versionService } from '@/services/versionService';
import { CloudServerOutlined, DesktopOutlined, ClockCircleOutlined } from '@/utils/optimizedIcons';
import {
  FooterContainer,
  VersionItem,
  VersionLabel,
  VersionValue,
  Separator,
  EnvironmentTag,
  UptimeText,
} from './styles';

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

  const apiVersion = apiHealth?.version ? `v${apiHealth.version}` : apiLoading ? '...' : 'Unknown';
  const environment = apiHealth?.environment || 'Unknown';
  const isProduction = environment === 'Production';
  const uptime = apiHealth?.uptime;

  return (
    <FooterContainer data-testid="system-version-footer">
      <VersionItem>
        <DesktopOutlined style={{ opacity: 0.5 }} />
        <VersionLabel>Console</VersionLabel>
        <VersionValue data-testid="ui-version">{uiVersion}</VersionValue>
      </VersionItem>

      <Separator>|</Separator>

      <VersionItem>
        <CloudServerOutlined style={{ opacity: 0.5 }} />
        <VersionLabel>API</VersionLabel>
        <VersionValue data-testid="api-version">{apiVersion}</VersionValue>
        <EnvironmentTag
          $isProduction={isProduction}
          variant={isProduction ? 'success' : 'warning'}
          data-testid="environment-tag"
        >
          {environment}
        </EnvironmentTag>
      </VersionItem>

      {uptime && (
        <>
          <Separator>|</Separator>
          <Tooltip title="API Uptime">
            <VersionItem>
              <ClockCircleOutlined style={{ opacity: 0.5 }} />
              <UptimeText data-testid="api-uptime">{formatUptime(uptime)}</UptimeText>
            </VersionItem>
          </Tooltip>
        </>
      )}
    </FooterContainer>
  );
};

export default SystemVersionFooter;
