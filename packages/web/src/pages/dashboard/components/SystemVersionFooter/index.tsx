import React, { useEffect, useState } from 'react';
import { Tooltip } from 'antd';
import { useApiHealth } from '@/api/queries/health';
import { RediaccText } from '@/components/ui';
import { versionService } from '@/services/versionService';
import { ClockCircleOutlined, CloudServerOutlined, DesktopOutlined } from '@/utils/optimizedIcons';
import { EnvironmentTag, FooterContainer, Separator, VersionItem } from './styles';

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
        <RediaccText size="sm" color="muted">
          Console
        </RediaccText>
        <RediaccText size="sm" color="secondary" weight="medium" data-testid="ui-version">
          {uiVersion}
        </RediaccText>
      </VersionItem>

      <Separator>|</Separator>

      <VersionItem>
        <CloudServerOutlined style={{ opacity: 0.5 }} />
        <RediaccText size="sm" color="muted">
          API
        </RediaccText>
        <RediaccText size="sm" color="secondary" weight="medium" data-testid="api-version">
          {apiVersion}
        </RediaccText>
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
              <RediaccText size="xs" color="muted" data-testid="api-uptime">
                {formatUptime(uptime)}
              </RediaccText>
            </VersionItem>
          </Tooltip>
        </>
      )}
    </FooterContainer>
  );
};

export default SystemVersionFooter;
