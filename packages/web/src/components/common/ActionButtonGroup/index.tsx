import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { MenuProps } from 'antd';
import { Button, Dropdown, Flex, Tooltip } from 'antd';
import React from 'react';
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FunctionOutlined,
  HistoryOutlined,
  LockOutlined,
} from '@/utils/optimizedIcons';
// =============================================================================
// TYPES
// =============================================================================

export type ActionButtonType = 'edit' | 'delete' | 'run' | 'trace' | 'view' | 'vault' | 'custom';
export type ActionButtonVariant = 'primary' | 'default' | 'link';

/**
 * Configuration for a standard action button
 */
export interface StandardButtonConfig<T = unknown> {
  /** Button type/identifier */
  type: string;
  /** Icon component */
  icon: React.ReactNode;
  /** Tooltip text (can be i18n key if t is provided) */
  tooltip: string;
  /** Optional text label (translation key) - if provided, button shows text alongside icon */
  label?: string;
  /** Click handler */
  onClick?: (record: T) => void;
  /** Dropdown menu items (makes this a dropdown button) */
  dropdownItems?: MenuProps['items'];
  /** Dropdown menu click handler */
  onDropdownClick?: (key: string, record: T) => void;
  /** Show loading state */
  loading?: boolean | ((record: T) => boolean);
  /** Button variant */
  variant?: ActionButtonVariant;
  /** Show danger styling */
  danger?: boolean;
  /** Visibility check */
  visible?: boolean | ((record: T) => boolean);
  /** Disabled check */
  disabled?: boolean | ((record: T) => boolean);
  /** Explicit test identifier */
  testId?: string | ((record: T) => string);
  /** Test ID suffix (auto-generated if not provided) */
  testIdSuffix?: string;
  /** Aria label (defaults to tooltip) */
  ariaLabel?: string;
}

/**
 * Configuration for a custom render slot
 */
export interface CustomButtonConfig<T = unknown> {
  /** Must be 'custom' to use render function */
  type: 'custom';
  /** Custom render function */
  render: (record: T) => React.ReactNode;
  /** Visibility check */
  visible?: boolean | ((record: T) => boolean);
}

/**
 * Union type for button configurations
 */
export type ActionButtonConfig<T = unknown> = StandardButtonConfig<T> | CustomButtonConfig<T>;

/**
 * Props for ActionButtonGroup component
 */
export interface ActionButtonGroupProps<T> {
  /** Button configurations */
  buttons: ActionButtonConfig<T>[];
  /** Current row record */
  record: T;
  /** Field to use for test ID generation */
  idField: keyof T;
  /** Test ID prefix */
  testIdPrefix?: string;
  /** Translation function */
  t?: TypedTFunction;
  /** Reserve space for hidden buttons to maintain consistent alignment across rows */
  reserveSpace?: boolean;
}

// =============================================================================
// STYLED COMPONENTS
// =============================================================================

const Container: React.FC<React.HTMLAttributes<HTMLDivElement>> = (props) => (
  <Flex align="center" className="inline-flex" {...props} />
);

const ButtonPlaceholder: React.FC<React.HTMLAttributes<HTMLDivElement>> = (props) => (
  <Flex className="flex-shrink-0" {...props} />
);

// =============================================================================
// COMPONENT
// =============================================================================

/**
 * Generates a group of action buttons for table rows
 *
 * @example
 * // In column definition
 * {
 *   title: t('common:table.actions'),
 *   key: 'actions',
 *   render: (_, record) => (
 *     <ActionButtonGroup
 *       buttons={[
 *         { type: 'edit', icon: <EditOutlined />, tooltip: 'common:actions.edit', onClick: onEdit },
 *         { type: 'delete', icon: <DeleteOutlined />, tooltip: 'common:actions.delete', onClick: onDelete, danger: true },
 *       ]}
 *       record={record}
 *       idField="clusterName"
 *       testIdPrefix="ds-cluster"
 *       t={t}
 *     />
 *   )
 * }
 */
