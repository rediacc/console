import React, { useEffect, useMemo } from 'react';
import { Card, Col, Empty, Flex, Progress, Row, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import {
  DetailPanelBody,
  DetailPanelDivider,
  DetailPanelFieldLabel,
  DetailPanelFieldMonospaceValue,
  DetailPanelFieldRow,
  DetailPanelFieldValue,
  DetailPanelSectionTitle,
  DetailPanelSurface,
} from '@/components/resources/internal/detailPanelPrimitives';
import { useTraceModal } from '@/hooks/useDialogState';
import { calculateResourcePercent } from '@/platform';
import type { Machine } from '@/types';
import {
  DatabaseOutlined,
  DesktopOutlined,
  HddOutlined,
  InfoCircleOutlined,
} from '@/utils/optimizedIcons';
import { abbreviatePath } from '@/utils/pathUtils';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
import { BlockDevicesSection } from './sections/BlockDevicesSection';
import { NetworkSection } from './sections/NetworkSection';
import { SystemContainersSection } from './sections/SystemContainersSection';
import type { SystemInfo, VaultData } from './types';

interface MachineVaultStatusPanelProps {
  machine: Machine | null;
  visible: boolean;
  onClose: () => void;
  splitView?: boolean;
}

export const MachineVaultStatusPanel: React.FC<MachineVaultStatusPanelProps> = ({
  machine,
  visible,
  onClose,
  splitView = false,
}) => {
  const { t } = useTranslation(['machines', 'resources', 'common']);
  const auditTrace = useTraceModal();

  const vaultData = useMemo<VaultData | null>(() => {
    if (!machine?.vaultStatus) return null;

    const parsed = parseVaultStatus(machine.vaultStatus);

    if (parsed.status !== 'completed' || !parsed.rawResult) {
      return null;
    }

    try {
      return JSON.parse(parsed.rawResult);
    } catch (err) {
      console.error('Error parsing vault status result:', err);
      return null;
    }
  }, [machine]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && visible) {
        onClose();
      }
    };

    if (visible) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [visible, onClose]);

  if (!machine || !visible) {
    return null;
  }

  return (
    <>
      <DetailPanelSurface $splitView={splitView} $visible={visible}>
        <DetailPanelBody data-testid="vault-status-content">
          {vaultData ? (
            <>
              {vaultData.system && (
                <>
                  <SystemInfoSection system={vaultData.system} t={t} />
                  <ResourceUsageSection system={vaultData.system} t={t} />
                </>
              )}

              {vaultData.network && <NetworkSection network={vaultData.network} t={t} />}

              {vaultData.block_devices && vaultData.block_devices.length > 0 && (
                <BlockDevicesSection devices={vaultData.block_devices} t={t} />
              )}

              {vaultData.system_containers && vaultData.system_containers.length > 0 && (
                <SystemContainersSection containers={vaultData.system_containers} t={t} />
              )}
            </>
          ) : (
            <Flex>
              <Empty description={t('machines:noVaultData')} data-testid="vault-status-empty" />
            </Flex>
          )}
        </DetailPanelBody>
      </DetailPanelSurface>

      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />
    </>
  );
};

interface SystemInfoSectionProps {
  system: SystemInfo;
  t: TypedTFunction;
}

