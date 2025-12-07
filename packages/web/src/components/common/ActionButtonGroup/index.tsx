import React from 'react';
import { Tooltip, Dropdown } from 'antd';
import styled from 'styled-components';
// eslint-disable-next-line import/order -- False positive: no empty line exists
import { TableActionButton } from '@/components/common/styled';
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
  type: ActionButtonType | string;
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
  t?: TFunction;
  /** Gap between buttons */
  gap?: 'XS' | 'SM' | 'MD';
  /** Reserve space for hidden buttons to maintain consistent alignment across rows */
  reserveSpace?: boolean;
}

// =============================================================================
// STYLED COMPONENTS
// =============================================================================

const Container = styled.div<{ $gap: 'XS' | 'SM' | 'MD' }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ $gap, theme }) => theme.spacing[$gap]}px;
`;

/**
 * Placeholder element that reserves space for hidden buttons
 */
const ButtonPlaceholder = styled.div`
  width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  flex-shrink: 0;
`;

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

export function ActionButtonGroup<T>({
  buttons,
  record,
  idField,
  testIdPrefix = '',
  t,
  gap = 'SM',
  reserveSpace = false,
}: ActionButtonGroupProps<T>): React.ReactElement {
  // Type-safe access to record ID field
  const recordValue = record[idField];
  const recordId = String(recordValue !== null && recordValue !== undefined ? recordValue : '');
  const prefix = testIdPrefix ? `${testIdPrefix}-` : '';

  const getTooltipText = (text: string) => (t ? t(text) : text);

  // When reserveSpace is enabled, iterate over all buttons and render placeholders for hidden ones
  // Otherwise, filter to only visible buttons (original behavior)
  const buttonsToRender = reserveSpace
    ? buttons
    : buttons.filter((btn) => isButtonVisible(btn, record));

  return (
    <Container $gap={gap}>
      {buttonsToRender.map((config, index) => {
        const isVisible = isButtonVisible(config, record);

        // If reserveSpace is enabled and button is not visible, render a placeholder
        if (reserveSpace && !isVisible) {
          return <ButtonPlaceholder key={`placeholder-${index}`} />;
        }

        // Handle custom render slot
        if (isCustomConfig(config)) {
          return <React.Fragment key={`custom-${index}`}>{config.render(record)}</React.Fragment>;
        }

        const isDisabled =
          config.disabled === true ||
          (typeof config.disabled === 'function' && config.disabled(record));
        const isLoading =
          typeof config.loading === 'function' ? config.loading(record) : config.loading;

        const testId =
          typeof config.testId === 'function'
            ? config.testId(record)
            : config.testId ||
              (config.testIdSuffix
                ? `${prefix}${config.testIdSuffix}-${recordId}`
                : `${prefix}${config.type}-${recordId}`);

        const tooltipText = getTooltipText(config.tooltip);
        const ariaLabel = config.ariaLabel ? getTooltipText(config.ariaLabel) : tooltipText;
        const labelText = config.label ? getTooltipText(config.label) : undefined;

        const buttonElement = (
          <TableActionButton
            variant={config.variant === 'primary' ? 'primary' : undefined}
            icon={config.icon}
            danger={config.danger}
            disabled={isDisabled}
            onClick={config.onClick ? () => config.onClick?.(record) : undefined}
            loading={isLoading}
            data-testid={testId}
            aria-label={ariaLabel}
            $hasLabel={!!labelText}
          >
            {labelText}
          </TableActionButton>
        );

        // Wrap in dropdown if needed
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
      })}
    </Container>
  );
}

// =============================================================================
// PRESET FACTORIES
// =============================================================================

/**
 * Common icon imports for presets
 */
import {
  EditOutlined,
  DeleteOutlined,
  FunctionOutlined,
  HistoryOutlined,
  EyeOutlined,
  LockOutlined,
} from '@/utils/optimizedIcons';
import type { MenuProps } from 'antd';
import type { TFunction } from 'i18next';

/**
 * Preset button configurations for common patterns
 */
export const actionButtonPresets = {
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

export default ActionButtonGroup;
