import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Flex,
  Form,
  Input,
  Popconfirm,
  Row,
  Switch,
  Tag,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { SimpleJsonEditor } from '@/components/common/VaultEditor/components/SimpleJsonEditor';
import {
  CodeOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  PlusOutlined,
} from '@/utils/optimizedIcons';

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

const EMPTY_RECORD: NestedRecord = {};

// Type-based default value map for cleaner branching
const getTypeBasedDefault = (value: unknown): NestedEntryValue => {
  if (typeof value === 'boolean') return false;
  if (typeof value === 'number') return 0;
  if (typeof value === 'string') return '';
  if (Array.isArray(value)) return [];
  if (isRecordLike(value)) return {};
  return '';
};

// Creates default value based on existing structure pattern
const createDefaultFromStructure = (
  firstEntry: NestedRecord,
  hasImagePattern: boolean
): NestedRecord => {
  return Object.keys(firstEntry).reduce<NestedRecord>((acc, keyName) => {
    const existingValue = firstEntry[keyName];

    if (keyName === 'active' || keyName === 'enabled') {
      acc[keyName] = true;
    } else if (keyName === 'image' && hasImagePattern) {
      acc[keyName] = '';
    } else {
      acc[keyName] = getTypeBasedDefault(existingValue);
    }

    return acc;
  }, {});
};

// Creates default value from field definition schema
const createDefaultFromSchema = (propDef: FieldSchema): NestedEntryValue => {
  if (propDef.type === 'object' && propDef.properties) {
    return Object.keys(propDef.properties).reduce<NestedRecord>((acc, keyName) => {
      const schema = propDef.properties?.[keyName];
      if (schema) {
        if (schema.default !== undefined) {
          acc[keyName] = schema.default;
        } else if (schema.type === 'boolean') {
          acc[keyName] = false;
        } else if (schema.type === 'number') {
          acc[keyName] = 0;
        } else {
          acc[keyName] = '';
        }
      }
      return acc;
    }, {});
  }

  if (propDef.type === 'boolean') return false;
  if (propDef.type === 'number') return 0;
  return '';
};

// Determines the default value for a new entry based on structure info or field definition
const getDefaultValueForNewEntry = (
  structureInfo: ReturnType<typeof detectStructurePattern>,
  entries: ObjectEntry[],
  fieldDefinition?: FieldSchema
): NestedEntryValue => {
  // Try to infer from existing uniform structure
  if (structureInfo.isUniform && structureInfo.keys && entries.length > 0) {
    const firstEntry = entries[0]?.value;
    if (isRecordLike(firstEntry)) {
      return createDefaultFromStructure(firstEntry, structureInfo.hasImagePattern ?? false);
    }
  }

  // Try to infer from field definition schema
  if (
    fieldDefinition?.additionalProperties &&
    typeof fieldDefinition.additionalProperties === 'object'
  ) {
    return createDefaultFromSchema(fieldDefinition.additionalProperties);
  }

  return '';
};

