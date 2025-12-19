import React, { type JSX } from 'react';
import { Alert, Col, Descriptions, Space } from 'antd';
import { RediaccStack, RediaccTag, RediaccText } from '@/components/ui';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { CompatibilityStatusText, FieldItem, IssueList, ListSection, RecommendationList } from '../styles';
import type { VaultFormValues } from '../types';
import type { FormInstance } from 'antd';

interface VaultEditorSystemCompatibilityProps {
  form: FormInstance<VaultFormValues>;
  osSetupCompleted: boolean | null;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export const VaultEditorSystemCompatibility: React.FC<VaultEditorSystemCompatibilityProps> = ({
  form,
  osSetupCompleted,
  t,
}) => {
  const kernelCompatibility = form.getFieldValue('kernel_compatibility');

  if (!kernelCompatibility) {
    return null;
  }

  const status = kernelCompatibility.compatibility_status || 'unknown';
  const osInfo = kernelCompatibility.os_info || {};

  const statusConfig: Record<
    string,
    {
      type: 'success' | 'warning' | 'error' | 'info';
      icon: JSX.Element;
      statusVariant: 'success' | 'warning' | 'error' | 'info';
    }
  > = {
    compatible: {
      type: 'success',
      icon: <CheckCircleOutlined />,
      statusVariant: 'success',
    },
    warning: {
      type: 'warning',
      icon: <WarningOutlined />,
      statusVariant: 'warning',
    },
    incompatible: {
      type: 'error',
      icon: <ExclamationCircleOutlined />,
      statusVariant: 'error',
    },
    unknown: {
      type: 'info',
      icon: <QuestionCircleOutlined />,
      statusVariant: 'info',
    },
  };

  const config = statusConfig[status] || statusConfig.unknown;

  const sudoStatus = kernelCompatibility.sudo_available || 'unknown';
  const sudoConfig: Record<string, { color: string; text: string }> = {
    available: {
      color: 'success',
      text: t('vaultEditor.systemCompatibility.available'),
    },
    password_required: {
      color: 'warning',
      text: t('vaultEditor.systemCompatibility.passwordRequired'),
    },
    not_installed: {
      color: 'error',
      text: t('vaultEditor.systemCompatibility.notInstalled'),
    },
  };

  const sudoConfigValue = sudoConfig[sudoStatus] || {
    color: 'neutral',
    text: t('vaultEditor.systemCompatibility.unknown'),
  };

  return (
    <Col xs={24} lg={12}>
      <FieldItem
        label={<RediaccText weight="bold">{t('vaultEditor.systemCompatibility.title')}</RediaccText>}
        colon={false}
      >
        <RediaccStack direction="vertical" gap="sm" fullWidth>
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label={t('vaultEditor.systemCompatibility.operatingSystem')}>
              {osInfo.pretty_name || t('vaultEditor.systemCompatibility.unknown')}
            </Descriptions.Item>
            <Descriptions.Item label={t('vaultEditor.systemCompatibility.kernelVersion')}>
              {kernelCompatibility.kernel_version || t('vaultEditor.systemCompatibility.unknown')}
            </Descriptions.Item>
            <Descriptions.Item label={t('vaultEditor.systemCompatibility.btrfsAvailable')}>
              {kernelCompatibility.btrfs_available ? (
                <RediaccTag variant="success">{t('vaultEditor.systemCompatibility.yes')}</RediaccTag>
              ) : (
                <RediaccTag variant="warning">{t('vaultEditor.systemCompatibility.no')}</RediaccTag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('vaultEditor.systemCompatibility.sudoAvailable')}>
              <RediaccTag
                variant={
                  sudoConfigValue.color as 'neutral' | 'success' | 'error' | 'warning' | 'primary'
                }
              >
                {sudoConfigValue.text}
              </RediaccTag>
            </Descriptions.Item>
            {osSetupCompleted !== null && (
              <Descriptions.Item label={t('vaultEditor.systemCompatibility.osSetup')}>
                <RediaccTag variant={osSetupCompleted ? 'success' : 'warning'}>
                  {osSetupCompleted
                    ? t('vaultEditor.systemCompatibility.setupCompleted')
                    : t('vaultEditor.systemCompatibility.setupRequired')}
                </RediaccTag>
              </Descriptions.Item>
            )}
          </Descriptions>

          <Alert
            type={config.type}
            icon={config.icon}
            message={
              <Space>
                <RediaccText weight="bold">
                  {t('vaultEditor.systemCompatibility.compatibilityStatus')}:
                </RediaccText>
                <CompatibilityStatusText $variant={config.statusVariant}>
                  {t(`vaultEditor.systemCompatibility.${status}`)}
                </CompatibilityStatusText>
              </Space>
            }
            description={
              <>
                {kernelCompatibility.compatibility_issues &&
                  kernelCompatibility.compatibility_issues.length > 0 && (
                    <ListSection>
                      <RediaccText weight="bold">
                        {t('vaultEditor.systemCompatibility.knownIssues')}:
                      </RediaccText>
                      <IssueList>
                        {kernelCompatibility.compatibility_issues.map(
                          (issue: string, index: number) => (
                            <li key={index}>{issue}</li>
                          )
                        )}
                      </IssueList>
                    </ListSection>
                  )}
                {kernelCompatibility.recommendations &&
                  kernelCompatibility.recommendations.length > 0 && (
                    <ListSection>
                      <RediaccText weight="bold">
                        {t('vaultEditor.systemCompatibility.recommendations')}:
                      </RediaccText>
                      <RecommendationList>
                        {kernelCompatibility.recommendations.map((rec: string, index: number) => (
                          <li key={index}>{rec}</li>
                        ))}
                      </RecommendationList>
                    </ListSection>
                  )}
              </>
            }
            showIcon
          />
        </RediaccStack>
      </FieldItem>
    </Col>
  );
};