/**
 * Type guard for custom button config
 */
function isCustomConfig<T>(config: ActionButtonConfig<T>): config is CustomButtonConfig<T> {
  return config.type === 'custom' && 'render' in config;
}

/**
 * Check if a button is visible for a given record
 */
function isButtonVisible<T>(btn: ActionButtonConfig<T>, record: T): boolean {
  if (btn.visible === undefined) return true;
  if (typeof btn.visible === 'boolean') return btn.visible;
  return btn.visible(record);
}

const VARIANT_TO_TYPE: Record<ActionButtonVariant | 'default', 'primary' | 'link' | 'default'> = {
  primary: 'primary',
  link: 'link',
  default: 'default',
};

function getButtonType(variant?: ActionButtonVariant): 'primary' | 'link' | 'default' {
  return VARIANT_TO_TYPE[variant ?? 'default'];
}

function resolveTestId<T>(
  config: StandardButtonConfig<T>,
  record: T,
  prefix: string,
  recordId: string
): string {
  if (typeof config.testId === 'function') return config.testId(record);
  if (config.testId) return config.testId;
  if (config.testIdSuffix) return `${prefix}${config.testIdSuffix}-${recordId}`;
  return `${prefix}${config.type}-${recordId}`;
}

function resolveBoolean<T>(
  value: boolean | ((record: T) => boolean) | undefined,
  record: T,
  defaultValue = false
): boolean {
  if (value === undefined) return defaultValue;
  if (typeof value === 'boolean') return value;
  return value(record);
}

interface StandardButtonRendererProps<T> {
  config: StandardButtonConfig<T>;
  record: T;
  prefix: string;
  recordId: string;
  getTooltipText: (text: string) => string;
}

function StandardButtonRenderer<T>({
  config,
  record,
  prefix,
  recordId,
  getTooltipText,
}: StandardButtonRendererProps<T>): React.ReactElement {
  const isDisabled = resolveBoolean(config.disabled, record);
  const isLoading = resolveBoolean(config.loading, record);
  const testId = resolveTestId(config, record, prefix, recordId);
  const tooltipText = getTooltipText(config.tooltip);
  const ariaLabel = config.ariaLabel ? getTooltipText(config.ariaLabel) : tooltipText;
  const labelText = config.label ? getTooltipText(config.label) : undefined;
  const buttonType = getButtonType(config.variant);

  const buttonElement = (
    <Button
      type={buttonType}
      icon={config.icon}
      danger={config.danger}
      disabled={isDisabled}
      onClick={config.onClick ? () => config.onClick?.(record) : undefined}
      loading={isLoading}
      data-testid={testId}
      aria-label={ariaLabel}
      shape={labelText ? 'default' : 'circle'}
    >
      {labelText}
    </Button>
  );

  if (config.dropdownItems) {
    return (
      <Dropdown
        key={config.type}
        menu={{
          items: config.dropdownItems,
          onClick: config.onDropdownClick
            ? ({ key }) => config.onDropdownClick?.(key, record)
            : undefined,
        }}
        trigger={['click']}
      >
        <Tooltip title={tooltipText}>{buttonElement}</Tooltip>
      </Dropdown>
    );
  }

  return (
    <Tooltip key={config.type} title={tooltipText}>
      {buttonElement}
    </Tooltip>
  );
}

export function ActionButtonGroup<T>({
  buttons,
  record,
  idField,
  testIdPrefix = '',
  t,
  reserveSpace = false,
}: ActionButtonGroupProps<T>): React.ReactElement {
  const recordValue = record[idField];
  const recordId = String(recordValue ?? '');
  const prefix = testIdPrefix ? `${testIdPrefix}-` : '';
  const getTooltipText = (text: string) => (t ? t(text) : text);

  const buttonsToRender = reserveSpace
    ? buttons
    : buttons.filter((btn) => isButtonVisible(btn, record));

  return (
    <Container>
      {buttonsToRender.map((config, index) => {
        const isVisible = isButtonVisible(config, record);

        if (reserveSpace && !isVisible) {
          return <ButtonPlaceholder key={`placeholder-${index}`} />;
        }

        if (isCustomConfig(config)) {
          return <React.Fragment key={`custom-${index}`}>{config.render(record)}</React.Fragment>;
        }

        return (
          <StandardButtonRenderer
            key={config.type}
            config={config}
            record={record}
            prefix={prefix}
            recordId={recordId}
            getTooltipText={getTooltipText}
          />
        );
      })}
    </Container>
  );
}

