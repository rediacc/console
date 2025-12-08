import { StyledRediaccSelect } from './RediaccSelect.styles';
import type { RediaccSelectProps, SelectSize } from './RediaccSelect.types';

const mapToAntdSize = (size: SelectSize = 'md'): 'small' | 'middle' | 'large' => {
  switch (size) {
    case 'sm':
      return 'small';
    case 'lg':
      return 'large';
    case 'md':
    default:
      return 'middle';
  }
};

/**
 * Unified RediaccSelect Component
 *
 * A single, centralized select component that replaces all legacy select variants.
 * Based on Ant Design Select with consistent theming and size variants.
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
 * // Small size select with minimum width
 * <RediaccSelect size="small" minWidth={150} options={options} />
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
  size = 'md',
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
  const antdSize = mapToAntdSize(size);

  return (
    <StyledRediaccSelect
      $size={size}
      size={antdSize}
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
