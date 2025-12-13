import { StyledRediaccSelect } from './RediaccSelect.styles';
import type { RediaccSelectProps } from './RediaccSelect.types';

/**
 * Unified RediaccSelect Component
 *
 * A single, centralized select component that replaces all legacy select variants.
 * Based on Ant Design Select with consistent theming.
 *
 * @example
 * // Basic select with options
 * <RediaccSelect
 *   value={value}
 *   onChange={setValue}
 *   options={[
 *     { value: '1', label: 'Option 1' },
 *     { value: '2', label: 'Option 2' }
 *   ]}
 * />
 *
 * @example
 * // Full-width select
 * <RediaccSelect fullWidth options={options} />
 *
 * @example
 * // Searchable select
 * <RediaccSelect showSearch filterOption options={options} />
 *
 * @example
 * // Multiple selection
 * <RediaccSelect mode="multiple" options={options} />
 *
 * @example
 * // Custom children (for advanced use cases)
 * <RediaccSelect>
 *   <RediaccSelect.Option value="1">Option 1</RediaccSelect.Option>
 *   <RediaccSelect.Option value="2">Option 2</RediaccSelect.Option>
 * </RediaccSelect>
 */
export const RediaccSelect: React.FC<RediaccSelectProps> = ({
  fullWidth = false,
  minWidth,
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
  loading = false,
  allowClear = false,
  showSearch = false,
  filterOption,
  searchValue,
  onSearch,
  mode,
  suffixIcon,
  popupMatchSelectWidth,
  tagRender,
  children,
  ...rest
}) => {
  return (
    <StyledRediaccSelect
      $fullWidth={fullWidth}
      $minWidth={minWidth}
      value={value}
      onChange={onChange}
      options={options}
      placeholder={placeholder}
      disabled={disabled}
      loading={loading}
      allowClear={allowClear}
      showSearch={showSearch}
      filterOption={filterOption}
      searchValue={searchValue}
      onSearch={onSearch}
      mode={mode}
      suffixIcon={suffixIcon}
      popupMatchSelectWidth={popupMatchSelectWidth}
      tagRender={tagRender}
      {...rest}
    >
      {children}
    </StyledRediaccSelect>
  );
};

RediaccSelect.displayName = 'RediaccSelect';

// Re-export Option for convenience when using children
export const { Option: RediaccOption } = StyledRediaccSelect;
