import React, { useState } from 'react';
import { Popover } from 'antd';
import { useTranslation } from 'react-i18next';
import { InlineStack } from '@/components/common/styled';
import { RediaccStack, RediaccText, RediaccTooltip } from '@/components/ui';
import { useMessage } from '@/hooks';
import {
  GenerationOptions,
  generateRepoCredential,
  generateSSHKeyPair,
} from '@/utils/cryptoGenerators';
import { CheckOutlined, CopyOutlined, KeyOutlined, ReloadOutlined } from '@/utils/optimizedIcons';
import {
  ActionStack,
  ControlButton,
  CopyButton,
  GeneratedValueCard,
  GeneratorButton,
  OptionGroup,
  OptionLabel,
  OptionRadio,
  PopoverContainer,
  SmallIcon,
  ValueContent,
  ValueHeader,
} from './styles';

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
        // Reset copy state immediately after user interaction
        setCopiedField(null);
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
      <OptionLabel>{label}</OptionLabel>
      <OptionGroup
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        data-testid={`vault-editor-radio-${label.toLowerCase().replace(/\s+/g, '-')}`}
      >
        {options.map((opt) => (
          <OptionRadio
            key={opt.value}
            value={opt.value}
            disabled={opt.disabled}
            data-testid={`vault-editor-radio-option-${opt.value}`}
          >
            {opt.label}
          </OptionRadio>
        ))}
      </OptionGroup>
    </div>
  );

  const currentKeyType: 'rsa' | 'ed25519' = keyOptions.keyType ?? 'rsa';
  const currentKeySize: 2048 | 4096 = keyOptions.keySize ?? 2048;

  const renderSSHKeyOptions = () => (
    <RediaccStack direction="vertical" fullWidth>
      {renderRadioGroup(t('fieldGenerator.keyType'), currentKeyType, keyTypeOptions, (val) =>
        setKeyOptions({ ...keyOptions, keyType: val })
      )}
      {currentKeyType === 'rsa' &&
        renderRadioGroup(t('fieldGenerator.keySize'), currentKeySize, keySizeOptions, (val) =>
          setKeyOptions({ ...keyOptions, keySize: val })
        )}
    </RediaccStack>
  );

  const renderGeneratedValues = () => (
    <RediaccStack direction="vertical" fullWidth>
      {Object.entries(generatedValues).map(([field, value]) => (
        <GeneratedValueCard key={field}>
          <ValueHeader>
            <RediaccText weight="bold">{field}:</RediaccText>
            <CopyButton
              icon={
                copiedField === field ? (
                  <SmallIcon>
                    <CheckOutlined />
                  </SmallIcon>
                ) : (
                  <SmallIcon>
                    <CopyOutlined />
                  </SmallIcon>
                )
              }
              onClick={() => handleCopy(field, value)}
              data-testid={`vault-editor-copy-${field.toLowerCase()}`}
            >
              {copiedField === field ? t('fieldGenerator.copied') : t('fieldGenerator.copy')}
            </CopyButton>
          </ValueHeader>
          <ValueContent>{value}</ValueContent>
        </GeneratedValueCard>
      ))}
    </RediaccStack>
  );

  const popoverContent = (
    <PopoverContainer>
      {fieldType === 'ssh_keys' && !Object.keys(generatedValues).length && renderSSHKeyOptions()}

      {Object.keys(generatedValues).length > 0 && renderGeneratedValues()}

      <ActionStack direction="horizontal" justify="end" fullWidth>
        {Object.keys(generatedValues).length === 0 ? (
          <ControlButton
            variant="primary"
            icon={
              <SmallIcon>
                <KeyOutlined />
              </SmallIcon>
            }
            onClick={handleGenerate}
            loading={generating}
            data-testid="vault-editor-generate-button"
          >
            {t('fieldGenerator.generate')}
          </ControlButton>
        ) : (
          <>
            <ControlButton
              onClick={() => setGeneratedValues({})}
              data-testid="vault-editor-generate-cancel"
            >
              {t('fieldGenerator.cancel')}
            </ControlButton>
            <ControlButton
              icon={
                <SmallIcon>
                  <ReloadOutlined />
                </SmallIcon>
              }
              onClick={handleGenerate}
              loading={generating}
              data-testid="vault-editor-regenerate-button"
            >
              {t('fieldGenerator.regenerate')}
            </ControlButton>
            <ControlButton
              variant="primary"
              onClick={handleApply}
              data-testid="vault-editor-apply-generated"
            >
              {t('fieldGenerator.apply')}
            </ControlButton>
          </>
        )}
      </ActionStack>
    </PopoverContainer>
  );

  return (
    <Popover
      content={popoverContent}
      title={
        <InlineStack>
          <SmallIcon>
            <KeyOutlined />
          </SmallIcon>
          <span>{t(`fieldGenerator.title.${fieldType}`)}</span>
        </InlineStack>
      }
      trigger="click"
      open={visible}
      onOpenChange={setVisible}
      placement="left"
    >
      <RediaccTooltip title={t('fieldGenerator.tooltip')}>
        <GeneratorButton
          variant="text"
          icon={
            <SmallIcon>
              <KeyOutlined />
            </SmallIcon>
          }
          data-testid={props['data-testid'] || 'vault-editor-field-generator'}
        />
      </RediaccTooltip>
    </Popover>
  );
};

export default FieldGenerator;
