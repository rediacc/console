import React, { type JSX } from 'react';
import { Alert, Col, Descriptions, Flex, Form, Space, Tag, Typography } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
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
    }
  > = {
    compatible: {
      type: 'success',
      icon: <CheckCircleOutlined />,
    },
    warning: {
      type: 'warning',
      icon: <WarningOutlined />,
    },
    incompatible: {
      type: 'error',
      icon: <ExclamationCircleOutlined />,
    },
    unknown: {
      type: 'info',
      icon: <QuestionCircleOutlined />,
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
      <Form.Item
        label={
          <Typography.Text strong>{t('vaultEditor.systemCompatibility.title')}</Typography.Text>
        }
        colon={false}
      >
        <Flex vertical gap={8} className="w-full">
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label={t('vaultEditor.systemCompatibility.operatingSystem')}>
              {osInfo.pretty_name || t('vaultEditor.systemCompatibility.unknown')}
            </Descriptions.Item>
            <Descriptions.Item label={t('vaultEditor.systemCompatibility.kernelVersion')}>
              {kernelCompatibility.kernel_version || t('vaultEditor.systemCompatibility.unknown')}
            </Descriptions.Item>
            <Descriptions.Item label={t('vaultEditor.systemCompatibility.btrfsAvailable')}>
              {kernelCompatibility.btrfs_available ? (
                <Tag>{t('vaultEditor.systemCompatibility.yes')}</Tag>
              ) : (
                <Tag>{t('vaultEditor.systemCompatibility.no')}</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('vaultEditor.systemCompatibility.sudoAvailable')}>
              <Tag>{sudoConfigValue.text}</Tag>
            </Descriptions.Item>
            {osSetupCompleted !== null && (
              <Descriptions.Item label={t('vaultEditor.systemCompatibility.osSetup')}>
                <Tag>
                  {osSetupCompleted
                    ? t('vaultEditor.systemCompatibility.setupCompleted')
                    : t('vaultEditor.systemCompatibility.setupRequired')}
                </Tag>
              </Descriptions.Item>
            )}
          </Descriptions>

          <Alert
            type={config.type}
            icon={config.icon}
            message={
              <Space>
                <Typography.Text strong>
                  {t('vaultEditor.systemCompatibility.compatibilityStatus')}:
                </Typography.Text>
                {/* eslint-disable-next-line no-restricted-syntax */}
                <Typography.Text style={{ textTransform: 'capitalize' }}>
                  {t(`vaultEditor.systemCompatibility.${status}`)}
                </Typography.Text>
              </Space>
            }
            description={
              <>
                {kernelCompatibility.compatibility_issues &&
                  kernelCompatibility.compatibility_issues.length > 0 && (
                    <Flex vertical>
                      <Typography.Text strong>
                        {t('vaultEditor.systemCompatibility.knownIssues')}:
                      </Typography.Text>
                      <ul>
                        {kernelCompatibility.compatibility_issues.map(
                          (issue: string, index: number) => (
                            <li key={index}>{issue}</li>
                          )
                        )}
                      </ul>
                    </Flex>
                  )}
                {kernelCompatibility.recommendations &&
                  kernelCompatibility.recommendations.length > 0 && (
                    <Flex vertical>
                      <Typography.Text strong>
                        {t('vaultEditor.systemCompatibility.recommendations')}:
                      </Typography.Text>
                      <ul>
                        {kernelCompatibility.recommendations.map((rec: string, index: number) => (
                          <li key={index}>{rec}</li>
                        ))}
                      </ul>
                    </Flex>
                  )}
              </>
            }
            showIcon
          />
        </Flex>
      </Form.Item>
    </Col>
  );
};
