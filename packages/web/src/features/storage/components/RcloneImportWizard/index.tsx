import React, { useState } from 'react';
import { Button, Checkbox, Flex, Modal, Space, Steps, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useCreateStorage, useGetTeamStorages } from '@/api/api-hooks.generated';
import {
  createStatusColumn,
  createTruncatedColumn,
  RESPONSIVE_HIDE_XS,
} from '@/components/common/columns';
import { createSorter } from '@/platform';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CloudOutlined,
  InfoCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import { ConnectionTest } from './ConnectionTest';
import { ImportProgress } from './ImportProgress';
import { StepConfigForm } from './StepConfigForm';
import type {
  ImportStatus,
  RcloneConfig,
  RcloneConfigFields,
  RcloneImportWizardProps,
} from './types';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload';

const RcloneImportWizard: React.FC<RcloneImportWizardProps> = ({
  open,
  onClose,
  teamName,
  onImportComplete,
}) => {
  const { t } = useTranslation(['resources', 'common']);
  const [currentStep, setCurrentStep] = useState(0);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [parsedConfigs, setParsedConfigs] = useState<RcloneConfig[]>([]);
  const [importStatuses, setImportStatuses] = useState<ImportStatus[]>([]);
  const [isImporting, setIsImporting] = useState(false);
  const [parsingError, setParsingError] = useState<string | null>(null);

  const createStorageMutation = useCreateStorage();
  const { data: existingStorages = [] } = useGetTeamStorages(teamName);

  const isSkippableLine = (line: string): boolean => {
    const trimmed = line.trim();
    return !trimmed || trimmed.startsWith('#') || trimmed.startsWith(';');
  };

  const parseKeyValuePair = (line: string): [string, string | Record<string, unknown>] | null => {
    const kvMatch = /^([^=]+)=(.*)$/.exec(line);
    if (!kvMatch) return null;

    const key = kvMatch[1].trim();
    const value = kvMatch[2].trim();

    try {
      return [key, JSON.parse(value) as Record<string, unknown>];
    } catch {
      return [key, value];
    }
  };

  const saveCurrentSection = (
    configs: RcloneConfig[],
    section: string | null,
    config: RcloneConfigFields
  ): void => {
    if (section && config.type) {
      configs.push({ name: section, type: config.type, config: { ...config } });
    }
  };

  // Parse INI-style rclone config
  const parseRcloneConfig = (content: string): RcloneConfig[] => {
    const configs: RcloneConfig[] = [];
    const lines = content.split('\n');
    let currentSection: string | null = null;
    let currentConfig: RcloneConfigFields = {};

    for (const line of lines) {
      if (isSkippableLine(line)) continue;

      const trimmedLine = line.trim();
      const sectionMatch = /^\[(.+)\]$/.exec(trimmedLine);

      if (sectionMatch) {
        saveCurrentSection(configs, currentSection, currentConfig);
        currentSection = sectionMatch[1];
        currentConfig = {};
        continue;
      }

      if (currentSection) {
        const parsed = parseKeyValuePair(trimmedLine);
        if (parsed) {
          currentConfig[parsed[0]] = parsed[1];
        }
      }
    }

    saveCurrentSection(configs, currentSection, currentConfig);
    return configs;
  };

  const PROVIDER_MAPPING: Record<string, string> = {
    drive: 'drive',
    onedrive: 'onedrive',
    s3: 's3',
    b2: 'b2',
    mega: 'mega',
    dropbox: 'dropbox',
    box: 'box',
    azureblob: 'azureblob',
    swift: 'swift',
    webdav: 'webdav',
    ftp: 'ftp',
    sftp: 'sftp',
  };

  const processConfigValue = (
    key: string,
    value: string | number | boolean | Record<string, unknown> | undefined
  ): string | number | boolean | Record<string, unknown> | undefined => {
    if (typeof value !== 'string') return value;
    if (!(key === 'token' || key.endsWith('_token'))) return value;
    if (!value.startsWith('{')) return value;

    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  };

  // Map rclone config to our storage provider format
  const mapRcloneToStorageProvider = (
    rcloneConfig: RcloneConfig
  ): Record<string, unknown> | null => {
    const { type, config } = rcloneConfig;
    const provider = PROVIDER_MAPPING[type];
    if (!provider) return null;

    const storageVault: Record<string, unknown> = { provider };

    Object.entries(config).forEach(([key, value]) => {
      if (key === 'type') return; // Skip 'type', we use 'provider' instead
      storageVault[key] = processConfigValue(key, value);
    });

    return storageVault;
  };

  const handleFileUpload = async (file: File) => {
    setParsingError(null);

    try {
      const content = await file.text();
      const configs = parseRcloneConfig(content);

      if (configs.length === 0) {
        setParsingError(t('resources:storage.import.noConfigsFound'));
        return false;
      }

      setParsedConfigs(configs);

      // Initialize import statuses
      const statuses: ImportStatus[] = configs.map((config) => {
        const exists = existingStorages.some((s) => s.storageName === config.name);
        return {
          name: config.name,
          status: 'pending',
          exists,
          selected: !exists, // Only select non-existing by default
        };
      });
      setImportStatuses(statuses);

      setCurrentStep(1);
      return false;
    } catch {
      setParsingError(t('resources:storage.import.parseError'));
      return false;
    }
  };

  const handleImport = async () => {
    setIsImporting(true);
    const selectedConfigs = parsedConfigs.filter((_, index) => importStatuses[index].selected);

    for (const config of selectedConfigs) {
      const statusIndex = parsedConfigs.findIndex((c) => c.name === config.name);

      try {
        const mappedConfig = mapRcloneToStorageProvider(config);
        if (!mappedConfig) {
          setImportStatuses((prev) => {
            const newStatuses = [...prev];
            newStatuses[statusIndex] = {
              ...newStatuses[statusIndex],
              status: 'error',
              message: t('resources:storage.import.unsupportedProvider', { type: config.type }),
            };
            return newStatuses;
          });
          continue;
        }

        // Create storage vault content
        const storageVault = JSON.stringify(mappedConfig);

        await createStorageMutation.mutateAsync({
          teamName,
          storageName: config.name,
          vaultContent: storageVault,
        });

        setImportStatuses((prev) => {
          const newStatuses = [...prev];
          newStatuses[statusIndex] = {
            ...newStatuses[statusIndex],
            status: 'success',
            message: t('resources:storage.import.imported'),
          };
          return newStatuses;
        });
      } catch (error: unknown) {
        const errorMessage =
          error instanceof Error ? error.message : t('resources:storage.import.importError');
        setImportStatuses((prev) => {
          const newStatuses = [...prev];
          newStatuses[statusIndex] = {
            ...newStatuses[statusIndex],
            status: 'error',
            message: errorMessage,
          };
          return newStatuses;
        });
      }
    }

    setIsImporting(false);
    setCurrentStep(2);
  };

  const handleClose = () => {
    // Reset state
    setCurrentStep(0);
    setFileList([]);
    setParsedConfigs([]);
    setImportStatuses([]);
    setIsImporting(false);
    setParsingError(null);

    // Call callbacks
    if (currentStep === 2 && importStatuses.some((s) => s.status === 'success')) {
      onImportComplete?.();
    }
    onClose();
  };

  const toggleSelection = (index: number) => {
    setImportStatuses((prev) => {
      const newStatuses = [...prev];
      newStatuses[index] = {
        ...newStatuses[index],
        selected: !newStatuses[index].selected,
      };
      return newStatuses;
    });
  };

  const selectAll = (selected: boolean) => {
    setImportStatuses((prev) => prev.map((status) => ({ ...status, selected })));
  };

  const nameColumn = createTruncatedColumn<ImportStatus>({
    title: t('resources:storage.storageName'),
    dataIndex: 'name',
    key: 'name',
    sorter: createSorter<ImportStatus>('name'),
  });

  const statusColumn = createStatusColumn<ImportStatus>({
    title: t('resources:storage.import.status'),
    dataIndex: 'status',
    key: 'status',
    statusMap: {
      pending: {
        icon: <ClockCircleOutlined />,
        label: t('resources:storage.import.pending'),
      },
      success: {
        icon: <CheckCircleOutlined />,
        label: t('resources:storage.import.success'),
      },
      error: {
        icon: <CloseCircleOutlined />,
        label: t('resources:storage.import.error'),
      },
      skipped: {
        icon: <WarningOutlined />,
        label: t('resources:storage.import.skipped'),
      },
    },
  });

  const columns: ColumnsType<ImportStatus> = [
    {
      title: (
        <Checkbox
          checked={importStatuses.every((s) => s.selected)}
          indeterminate={
            importStatuses.some((s) => s.selected) && !importStatuses.every((s) => s.selected)
          }
          onChange={(e) => selectAll(e.target.checked)}
          disabled={currentStep === 2}
          data-testid="rclone-wizard-select-all-checkbox"
        />
      ),
      dataIndex: 'selected',
      key: 'selected',
      width: 50,
      render: (_: unknown, record: ImportStatus, index: number) => (
        <Checkbox
          checked={record.selected}
          onChange={() => toggleSelection(index)}
          disabled={currentStep === 2}
          data-testid={`rclone-wizard-config-checkbox-${record.name}`}
        />
      ),
    },
    {
      ...nameColumn,
      render: (name: string, record: ImportStatus) => {
        const truncated = nameColumn.render?.(name, record, 0) as React.ReactNode;
        return (
          <Space>
            <CloudOutlined />
            <Typography.Text>{truncated}</Typography.Text>
            {record.exists && (
              <Tooltip title={t('resources:storage.import.alreadyExists')}>
                <Tag>
                  <InfoCircleOutlined /> {t('resources:storage.import.exists')}
                </Tag>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: t('resources:storage.provider'),
      key: 'provider',
      width: 120,
      responsive: RESPONSIVE_HIDE_XS,
      render: (_: unknown, record: ImportStatus) => {
        const config = parsedConfigs.find((c) => c.name === record.name);
        if (!config) return null;

        // Capitalize provider name for display
        const displayName = config.type.charAt(0).toUpperCase() + config.type.slice(1);
        return <Tag>{displayName}</Tag>;
      },
    },
    {
      ...statusColumn,
      render: (status: ImportStatus['status'], record) => {
        if (currentStep < 2) return null;
        return (
          <Space direction="vertical" size={8}>
            {statusColumn.render?.(status, record, 0) as React.ReactNode}
            {record.message && <Typography.Text>{record.message}</Typography.Text>}
          </Space>
        );
      },
    },
  ];

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <StepConfigForm
            t={t}
            fileList={fileList}
            parsingError={parsingError}
            onBeforeUpload={handleFileUpload}
            onFileListChange={setFileList}
          />
        );
      case 1:
        return <ConnectionTest t={t} importStatuses={importStatuses} columns={columns} />;
      case 2:
        return (
          <ImportProgress
            t={t}
            importStatuses={importStatuses}
            columns={columns}
            isImporting={isImporting}
          />
        );
      default:
        return null;
    }
  };

  return (
    <Modal
      title={
        <Space>
          <CloudOutlined />
          {t('resources:storage.import.title')}
        </Space>
      }
      width={960}
      open={open}
      onCancel={handleClose}
      data-testid="rclone-import-wizard-modal"
      footer={(() => {
        if (currentStep === 0) {
          return (
            <Button onClick={handleClose} data-testid="rclone-wizard-cancel-button">
              {t('common:actions.cancel')}
            </Button>
          );
        } else if (currentStep === 1) {
          return (
            <>
              <Button onClick={() => setCurrentStep(0)} data-testid="rclone-wizard-back-button">
                {t('common:actions.back')}
              </Button>
              <Button onClick={handleClose} data-testid="rclone-wizard-cancel-button">
                {t('common:actions.cancel')}
              </Button>
              <Button
                type="primary"
                onClick={handleImport}
                disabled={!importStatuses.some((s) => s.selected)}
                loading={isImporting}
                data-testid="rclone-wizard-import-button"
              >
                {t('resources:storage.import.importSelected')}
              </Button>
            </>
          );
        }
        return (
          <Button type="primary" onClick={handleClose} data-testid="rclone-wizard-close-button">
            {t('common:actions.close')}
          </Button>
        );
      })()}
      centered
    >
      <Flex vertical>
        <Steps
          current={currentStep}
          data-testid="rclone-wizard-steps"
          items={[
            { title: t('resources:storage.import.step1') },
            { title: t('resources:storage.import.step2') },
            { title: t('resources:storage.import.step3') },
          ]}
        />
      </Flex>

      {renderStepContent()}
    </Modal>
  );
};

export default RcloneImportWizard;