const SystemInfoSection: React.FC<SystemInfoSectionProps> = ({ system, t }) => {
  return (
    <Flex vertical>
      <DetailPanelDivider
        orientation="center"
        className="!mt-0 [&_.ant-divider-inner-text]:px-0"
      >
        <Flex align="center" className="gap-2">
          <DesktopOutlined />
          <DetailPanelSectionTitle
            level={5}
            className="!m-0"
            data-testid="vault-status-system-info-title"
          >
            {t('resources:repositories.systemInfo')}
          </DetailPanelSectionTitle>
        </Flex>
      </DetailPanelDivider>

      <Card size="small" data-testid="vault-status-system-info-card">
        <Flex vertical className="w-full gap-sm">
          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>{t('resources:repositories.hostname')}:</DetailPanelFieldLabel>
            <DetailPanelFieldValue data-testid="vault-status-hostname">
              {system.hostname}
            </DetailPanelFieldValue>
          </DetailPanelFieldRow>
          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>{t('resources:repositories.uptime')}:</DetailPanelFieldLabel>
            <DetailPanelFieldValue data-testid="vault-status-uptime">
              {system.uptime}
            </DetailPanelFieldValue>
          </DetailPanelFieldRow>
          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>{t('resources:repositories.osName')}:</DetailPanelFieldLabel>
            <DetailPanelFieldValue data-testid="vault-status-os-name">
              {system.os_name}
            </DetailPanelFieldValue>
          </DetailPanelFieldRow>
          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>{t('resources:repositories.kernel')}:</DetailPanelFieldLabel>
            <DetailPanelFieldValue data-testid="vault-status-kernel">
              {system.kernel}
            </DetailPanelFieldValue>
          </DetailPanelFieldRow>
          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>{t('resources:repositories.cpu')}:</DetailPanelFieldLabel>
            <DetailPanelFieldValue data-testid="vault-status-cpu">
              {system.cpu_count} × {system.cpu_model}
            </DetailPanelFieldValue>
          </DetailPanelFieldRow>
          <DetailPanelFieldRow>
            <DetailPanelFieldLabel>{t('resources:repositories.systemTime')}:</DetailPanelFieldLabel>
            <DetailPanelFieldValue data-testid="vault-status-system-time">
              {system.system_time_human} ({system.timezone})
            </DetailPanelFieldValue>
          </DetailPanelFieldRow>
        </Flex>
      </Card>
    </Flex>
  );
};

interface ResourceUsageSectionProps {
  system: SystemInfo;
  t: TypedTFunction;
}

const ResourceUsageSection: React.FC<ResourceUsageSectionProps> = ({ system, t }) => {
  const memoryPercent = calculateResourcePercent(system.memory.used, system.memory.total) || 0;
  const diskPercent = Number.parseInt(system.disk.use_percent, 10) || 0;
  const datastorePercent = Number.parseInt(system.datastore.use_percent, 10) || 0;

  return (
    <Flex vertical>
      <DetailPanelDivider orientation="center" className="[&_.ant-divider-inner-text]:px-0">
        <Flex align="center" className="gap-2">
          <InfoCircleOutlined />
          <DetailPanelSectionTitle level={5} className="!m-0">
            {t('resources:repositories.resourceUsage')}
          </DetailPanelSectionTitle>
        </Flex>
      </DetailPanelDivider>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card size="small" data-testid="vault-status-memory-card">
            <Flex className="gap-2" align="center">
              <DatabaseOutlined />
              <Typography.Title level={5} className="!m-0">
                {t('resources:repositories.memory')}
              </Typography.Title>
            </Flex>
            <Progress percent={Math.round(memoryPercent)} />
            <Typography.Text>
              {t('resources:repositories.used')}: {system.memory.used} / {system.memory.total}
            </Typography.Text>
            <Typography.Text>
              {t('resources:repositories.available')}: {system.memory.available}
            </Typography.Text>
          </Card>
        </Col>

        <Col span={24}>
          <Card size="small" data-testid="vault-status-disk-card">
            <Flex className="gap-2" align="center">
              <HddOutlined />
              <Typography.Title level={5} className="!m-0">
                {t('resources:repositories.disk')}
              </Typography.Title>
            </Flex>
            <Progress percent={diskPercent} />
            <Typography.Text>
              {t('resources:repositories.used')}: {system.disk.used} / {system.disk.total}
            </Typography.Text>
            <Typography.Text>
              {t('resources:repositories.available')}: {system.disk.available}
            </Typography.Text>
          </Card>
        </Col>

        <Col span={24}>
          <Card size="small" data-testid="vault-status-datastore-card">
            <Flex className="gap-2" align="center">
              <DatabaseOutlined />
              <Typography.Title level={5} className="!m-0">
                {t('resources:repositories.datastore')}
              </Typography.Title>
            </Flex>
            {system.datastore.path && (
              <DetailPanelFieldRow>
                <DetailPanelFieldLabel>{t('common:general.path')}:</DetailPanelFieldLabel>
                <DetailPanelFieldMonospaceValue copyable={{ text: system.datastore.path }}>
                  {abbreviatePath(system.datastore.path, 40)}
                </DetailPanelFieldMonospaceValue>
              </DetailPanelFieldRow>
            )}
            <Progress percent={datastorePercent} />
            <Typography.Text>
              {t('resources:repositories.used')}: {system.datastore.used} / {system.datastore.total}
            </Typography.Text>
            <Typography.Text>
              {t('resources:repositories.available')}: {system.datastore.available}
            </Typography.Text>
          </Card>
        </Col>
      </Row>
    </Flex>
  );
};