// =============================================================================
// PRESET FACTORIES
// =============================================================================

/**
 * Preset button configurations for common patterns
 */
const actionButtonPresets = {
  /**
   * Edit button
   */
  edit: <T,>(onClick: (record: T) => void): ActionButtonConfig<T> => ({
    type: 'edit',
    icon: <EditOutlined />,
    tooltip: 'common:actions.edit',
    onClick,
    variant: 'primary',
  }),

  /**
   * Delete button (danger)
   */
  delete: <T,>(onClick: (record: T) => void): ActionButtonConfig<T> => ({
    type: 'delete',
    icon: <DeleteOutlined />,
    tooltip: 'common:actions.delete',
    onClick,
    variant: 'primary',
    danger: true,
  }),

  /**
   * Trace/history button
   */
  trace: <T,>(onClick: (record: T) => void): ActionButtonConfig<T> => ({
    type: 'trace',
    icon: <HistoryOutlined />,
    tooltip: 'common:actions.trace',
    onClick,
    variant: 'default',
  }),

  /**
   * View details button
   */
  view: <T,>(onClick: (record: T) => void): ActionButtonConfig<T> => ({
    type: 'view',
    icon: <EyeOutlined />,
    tooltip: 'common:viewDetails',
    onClick,
    variant: 'default',
  }),

  /**
   * Vault button
   */
  vault: <T,>(onClick: (record: T) => void): ActionButtonConfig<T> => ({
    type: 'vault',
    icon: <LockOutlined />,
    tooltip: 'common:actions.vault',
    onClick,
    variant: 'primary',
  }),

  /**
   * Run function dropdown button
   */
  runFunction: <T,>(
    dropdownItems: MenuProps['items'],
    onDropdownClick: (key: string, record: T) => void
  ): ActionButtonConfig<T> => ({
    type: 'run',
    icon: <FunctionOutlined />,
    tooltip: 'common:actions.remote',
    dropdownItems,
    onDropdownClick,
    variant: 'primary',
  }),

  /**
   * Common preset: Edit + Run + Trace + Delete
   */
  editRunTraceDelete: <T,>(handlers: {
    onEdit: (record: T) => void;
    onDelete: (record: T) => void;
    onTrace: (record: T) => void;
    dropdownItems: MenuProps['items'];
    onDropdownClick: (key: string, record: T) => void;
  }): ActionButtonConfig<T>[] => [
    actionButtonPresets.edit(handlers.onEdit),
    actionButtonPresets.runFunction(handlers.dropdownItems, handlers.onDropdownClick),
    actionButtonPresets.trace(handlers.onTrace),
    actionButtonPresets.delete(handlers.onDelete),
  ],

  /**
   * Common preset: Edit + Delete
   */
  editDelete: <T,>(handlers: {
    onEdit: (record: T) => void;
    onDelete: (record: T) => void;
  }): ActionButtonConfig<T>[] => [
    actionButtonPresets.edit(handlers.onEdit),
    actionButtonPresets.delete(handlers.onDelete),
  ],

  /**
   * Common preset: View + Edit + Delete
   */
  viewEditDelete: <T,>(handlers: {
    onView: (record: T) => void;
    onEdit: (record: T) => void;
    onDelete: (record: T) => void;
  }): ActionButtonConfig<T>[] => [
    actionButtonPresets.view(handlers.onView),
    actionButtonPresets.edit(handlers.onEdit),
    actionButtonPresets.delete(handlers.onDelete),
  ],
};

// Export for internal use if needed in the future
void actionButtonPresets;
