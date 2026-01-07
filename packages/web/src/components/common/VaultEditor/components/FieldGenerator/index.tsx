import React, { useState } from 'react';
import { Button, Flex, Popover, Radio, Tooltip, Typography, type RadioChangeEvent } from 'antd';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks';
import { GenerationOptions, generateRepoCredential, generateSSHKeyPair } from '@/utils/generators';
import { CheckOutlined, CopyOutlined, KeyOutlined, ReloadOutlined } from '@/utils/optimizedIcons';

interface FieldGeneratorProps {
  fieldType: 'ssh_keys' | 'repo_credential';
  onGenerate: (values: Record<string, string>) => void;
  entityType?: string;
  'data-testid'?: string;
}

const FieldGenerator: React.FC<FieldGeneratorProps> = (props) => {
  const { fieldType, onGenerate, entityType } = props;
  const { t } = useTranslation('common');
  const message = useMessage();
  const [visible, setVisible] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatedValues, setGeneratedValues] = useState<Record<string, string>>({});
  const [keyOptions, setKeyOptions] = useState<GenerationOptions>({
    keyType: 'rsa',
    keySize: 2048,
    comment: `${entityType ?? 'generated'}-${new Date().toISOString().split('T')[0]}`,
  });
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const generators = {
    ssh_keys: async () => {
      const keys = await generateSSHKeyPair(keyOptions);
      return { SSH_PRIVATE_KEY: keys.privateKey, SSH_PUBLIC_KEY: keys.publicKey };
    },
    repo_credential: () => ({ credential: generateRepoCredential() }),
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const values = await generators[fieldType]();
      setGeneratedValues(values);
      message.success('common:fieldGenerator.generationSuccess');
    } catch {
      message.error('common:fieldGenerator.generationError');
    } finally {
      setGenerating(false);
    }
  };

  const handleApply = () => {
    onGenerate(generatedValues);
    setVisible(false);
    setGeneratedValues({});
    message.success('common:fieldGenerator.applied');
  };

  const handleCopy = (field: string, value: string) => {
    navigator.clipboard
      .writeText(value)
      .then(() => {
        setCopiedField(field);
        message.success('common:fieldGenerator.copied');
        // Reset copy state after delay to show visual feedback
        setTimeout(() => setCopiedField(null), 2000);
      })
      .catch(() => message.error('common:fieldGenerator.copyError'));
  };

  const keyTypeOptions: readonly {
    value: 'rsa' | 'ed25519';
    label: string;
    disabled?: boolean;
  }[] = [
    { value: 'rsa', label: 'RSA' },
    { value: 'ed25519', label: `Ed25519 ${t('fieldGenerator.comingSoon')}`, disabled: true },
  ];

  const keySizeOptions: readonly { value: 2048 | 4096; label: string; disabled?: boolean }[] = [
    { value: 2048, label: '2048 bits' },
    { value: 4096, label: `4096 bits (${t('fieldGenerator.moreSecure')})` },
  ];

  const renderRadioGroup = <T extends string | number>(
    label: string,
    value: T,
    options: readonly { value: T; label: string; disabled?: boolean }[],
    onChange: (val: T) => void
  ) => (
    <Flex vertical>
      <Typography.Text className="block font-medium text-sm">{label}</Typography.Text>
      <Radio.Group
        className="block"
        value={value}
        onChange={(e: RadioChangeEvent) => onChange(e.target.value as T)}
        data-testid={`vault-editor-radio-${label.toLowerCase().replace(/\s+/g, '-')}`}
      >
        {options.map((opt) => (
          <Radio.Button
            className="block text-sm"
            key={opt.value}
            value={opt.value}
            disabled={opt.disabled}
            data-testid={`vault-editor-radio-option-${opt.value}`}
          >
            {opt.label}
          </Radio.Button>
        ))}
      </Radio.Group>
    </Flex>
  );

  const currentKeyType: 'rsa' | 'ed25519' = keyOptions.keyType ?? 'rsa';
  const currentKeySize: 2048 | 4096 = keyOptions.keySize ?? 2048;

  const renderSSHKeyOptions = () => (
    <Flex vertical className="w-full">
      {renderRadioGroup(t('fieldGenerator.keyType'), currentKeyType, keyTypeOptions, (val) =>
        setKeyOptions({ ...keyOptions, keyType: val })
      )}
      {currentKeyType === 'rsa' &&
        renderRadioGroup(t('fieldGenerator.keySize'), currentKeySize, keySizeOptions, (val) =>
          setKeyOptions({ ...keyOptions, keySize: val })
        )}
    </Flex>
  );

  const renderGeneratedValues = () => (
    <Flex vertical className="w-full">
      {Object.entries(generatedValues).map(([field, value]) => (
        <Flex key={field} vertical>
          <Flex justify="space-between" align="center" className="font-medium">
            <Typography.Text strong>{field}:</Typography.Text>
            <Button
              icon={
                copiedField === field ? (
                  <Typography.Text className="inline-flex items-center text-xs">
                    <CheckOutlined />
                  </Typography.Text>
                ) : (
                  <Typography.Text className="inline-flex items-center text-xs">
                    <CopyOutlined />
                  </Typography.Text>
                )
              }
              onClick={() => handleCopy(field, value)}
              data-testid={`vault-editor-copy-${field.toLowerCase()}`}
            >
              {copiedField === field ? t('fieldGenerator.copied') : t('fieldGenerator.copy')}
            </Button>
          </Flex>
          <Flex className="overflow-auto break-all max-h-200 text-xs line-height-normal">
            {value}
          </Flex>
        </Flex>
      ))}
    </Flex>
  );

  const popoverContent = (
    <Flex vertical className="max-w-full w-320">
      {fieldType === 'ssh_keys' && !Object.keys(generatedValues).length && renderSSHKeyOptions()}

      {Object.keys(generatedValues).length > 0 && renderGeneratedValues()}

      <Flex justify="flex-end" className="w-full">
        {Object.keys(generatedValues).length === 0 ? (
          <Button
            type="primary"
            icon={
              <Typography.Text className="inline-flex items-center text-xs">
                <KeyOutlined />
              </Typography.Text>
            }
            onClick={handleGenerate}
            loading={generating}
            data-testid="vault-editor-generate-button"
          >
            {t('fieldGenerator.generate')}
          </Button>
        ) : (
          <>
            <Button
              onClick={() => setGeneratedValues({})}
              data-testid="vault-editor-generate-cancel"
            >
              {t('fieldGenerator.cancel')}
            </Button>
            <Button
              icon={
                <Typography.Text className="inline-flex items-center text-xs">
                  <ReloadOutlined />
                </Typography.Text>
              }
              onClick={handleGenerate}
              loading={generating}
              data-testid="vault-editor-regenerate-button"
            >
              {t('fieldGenerator.regenerate')}
            </Button>
            <Button type="primary" onClick={handleApply} data-testid="vault-editor-apply-generated">
              {t('fieldGenerator.apply')}
            </Button>
          </>
        )}
      </Flex>
    </Flex>
  );

  return (
    <Popover
      content={popoverContent}
      title={
        <Flex align="center" wrap className="inline-flex">
          <Typography.Text className="inline-flex items-center text-xs">
            <KeyOutlined />
          </Typography.Text>
          <Typography.Text>{t(`fieldGenerator.title.${fieldType}`)}</Typography.Text>
        </Flex>
      }
      trigger="click"
      open={visible}
      onOpenChange={setVisible}
      placement="left"
    >
      <Tooltip title={t('fieldGenerator.tooltip')}>
        <Button
          type="text"
          icon={
            <Typography.Text className="inline-flex items-center text-xs">
              <KeyOutlined />
            </Typography.Text>
          }
          aria-label={t('fieldGenerator.tooltip')}
          data-testid={props['data-testid'] ?? 'vault-editor-field-generator'}
        />
      </Tooltip>
    </Popover>
  );
};

export default FieldGenerator;
