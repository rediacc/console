import React, { useEffect, useState } from 'react';
import { Input, Popconfirm, Empty, Row, Col } from 'antd';
import { useTranslation } from 'react-i18next';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import { RediaccSwitch, RediaccText } from '@/components/ui';
import {
  PlusOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  CodeOutlined,
} from '@/utils/optimizedIcons';
import {
  EditorContainer,
  SummaryCard,
  SummaryBadgeRow,
  UniformTag,
  EditorStack,
  AddEntryCard,
  EntryActionsRow,
  KeyInputWrapper,
  KeyInput,
  PrimaryActionButton,
  SecondaryActionButton,
  CollapseWrapper,
  EntryHeader,
  KeyTag,
  TypeTag,
  PanelActions,
  PanelDeleteButton,
  RawJsonCard,
  InlineFormItem,
  ImagePatternCard,
  NumericInput,
} from './styles';

type NestedEntryValue = unknown;
type NestedRecord = Record<string, NestedEntryValue>;

interface FieldSchema extends Record<string, unknown> {
  type?: string;
  description?: string;
  properties?: Record<string, FieldSchema>;
  additionalProperties?: boolean | FieldSchema;
  default?: NestedEntryValue;
}

interface NestedObjectEditorProps {
  value?: NestedRecord;
  onChange?: (value: NestedRecord) => void;
  fieldDefinition?: FieldSchema;
  readOnly?: boolean;
  title?: string;
  description?: string;
  'data-testid'?: string;
}

interface ObjectEntry {
  key: string;
  value: NestedEntryValue;
  isEditing?: boolean;
}

const isRecordLike = (value: unknown): value is NestedRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const looksLikeImageReference = (value: unknown): value is string =>
  typeof value === 'string' && (value.includes(':') || value.includes('/'));

const detectStructurePattern = (
  obj: NestedRecord
): {
  isUniform: boolean;
  keys?: string[];
  hasImagePattern?: boolean;
} => {
  const entries = Object.entries(obj);
  if (!entries.length) {
    return { isUniform: false };
  }

  const firstValue = entries[0][1];
  if (!isRecordLike(firstValue)) {
    return { isUniform: false };
  }

  const firstKeys = Object.keys(firstValue).sort();
  const isConsistent = entries.every(([, value]) => {
    if (!isRecordLike(value)) {
      return false;
    }
    const keys = Object.keys(value).sort();
    return keys.length === firstKeys.length && keys.every((key, index) => key === firstKeys[index]);
  });

  if (!isConsistent) {
    return { isUniform: false };
  }

  const hasImagePattern =
    firstKeys.includes('image') &&
    entries.some(([, value]) => isRecordLike(value) && looksLikeImageReference(value.image));

  return {
    isUniform: true,
    keys: firstKeys,
    hasImagePattern,
  };
};

