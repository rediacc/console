import React, { useState } from 'react';
import { Steps, Upload, Button, Table, Space, Typography, Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useCreateStorage } from '@/api/queries/storage';
import { useStorage } from '@/api/queries/storage';
import { createStatusColumn, createTruncatedColumn } from '@/components/common/columns';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccCheckbox, RediaccAlert } from '@/components/ui';
import { createSorter } from '@/platform';
import {
  CloudOutlined,
  InfoCircleOutlined,
  UploadOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import {
  WizardModal,
  UploadStepWrapper,
  StepsContainer,
  LoadingState,
  StatusMessage,
} from './styles';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload';
import type { TFunction } from 'i18next';

const { Text, Paragraph } = Typography;

type RcloneConfigFields = {
  [key: string]: string | number | boolean | Record<string, unknown> | undefined;
  type?: string;
};

interface RcloneConfig {
  name: string;
  type: string;
  config: RcloneConfigFields;
}

interface ImportStatus {
  name: string;
  status: 'pending' | 'success' | 'error' | 'skipped';
  message?: string;
  exists?: boolean;
  selected?: boolean;
}

interface RcloneImportWizardProps {
  open: boolean;
  onClose: () => void;
  teamName: string;
  onImportComplete?: () => void;
}

type WizardTranslator = TFunction<'resources' | 'common'>;

interface UploadStepProps {
  t: WizardTranslator;
  fileList: UploadFile[];
  parsingError: string | null;
  onBeforeUpload: (file: File) => Promise<boolean>;
  onFileListChange: (files: UploadFile[]) => void;
}

const UploadStep: React.FC<UploadStepProps> = ({
  t,
  fileList,
  parsingError,
  onBeforeUpload,
  onFileListChange,
}) => (
  <UploadStepWrapper>
    <RediaccAlert
      spacing="spacious"
      message={t('resources:storage.import.instructions')}
      description={
        <div>
          <Paragraph>{t('resources:storage.import.instructionsDetail')}</Paragraph>
          <Paragraph>
            <Text code>rclone config file</Text>
          </Paragraph>
          <Paragraph>{t('resources:storage.import.uploadPrompt')}</Paragraph>
        </div>
      }
      variant="info"
      showIcon
      icon={<InfoCircleOutlined />}
    />

    <Upload.Dragger
      accept=".conf"
      fileList={fileList}
      beforeUpload={onBeforeUpload}
      onChange={({ fileList }) => onFileListChange(fileList)}
      maxCount={1}
      data-testid="rclone-wizard-upload-dragger"
    >
      <p className="ant-upload-drag-icon">
        <UploadOutlined />
      </p>
      <p className="ant-upload-text">{t('resources:storage.import.dragDropText')}</p>
      <p className="ant-upload-hint">{t('resources:storage.import.supportedFormats')}</p>
    </Upload.Dragger>

    {parsingError && (
      <RediaccAlert message={parsingError} variant="error" showIcon style={{ marginTop: '16px' }} />
    )}
  </UploadStepWrapper>
);

interface SelectionStepProps {
  t: WizardTranslator;
  importStatuses: ImportStatus[];
  columns: ColumnsType<ImportStatus>;
}

const SelectionStep: React.FC<SelectionStepProps> = ({ t, importStatuses, columns }) => (
  <div>
    <RediaccAlert
      spacing="default"
      message={t('resources:storage.import.selectStorages')}
      description={t('resources:storage.import.selectDescription')}
      variant="info"
      showIcon
    />

    <Table
      dataSource={importStatuses}
      columns={columns}
      rowKey="name"
      pagination={false}
      size="small"
      data-testid="rclone-wizard-config-table"
    />
  </div>
);

interface ResultStepProps {
  t: WizardTranslator;
  importStatuses: ImportStatus[];
  columns: ColumnsType<ImportStatus>;
  isImporting: boolean;
}

const ResultStep: React.FC<ResultStepProps> = ({ t, importStatuses, columns, isImporting }) => (
  <div>
    {isImporting ? (
      <LoadingState>
        <LoadingWrapper
          loading
          centered
          minHeight={160}
          tip={t('resources:storage.import.importing') as string}
        >
          <div />
        </LoadingWrapper>
      </LoadingState>
    ) : (
      <>
        <RediaccAlert
          spacing="default"
          message={t('resources:storage.import.complete')}
          description={t('resources:storage.import.completeDescription')}
          variant="success"
          showIcon
        />

        <Table
          dataSource={importStatuses}
          columns={columns}
          rowKey="name"
          pagination={false}
          size="small"
          data-testid="rclone-wizard-results-table"
        />
      </>
    )}
  </div>
);

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
  const { data: existingStorages = [] } = useStorage(teamName);

  // Parse INI-style rclone config
  const parseRcloneConfig = (content: string): RcloneConfig[] => {
    const configs: RcloneConfig[] = [];
    const lines = content.split('\n');
    let currentSection: string | null = null;
    let currentConfig: RcloneConfigFields = {};

    for (const line of lines) {
      const trimmedLine = line.trim();

      // Skip empty lines and comments
      if (!trimmedLine || trimmedLine.startsWith('#') || trimmedLine.startsWith(';')) {
        continue;
      }

      // Check if it's a section header
      const sectionMatch = trimmedLine.match(/^\[(.+)\]$/);
      if (sectionMatch) {
        // Save previous section if exists
        if (currentSection && currentConfig.type) {
          configs.push({
            name: currentSection,
            type: currentConfig.type,
            config: { ...currentConfig },
          });
        }

        // Start new section
        currentSection = sectionMatch[1];
        currentConfig = {};
      } else if (currentSection) {
        // Parse key-value pair
        const kvMatch = trimmedLine.match(/^([^=]+)=(.*)$/);
        if (kvMatch) {
          const key = kvMatch[1].trim();
          const value = kvMatch[2].trim();

          // Try to parse JSON values (for complex objects like tokens)
          try {
            currentConfig[key] = JSON.parse(value) as Record<string, unknown>;
          } catch {
            // If not JSON, store as string
            currentConfig[key] = value;
          }
        }
      }
    }

    // Don't forget the last section
    if (currentSection && currentConfig.type) {
      configs.push({
        name: currentSection,
        type: currentConfig.type,
        config: { ...currentConfig },
      });
    }

    return configs;
  };

  // Map rclone config to our storage provider format
  const mapRcloneToStorageProvider = (
    rcloneConfig: RcloneConfig
  ): Record<string, unknown> | null => {
    const { type, config } = rcloneConfig;

    // Map rclone type to our provider type
    const providerMapping: Record<string, string> = {
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

    const provider = providerMapping[type];
    if (!provider) {
      return null;
    }

    // Storage vault should contain all fields directly at top level
    // matching the format used in data.json
    const storageVault: Record<string, unknown> = {};

    // Process all config fields
    Object.entries(config).forEach(([key, value]) => {
      if (key === 'type') {
        // Replace 'type' with 'provider' for our system
        storageVault.provider = provider;
      } else {
        // Parse JSON strings if needed
        let processedValue: string | number | boolean | Record<string, unknown> | undefined = value;
        if (typeof value === 'string') {
          // Check if it's a JSON string that needs to be parsed
          if ((key === 'token' || key.endsWith('_token')) && value.startsWith('{')) {
            try {
              processedValue = JSON.parse(value);
            } catch {
              processedValue = value;
            }
          }
        }

        // Add field directly to vault
        storageVault[key] = processedValue;
      }
    });

    // Ensure provider is set if not already
    if (!storageVault.provider) {
      storageVault.provider = provider;
    }

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

    for (let i = 0; i < selectedConfigs.length; i++) {
      const config = selectedConfigs[i];
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
        color: 'default',
      },
      success: {
        icon: <CheckCircleOutlined />,
        label: t('resources:storage.import.success'),
        color: 'success',
      },
      error: {
        icon: <CloseCircleOutlined />,
        label: t('resources:storage.import.error'),
        color: 'error',
      },
      skipped: {
        icon: <WarningOutlined />,
        label: t('resources:storage.import.skipped'),
        color: 'warning',
      },
    },
  });

  const columns: ColumnsType<ImportStatus> = [
    {
      title: (
        <RediaccCheckbox
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
        <RediaccCheckbox
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
            <span style={{ fontWeight: 600 }}>{truncated}</span>
            {record.exists && (
              <Tooltip title={t('resources:storage.import.alreadyExists')}>
                <Tag color="warning">
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
      render: (_: unknown, record: ImportStatus) => {
        const config = parsedConfigs.find((c) => c.name === record.name);
        if (!config) return null;

        // Capitalize provider name for display
        const displayName = config.type.charAt(0).toUpperCase() + config.type.slice(1);
        return <Tag color="blue">{displayName}</Tag>;
      },
    },
    {
      ...statusColumn,
      render: (status: ImportStatus['status'], record) => {
        if (currentStep < 2) return null;
        return (
          <Space direction="vertical" size={8}>
            {statusColumn.render?.(status, record, 0) as React.ReactNode}
            {record.message && <StatusMessage>{record.message}</StatusMessage>}
          </Space>
        );
      },
    },
  ];

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <UploadStep
            t={t}
            fileList={fileList}
            parsingError={parsingError}
            onBeforeUpload={handleFileUpload}
            onFileListChange={setFileList}
          />
        );
      case 1:
        return <SelectionStep t={t} importStatuses={importStatuses} columns={columns} />;
      case 2:
        return (
          <ResultStep
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
    <WizardModal
      title={
        <Space>
          <CloudOutlined />
          {t('resources:storage.import.title')}
        </Space>
      }
      open={open}
      onCancel={handleClose}
      footer={
        currentStep === 0 ? (
          <Button onClick={handleClose} data-testid="rclone-wizard-cancel-button">
            {t('common:actions.cancel')}
          </Button>
        ) : currentStep === 1 ? (
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
        ) : (
          <Button type="primary" onClick={handleClose} data-testid="rclone-wizard-close-button">
            {t('common:actions.close')}
          </Button>
        )
      }
    >
      <StepsContainer>
        <Steps
          current={currentStep}
          data-testid="rclone-wizard-steps"
          items={[
            { title: t('resources:storage.import.step1') },
            { title: t('resources:storage.import.step2') },
            { title: t('resources:storage.import.step3') },
          ]}
        />
      </StepsContainer>

      {renderStepContent()}
    </WizardModal>
  );
};

export default RcloneImportWizard;