export const NestedObjectEditor: React.FC<NestedObjectEditorProps> = ({
  value,
  onChange,
  fieldDefinition,
  readOnly = false,
  title,
  description,
  'data-testid': dataTestId,
}) => {
  const { t } = useTranslation('common');
  const safeValue = value ?? EMPTY_RECORD;
  const serializedValue = useMemo(() => JSON.stringify(safeValue), [safeValue]);
  const parsedValue = useMemo(() => {
    try {
      return JSON.parse(serializedValue) as NestedRecord;
    } catch {
      return EMPTY_RECORD;
    }
  }, [serializedValue]);
  const [entries, setEntries] = useState<ObjectEntry[]>(() =>
    Object.entries(safeValue).map(([key, val]) => ({
      key,
      value: val,
      isEditing: false,
    }))
  );
  const [newKey, setNewKey] = useState('');
  const [showRawJson, setShowRawJson] = useState(false);
  const [rawJsonValue, setRawJsonValue] = useState(() => JSON.stringify(safeValue, null, 2));
  const [rawJsonError, setRawJsonError] = useState<string | null>(null);
  const [structureInfo, setStructureInfo] = useState<ReturnType<typeof detectStructurePattern>>(
    () => detectStructurePattern(safeValue)
  );

  useEffect(() => {
    const entriesArray = Object.entries(parsedValue).map(([key, val]) => ({
      key,
      value: val,
      isEditing: false,
    }));
    setEntries(entriesArray);
    setRawJsonValue(JSON.stringify(parsedValue, null, 2));
    setStructureInfo(detectStructurePattern(parsedValue));
  }, [parsedValue, serializedValue]);

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

    const defaultValue = getDefaultValueForNewEntry(structureInfo, entries, fieldDefinition);

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

  const getFieldTestId = (entryKey: string, suffix?: string): string => {
    const baseSuffix = suffix ? `-${suffix}` : '';
    return dataTestId
      ? `${dataTestId}-field-${entryKey}${baseSuffix}`
      : `vault-editor-nested-field-${entryKey}${baseSuffix}`;
  };

  const isImageActivePattern = (
    entryValue: NestedRecord
  ): entryValue is NestedRecord & { image: string; active: boolean } => {
    const imageValue = entryValue.image;
    const activeValue = entryValue.active;
    return (
      typeof imageValue === 'string' &&
      typeof activeValue === 'boolean' &&
      (structureInfo.hasImagePattern ?? looksLikeImageReference(imageValue))
    );
  };

  const renderImageActiveEditor = (
    entry: ObjectEntry,
    index: number,
    entryValue: NestedRecord & { image: string; active: boolean }
  ): React.ReactNode => (
    <Card size="small">
      <Row gutter={16}>
        <Col span={18}>
          <Form.Item label={<Typography.Text>{t('nestedObjectEditor.Image')}</Typography.Text>}>
            <Input
              value={entryValue.image}
              onChange={(event) =>
                handleUpdateEntry(index, {
                  value: { ...entryValue, image: event.target.value },
                })
              }
              disabled={readOnly}
              placeholder={t('functions:imagePlaceholder')}
              data-testid={getFieldTestId(entry.key, 'image')}
            />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item label={<Typography.Text>{t('nestedObjectEditor.Active')}</Typography.Text>}>
            <Switch
              checked={entryValue.active}
              onChange={(checked) =>
                handleUpdateEntry(index, {
                  value: { ...entryValue, active: checked },
                })
              }
              disabled={readOnly}
              data-testid={getFieldTestId(entry.key, 'active')}
            />
          </Form.Item>
        </Col>
      </Row>
    </Card>
  );

  const renderRecordEntry = (entry: ObjectEntry, index: number): React.ReactNode => {
    const entryValue = entry.value as NestedRecord;

    if (isImageActivePattern(entryValue)) {
      return renderImageActiveEditor(entry, index, entryValue);
    }

    const entryDef =
      fieldDefinition?.properties?.[entry.key] ?? fieldDefinition?.additionalProperties;
    const nestedDefinition = typeof entryDef === 'object' ? entryDef : undefined;

    return (
      <NestedObjectEditor
        value={entryValue}
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
  };

  const renderPrimitiveEntry = (entry: ObjectEntry, index: number): React.ReactNode => {
    const testId = getFieldTestId(entry.key);

    if (typeof entry.value === 'boolean') {
      return (
        <Switch
          checked={entry.value}
          onChange={(checked) => handleUpdateEntry(index, { value: checked })}
          disabled={readOnly}
          data-testid={testId}
        />
      );
    }

    if (typeof entry.value === 'number') {
      return (
        <Input
          className="w-full"
          // eslint-disable-next-line no-restricted-syntax
          style={{ maxWidth: 240 }}
          value={String(entry.value)}
          onChange={(event) =>
            handleUpdateEntry(index, { value: Number(event.currentTarget.value) })
          }
          disabled={readOnly}
          data-testid={testId}
        />
      );
    }

    return (
      <Input
        value={entry.value as string | undefined}
        onChange={(event) => handleUpdateEntry(index, { value: event.target.value })}
        disabled={readOnly}
        data-testid={testId}
      />
    );
  };

  const renderEntryValue = (entry: ObjectEntry, index: number): React.ReactNode => {
    if (isRecordLike(entry.value)) {
      return renderRecordEntry(entry, index);
    }
    return renderPrimitiveEntry(entry, index);
  };

  return (
    <Flex vertical className="w-full">
      {Boolean(title ?? description ?? structureInfo.isUniform) && (
        <Flex vertical>
          {title && <Typography.Text strong>{title}</Typography.Text>}
          {description && (
            <Typography.Text>
              <InfoCircleOutlined /> {description}
            </Typography.Text>
          )}
          {structureInfo.isUniform && (
            <Flex wrap>
              <Tag>{t('nestedObjectEditor.Uniform Structure')}</Tag>
              {structureInfo.keys && (
                <Typography.Text>
                  {t('nestedObjectEditor.Fields')}: {structureInfo.keys.join(', ')}
                </Typography.Text>
              )}
              {structureInfo.hasImagePattern && (
                <Tag>{t('nestedObjectEditor.Container Images Detected')}</Tag>
              )}
            </Flex>
          )}
        </Flex>
      )}

      <Flex vertical className="w-full">
        {!readOnly && (
          <Card
            size="small"
            title={
              <Typography.Text strong>{t('nestedObjectEditor.Add New Entry')}</Typography.Text>
            }
          >
            <Flex align="center" wrap>
              <Flex
                className="max-w-full"
                // eslint-disable-next-line no-restricted-syntax
                style={{ flex: '1 1 60%', minWidth: 240 }}
              >
                <Input
                  className="w-full"
                  placeholder={t('nestedObjectEditor.Enter key name')}
                  value={newKey}
                  onChange={(event) => setNewKey(event.target.value)}
                  onPressEnter={handleAddEntry}
                  autoComplete="off"
                  data-testid={dataTestId ? `${dataTestId}-new-key` : 'vault-editor-nested-new-key'}
                />
              </Flex>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleAddEntry}
                disabled={!newKey.trim()}
                data-testid={dataTestId ? `${dataTestId}-add` : 'vault-editor-nested-add'}
              >
                {t('nestedObjectEditor.Add')}
              </Button>
              <Button
                icon={<CodeOutlined />}
                onClick={() => setShowRawJson((current) => !current)}
                data-testid={
                  dataTestId ? `${dataTestId}-toggle-json` : 'vault-editor-nested-toggle-json'
                }
              >
                {showRawJson
                  ? t('nestedObjectEditor.Hide JSON')
                  : t('nestedObjectEditor.Show JSON')}
              </Button>
            </Flex>
          </Card>
        )}

        {entries.length === 0 ? (
          <Empty
            description={t('nestedObjectEditor.No entries')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Collapse
            defaultActiveKey={entries.map((_, i) => i.toString())}
            data-testid={dataTestId ? `${dataTestId}-collapse` : 'vault-editor-nested-collapse'}
            items={entries.map((entry, index) => ({
              key: entry.key,
              label: (
                <Flex align="center" wrap>
                  <Tag>{entry.key}</Tag>
                  {isRecordLike(entry.value) && <Tag>{t('nestedObjectEditor.Object')}</Tag>}
                  {Array.isArray(entry.value) && <Tag>{t('nestedObjectEditor.Array')}</Tag>}
                  {typeof entry.value === 'boolean' && (
                    <Tag>
                      {entry.value ? t('nestedObjectEditor.True') : t('nestedObjectEditor.False')}
                    </Tag>
                  )}
                </Flex>
              ),
              extra: readOnly ? undefined : (
                <Flex onClick={(event) => event.stopPropagation()}>
                  <Popconfirm
                    title={t('nestedObjectEditor.Delete this entry?')}
                    onConfirm={() => handleDeleteEntry(index)}
                    okText={t('nestedObjectEditor.Yes')}
                    cancelText={t('nestedObjectEditor.No')}
                  >
                    <Button
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      data-testid={
                        dataTestId
                          ? `${dataTestId}-delete-${entry.key}`
                          : `vault-editor-nested-delete-${entry.key}`
                      }
                    />
                  </Popconfirm>
                </Flex>
              ),
              children: renderEntryValue(entry, index),
            }))}
          />
        )}

        {showRawJson && (
          <Card
            size="small"
            title={
              <Typography.Text strong>
                <CodeOutlined />
                {t('nestedObjectEditor.Raw JSON Editor')}
              </Typography.Text>
            }
          >
            {rawJsonError && (
              <Typography.Text type="danger">
                {t('nestedObjectEditor.JSON Error')}: {rawJsonError}
              </Typography.Text>
            )}
            <SimpleJsonEditor
              value={rawJsonValue}
              onChange={handleRawJsonChange}
              readOnly={readOnly}
              height="300px"
              data-testid={dataTestId ? `${dataTestId}-raw-json` : 'vault-editor-nested-raw-json'}
            />
          </Card>
        )}
      </Flex>
    </Flex>
  );
};
