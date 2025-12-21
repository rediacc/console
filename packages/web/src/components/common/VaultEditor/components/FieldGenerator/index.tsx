import React, { useState } from 'react';
import { Button, Flex, Popover, Radio, Tooltip, Typography, type RadioChangeEvent } from 'antd';
import { useTranslation } from 'react-i18next';
import { useMessage } from '@/hooks';
import {
  GenerationOptions,
  generateRepoCredential,
  generateSSHKeyPair,
} from '@/utils/cryptoGenerators';
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
    comment: `${entityType || 'generated'}-${new Date().toISOString().split('T')[0]}`,
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

  const keyTypeOptions: ReadonlyArray<{
    value: 'rsa' | 'ed25519';
    label: string;
    disabled?: boolean;
  }> = [
    { value: 'rsa', label: 'RSA' },
    { value: 'ed25519', label: `Ed25519 ${t('fieldGenerator.comingSoon')}`, disabled: true },
  ];

  const keySizeOptions: ReadonlyArray<{ value: 2048 | 4096; label: string; disabled?: boolean }> = [
    { value: 2048, label: '2048 bits' },
    { value: 4096, label: `4096 bits (${t('fieldGenerator.moreSecure')})` },
  ];

  const renderRadioGroup = <T extends string | number>(
    label: string,
    value: T,
    options: ReadonlyArray<{ value: T; label: string; disabled?: boolean }>,
    onChange: (val: T) => void
  ) => (
    <div>
      <label style={{ fontWeight: 500, fontSize: 14, display: 'block' }}>{label}</label>
      <Radio.Group
        style={{ display: 'block' }}
        value={value}
        onChange={(e: RadioChangeEvent) => onChange(e.target.value as T)}
        data-testid={`vault-editor-radio-${label.toLowerCase().replace(/\s+/g, '-')}`}
      >
        {options.map((opt) => (
          <Radio.Button
            style={{ display: 'block', fontSize: 14 }}
            key={opt.value}
            value={opt.value}
            disabled={opt.disabled}
            data-testid={`vault-editor-radio-option-${opt.value}`}
          >
            {opt.label}
          </Radio.Button>
        ))}
      </Radio.Group>
    </div>
  );

  const currentKeyType: 'rsa' | 'ed25519' = keyOptions.keyType ?? 'rsa';
  const currentKeySize: 2048 | 4096 = keyOptions.keySize ?? 2048;

  const renderSSHKeyOptions = () => (
    <Flex vertical style={{ width: '100%' }}>
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
    <Flex vertical style={{ width: '100%' }}>
      {Object.entries(generatedValues).map(([field, value]) => (
        <div key={field} style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontWeight: 500,
            }}
          >
            <Typography.Text strong>{field}:</Typography.Text>
            <Button
              icon={
                copiedField === field ? (
                  <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center' }}>
                    <CheckOutlined />
                  </span>
                ) : (
                  <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center' }}>
                    <CopyOutlined />
                  </span>
                )
              }
              onClick={() => handleCopy(field, value)}
              data-testid={`vault-editor-copy-${field.toLowerCase()}`}
            >
              {copiedField === field ? t('fieldGenerator.copied') : t('fieldGenerator.copy')}
            </Button>
          </div>
          <div
            style={{
              wordBreak: 'break-all',
              maxHeight: 200,
              overflow: 'auto',
              fontSize: 12,
              lineHeight: 1.4,
            }}
          >
            {value}
          </div>
        </div>
      ))}
    </Flex>
  );

  const popoverContent = (
    <div style={{ width: 320, maxWidth: '100%' }}>
      {fieldType === 'ssh_keys' && !Object.keys(generatedValues).length && renderSSHKeyOptions()}

      {Object.keys(generatedValues).length > 0 && renderGeneratedValues()}

      <Flex justify="flex-end" style={{ width: '100%' }}>
        {Object.keys(generatedValues).length === 0 ? (
          <Button
            type="primary"
            icon={
              <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center' }}>
                <KeyOutlined />
              </span>
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
                <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center' }}>
                  <ReloadOutlined />
                </span>
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
    </div>
  );

  return (
    <Popover
      content={popoverContent}
      title={
        <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
          <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center' }}>
            <KeyOutlined />
          </span>
          <span>{t(`fieldGenerator.title.${fieldType}`)}</span>
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
            <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center' }}>
              <KeyOutlined />
            </span>
          }
          aria-label={t('fieldGenerator.tooltip')}
          data-testid={props['data-testid'] || 'vault-editor-field-generator'}
        />
      </Tooltip>
    </Popover>
  );
};

export default FieldGenerator;