export const NestedObjectEditor: React.FC<NestedObjectEditorProps> = ({
  value = {},
  onChange,
  fieldDefinition,
  readOnly = false,
  title,
  description,
  'data-testid': dataTestId,
}) => {
  const { t } = useTranslation('common');
  const [entries, setEntries] = useState<ObjectEntry[]>(() =>
    Object.entries(value).map(([key, val]) => ({
      key,
      value: val,
      isEditing: false,
    }))
  );
  const [newKey, setNewKey] = useState('');
  const [showRawJson, setShowRawJson] = useState(false);
  const [rawJsonValue, setRawJsonValue] = useState(() => JSON.stringify(value, null, 2));
  const [rawJsonError, setRawJsonError] = useState<string | null>(null);
  const [structureInfo, setStructureInfo] = useState<ReturnType<typeof detectStructurePattern>>(
    () => detectStructurePattern(value)
  );

  useEffect(() => {
    const entriesArray = Object.entries(value).map(([key, val]) => ({
      key,
      value: val,
      isEditing: false,
    }));
    setEntries(entriesArray);
    setRawJsonValue(JSON.stringify(value, null, 2));
    setStructureInfo(detectStructurePattern(value));
  }, [value]);

  const updateValue = (newEntries: ObjectEntry[]) => {
    const newValue = newEntries.reduce<NestedRecord>((acc, entry) => {
      acc[entry.key] = entry.value;
      return acc;
    }, {});

    setEntries(newEntries);
    setRawJsonValue(JSON.stringify(newValue, null, 2));
    onChange?.(newValue);
  };

  const handleAddEntry = () => {
    if (!newKey.trim()) {
      return;
    }

    if (entries.some((entry) => entry.key === newKey)) {
      return;
    }

    let defaultValue: NestedEntryValue = '';

    if (structureInfo.isUniform && structureInfo.keys && entries.length > 0) {
      const firstEntry = entries[0]?.value;
      if (isRecordLike(firstEntry)) {
        defaultValue = Object.keys(firstEntry).reduce<NestedRecord>((acc, keyName) => {
          const existingValue = firstEntry[keyName];
          if (keyName === 'active' || keyName === 'enabled') {
            acc[keyName] = true;
          } else if (keyName === 'image' && structureInfo.hasImagePattern) {
            acc[keyName] = '';
          } else if (typeof existingValue === 'boolean') {
            acc[keyName] = false;
          } else if (typeof existingValue === 'number') {
            acc[keyName] = 0;
          } else if (typeof existingValue === 'string') {
            acc[keyName] = '';
          } else if (Array.isArray(existingValue)) {
            acc[keyName] = [];
          } else if (isRecordLike(existingValue)) {
            acc[keyName] = {};
          } else {
            acc[keyName] = '';
          }
          return acc;
        }, {});
      }
    } else if (
      fieldDefinition?.additionalProperties &&
      typeof fieldDefinition.additionalProperties === 'object'
    ) {
      const propDef = fieldDefinition.additionalProperties as FieldSchema;
      if (propDef.type === 'object' && propDef.properties) {
        defaultValue = Object.keys(propDef.properties).reduce<NestedRecord>((acc, keyName) => {
          const schema = propDef.properties?.[keyName];
          if (schema) {
            acc[keyName] =
              schema.default ??
              (schema.type === 'boolean' ? false : schema.type === 'number' ? 0 : '');
          }
          return acc;
        }, {});
      } else if (propDef.type === 'boolean') {
        defaultValue = false;
      } else if (propDef.type === 'number') {
        defaultValue = 0;
      }
    }

    const nextEntries = [...entries, { key: newKey, value: defaultValue, isEditing: true }];
    updateValue(nextEntries);
    setNewKey('');
  };

  const handleDeleteEntry = (index: number) => {
    const filtered = entries.filter((_, i) => i !== index);
    updateValue(filtered);
  };

  const handleUpdateEntry = (index: number, updates: Partial<ObjectEntry>) => {
    const nextEntries = [...entries];
    nextEntries[index] = { ...nextEntries[index], ...updates };
    updateValue(nextEntries);
  };

  const handleRawJsonChange = (jsonString: string) => {
    setRawJsonValue(jsonString);
    try {
      const parsed: unknown = JSON.parse(jsonString);
      if (!isRecordLike(parsed)) {
        throw new Error('Invalid JSON structure');
      }
      setRawJsonError(null);
      onChange?.(parsed);
    } catch (error) {
      setRawJsonError((error as Error).message);
    }
  };

  const renderEntryValue = (entry: ObjectEntry, index: number): React.ReactNode => {
    const entryDef =
      fieldDefinition?.properties?.[entry.key] ?? fieldDefinition?.additionalProperties;
    const nestedDefinition =
      typeof entryDef === 'object' && entryDef ? (entryDef as FieldSchema) : undefined;

    if (isRecordLike(entry.value)) {
      const imageValue = entry.value.image;
      const activeValue = entry.value.active;

      if (
        typeof imageValue === 'string' &&
        typeof activeValue === 'boolean' &&
        (structureInfo.hasImagePattern || looksLikeImageReference(imageValue))
      ) {
        return (
          <ImagePatternCard size="sm">
            <Row gutter={16}>
              <Col span={18}>
                <InlineFormItem
                  label={<RediaccText variant="label">{t('nestedObjectEditor.Image')}</RediaccText>}
                >
                  <Input
                    value={imageValue}
                    onChange={(event) =>
                      handleUpdateEntry(index, {
                        value: { ...(entry.value as NestedRecord), image: event.target.value },
                      })
                    }
                    disabled={readOnly}
                    placeholder="e.g., registry/image:tag"
                    data-testid={
                      dataTestId
                        ? `${dataTestId}-field-${entry.key}-image`
                        : `vault-editor-nested-field-${entry.key}-image`
                    }
                  />
                </InlineFormItem>
              </Col>
              <Col span={6}>
                <InlineFormItem
                  label={
                    <RediaccText variant="label">{t('nestedObjectEditor.Active')}</RediaccText>
                  }
                >
                  <RediaccSwitch
                    checked={activeValue}
                    onChange={(checked) =>
                      handleUpdateEntry(index, {
                        value: { ...(entry.value as NestedRecord), active: checked },
                      })
                    }
                    disabled={readOnly}
                    data-testid={
                      dataTestId
                        ? `${dataTestId}-field-${entry.key}-active`
                        : `vault-editor-nested-field-${entry.key}-active`
                    }
                  />
                </InlineFormItem>
              </Col>
            </Row>
          </ImagePatternCard>
        );
      }

      return (
        <NestedObjectEditor
          value={entry.value}
          onChange={(newValue) => handleUpdateEntry(index, { value: newValue })}
          fieldDefinition={nestedDefinition}
          readOnly={readOnly}
          data-testid={
            dataTestId
              ? `${dataTestId}-nested-${entry.key}`
              : `vault-editor-nested-nested-${entry.key}`
          }
        />
      );
    }

    if (typeof entry.value === 'boolean') {
      return (
        <RediaccSwitch
          checked={entry.value}
          onChange={(checked) => handleUpdateEntry(index, { value: checked })}
          disabled={readOnly}
          data-testid={
            dataTestId
              ? `${dataTestId}-field-${entry.key}`
              : `vault-editor-nested-field-${entry.key}`
          }
        />
      );
    }

    if (typeof entry.value === 'number') {
      return (
        <NumericInput
          value={String(entry.value)}
          onChange={(event) =>
            handleUpdateEntry(index, { value: Number(event.currentTarget.value) })
          }
          disabled={readOnly}
          data-testid={
            dataTestId
              ? `${dataTestId}-field-${entry.key}`
              : `vault-editor-nested-field-${entry.key}`
          }
        />
      );
    }

    return (
      <Input
        value={entry.value as string | undefined}
        onChange={(event) => handleUpdateEntry(index, { value: event.target.value })}
        disabled={readOnly}
        data-testid={
          dataTestId ? `${dataTestId}-field-${entry.key}` : `vault-editor-nested-field-${entry.key}`
        }
      />
    );
  };

  return (
    <EditorContainer>
      {(title || description || structureInfo.isUniform) && (
        <SummaryCard>
          {title && (
            <RediaccText size="lg" weight="semibold" style={{ marginBottom: 4 }}>
              {title}
            </RediaccText>
          )}
          {description && (
            <RediaccText
              variant="description"
              style={{ display: 'flex', alignItems: 'center', gap: 4 }}
            >
              <InfoCircleOutlined /> {description}
            </RediaccText>
          )}
          {structureInfo.isUniform && (
            <SummaryBadgeRow>
              <UniformTag variant="success">{t('nestedObjectEditor.Uniform Structure')}</UniformTag>
              {structureInfo.keys && (
                <RediaccText
                  variant="caption"
                  color="secondary"
                  style={{
                    fontFamily:
                      "'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace",
                    backgroundColor: 'var(--rediacc-color-bg-secondary)',
                    padding: '4px 8px',
                    borderRadius: '4px',
                  }}
                >
                  {t('nestedObjectEditor.Fields')}: {structureInfo.keys.join(', ')}
                </RediaccText>
              )}
              {structureInfo.hasImagePattern && (
                <UniformTag variant="info">
                  {t('nestedObjectEditor.Container Images Detected')}
                </UniformTag>
              )}
            </SummaryBadgeRow>
          )}
        </SummaryCard>
      )}

      <EditorStack>
        {!readOnly && (
          <AddEntryCard
            size="sm"
            title={
              <RediaccText size="sm" weight="semibold">
                {t('nestedObjectEditor.Add New Entry')}
              </RediaccText>
            }
          >
            <EntryActionsRow>
              <KeyInputWrapper>
                <KeyInput
                  placeholder={t('nestedObjectEditor.Enter key name')}
                  value={newKey}
                  onChange={(event) => setNewKey(event.target.value)}
                  onPressEnter={handleAddEntry}
                  autoComplete="off"
                  data-testid={dataTestId ? `${dataTestId}-new-key` : 'vault-editor-nested-new-key'}
                />
              </KeyInputWrapper>
              <PrimaryActionButton
                icon={<PlusOutlined />}
                onClick={handleAddEntry}
                disabled={!newKey.trim()}
                data-testid={dataTestId ? `${dataTestId}-add` : 'vault-editor-nested-add'}
              >
                {t('nestedObjectEditor.Add')}
              </PrimaryActionButton>
              <SecondaryActionButton
                icon={<CodeOutlined />}
                onClick={() => setShowRawJson((current) => !current)}
                data-testid={
                  dataTestId ? `${dataTestId}-toggle-json` : 'vault-editor-nested-toggle-json'
                }
              >
                {showRawJson
                  ? t('nestedObjectEditor.Hide JSON')
                  : t('nestedObjectEditor.Show JSON')}
              </SecondaryActionButton>
            </EntryActionsRow>
          </AddEntryCard>
        )}

        {entries.length === 0 ? (
          <Empty
            description={t('nestedObjectEditor.No entries')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <CollapseWrapper
            defaultActiveKey={entries.map((_, i) => i.toString())}
            data-testid={dataTestId ? `${dataTestId}-collapse` : 'vault-editor-nested-collapse'}
            items={entries.map((entry, index) => ({
              key: entry.key,
              label: (
                <EntryHeader>
                  <KeyTag variant="info">{entry.key}</KeyTag>
                  {isRecordLike(entry.value) && (
                    <TypeTag variant="success">{t('nestedObjectEditor.Object')}</TypeTag>
                  )}
                  {Array.isArray(entry.value) && (
                    <TypeTag variant="warning">{t('nestedObjectEditor.Array')}</TypeTag>
                  )}
                  {typeof entry.value === 'boolean' && (
                    <TypeTag variant={entry.value ? 'success' : 'default'}>
                      {entry.value ? t('nestedObjectEditor.True') : t('nestedObjectEditor.False')}
                    </TypeTag>
                  )}
                </EntryHeader>
              ),
              extra: !readOnly ? (
                <PanelActions onClick={(event) => event.stopPropagation()}>
                  <Popconfirm
                    title={t('nestedObjectEditor.Delete this entry?')}
                    onConfirm={() => handleDeleteEntry(index)}
                    okText={t('nestedObjectEditor.Yes')}
                    cancelText={t('nestedObjectEditor.No')}
                  >
                    <PanelDeleteButton
                      variant="text"
                      danger
                      icon={<DeleteOutlined />}
                      size="sm"
                      data-testid={
                        dataTestId
                          ? `${dataTestId}-delete-${entry.key}`
                          : `vault-editor-nested-delete-${entry.key}`
                      }
                    />
                  </Popconfirm>
                </PanelActions>
              ) : undefined,
              children: renderEntryValue(entry, index),
            }))}
          />
        )}

        {showRawJson && (
          <RawJsonCard
            size="sm"
            title={
              <RediaccText
                size="sm"
                weight="semibold"
                style={{ display: 'flex', alignItems: 'center', gap: 4 }}
              >
                <CodeOutlined />
                {t('nestedObjectEditor.Raw JSON Editor')}
              </RediaccText>
            }
          >
            {rawJsonError && (
              <RediaccText color="danger" style={{ display: 'block', marginBottom: 8 }}>
                {t('nestedObjectEditor.JSON Error')}: {rawJsonError}
              </RediaccText>
            )}
            <SimpleJsonEditor
              value={rawJsonValue}
              onChange={handleRawJsonChange}
              readOnly={readOnly}
              height="300px"
              data-testid={dataTestId ? `${dataTestId}-raw-json` : 'vault-editor-nested-raw-json'}
            />
          </RawJsonCard>
        )}
      </EditorStack>
    </EditorContainer>
  );
};
