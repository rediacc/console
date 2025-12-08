import { forwardRef } from 'react';
import {
  StyledRediaccInput,
  StyledRediaccInputNumber,
  StyledRediaccPasswordInput,
  StyledRediaccSearchInput,
  StyledRediaccTextArea,
} from './RediaccInput.styles';
import type {
  RediaccInputNumberProps,
  RediaccInputProps,
  RediaccPasswordInputProps,
  RediaccSearchInputProps,
  RediaccTextAreaProps,
} from './RediaccInput.types';

/**
 * Unified RediaccInput Component
 *
 * A single, centralized input component that replaces all legacy input variants.
 *
 * @example
 * // Default text input
 * <RediaccInput placeholder="Enter text" />
 *
 * // Full-width input
 * <RediaccInput fullWidth placeholder="Enter email" />
 *
 * // Small size input
 * <RediaccInput size="small" placeholder="Search..." />
 *
 * // Input with prefix icon
 * <RediaccInput prefix={<SearchOutlined />} placeholder="Search..." />
 *
 * // Centered input
 * <RediaccInput centered placeholder="123456" />
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccInput = forwardRef<any, RediaccInputProps>(
  (
    {
      variant = 'default',
      size = 'md',
      fullWidth = false,
      centered = false,
      placeholder,
      value,
      onChange,
      disabled = false,
      prefix,
      suffix,
      allowClear = false,
      maxLength,
      autoFocus = false,
      name,
      id,
      onBlur,
      onFocus,
      onPressEnter,
      tabIndex,
      readOnly = false,
      status,
      defaultValue,
      type = 'text',
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccInput
        ref={ref}
        $variant={variant}
        $size={size}
        $fullWidth={fullWidth}
        $centered={centered}
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        prefix={prefix}
        suffix={suffix}
        allowClear={allowClear}
        maxLength={maxLength}
        autoFocus={autoFocus}
        name={name}
        id={id}
        onBlur={onBlur}
        onFocus={onFocus}
        onPressEnter={onPressEnter}
        tabIndex={tabIndex}
        readOnly={readOnly}
        status={status}
        defaultValue={defaultValue}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      />
    );
  }
);

RediaccInput.displayName = 'RediaccInput';

/**
 * RediaccPasswordInput Component
 *
 * Specialized input for password fields with visibility toggle.
 *
 * @example
 * // Basic password input
 * <RediaccPasswordInput placeholder="Enter password" />
 *
 * // Full-width password input
 * <RediaccPasswordInput fullWidth placeholder="Confirm password" />
 *
 * // Small size password input
 * <RediaccPasswordInput size="small" placeholder="New password" />
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccPasswordInput = forwardRef<any, RediaccPasswordInputProps>(
  (
    {
      size = 'md',
      fullWidth = false,
      centered = false,
      placeholder,
      value,
      onChange,
      disabled = false,
      prefix,
      suffix,
      allowClear = false,
      maxLength,
      autoFocus = false,
      name,
      id,
      onBlur,
      onFocus,
      onPressEnter,
      tabIndex,
      readOnly = false,
      status,
      defaultValue,
      visibilityToggle = true,
      iconRender,
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccPasswordInput
        ref={ref}
        $size={size}
        $fullWidth={fullWidth}
        $centered={centered}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        prefix={prefix}
        suffix={suffix}
        allowClear={allowClear}
        maxLength={maxLength}
        autoFocus={autoFocus}
        name={name}
        id={id}
        onBlur={onBlur}
        onFocus={onFocus}
        onPressEnter={onPressEnter}
        tabIndex={tabIndex}
        readOnly={readOnly}
        status={status}
        defaultValue={defaultValue}
        visibilityToggle={visibilityToggle}
        iconRender={iconRender}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      />
    );
  }
);

RediaccPasswordInput.displayName = 'RediaccPasswordInput';

/**
 * RediaccTextArea Component
 *
 * Multi-line text input with auto-resize support.
 *
 * @example
 * // Basic textarea
 * <RediaccTextArea rows={4} placeholder="Enter description" />
 *
 * // Auto-resize textarea
 * <RediaccTextArea autoSize={{ minRows: 2, maxRows: 6 }} placeholder="Comments" />
 *
 * // Full-width with character count
 * <RediaccTextArea fullWidth showCount maxLength={500} />
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccTextArea = forwardRef<any, RediaccTextAreaProps>(
  (
    {
      fullWidth = false,
      placeholder,
      value,
      onChange,
      disabled = false,
      allowClear = false,
      maxLength,
      autoFocus = false,
      name,
      id,
      onBlur,
      onFocus,
      onPressEnter,
      tabIndex,
      readOnly = false,
      status,
      defaultValue,
      rows = 4,
      autoSize = false,
      showCount = false,
      resize = 'vertical',
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccTextArea
        ref={ref}
        $fullWidth={fullWidth}
        $resize={resize}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        allowClear={allowClear}
        maxLength={maxLength}
        autoFocus={autoFocus}
        name={name}
        id={id}
        onBlur={onBlur}
        onFocus={onFocus}
        onPressEnter={onPressEnter}
        tabIndex={tabIndex}
        readOnly={readOnly}
        status={status}
        defaultValue={defaultValue}
        rows={rows}
        autoSize={autoSize}
        showCount={showCount}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      />
    );
  }
);

RediaccTextArea.displayName = 'RediaccTextArea';

/**
 * RediaccInputNumber Component
 *
 * Numeric input with increment/decrement controls.
 *
 * @example
 * // Basic number input
 * <RediaccInputNumber placeholder="Enter amount" />
 *
 * // With min/max and step
 * <RediaccInputNumber min={0} max={100} step={5} />
 *
 * // Full-width with precision
 * <RediaccInputNumber fullWidth precision={2} />
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccInputNumber = forwardRef<any, RediaccInputNumberProps>(
  (
    {
      size = 'md',
      fullWidth = false,
      placeholder,
      value,
      onChange,
      disabled = false,
      prefix,
      suffix,
      allowClear: _allowClear = false,
      maxLength,
      autoFocus = false,
      name,
      id,
      onBlur,
      onFocus,
      onPressEnter,
      tabIndex,
      readOnly = false,
      status,
      defaultValue,
      min,
      max,
      step = 1,
      precision,
      formatter,
      parser,
      controls = true,
      keyboard = true,
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccInputNumber
        ref={ref}
        $size={size}
        $fullWidth={fullWidth}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        prefix={prefix}
        suffix={suffix}
        maxLength={maxLength}
        autoFocus={autoFocus}
        name={name}
        id={id}
        onBlur={onBlur}
        onFocus={onFocus}
        onPressEnter={onPressEnter}
        tabIndex={tabIndex}
        readOnly={readOnly}
        status={status}
        defaultValue={defaultValue}
        min={min}
        max={max}
        step={step}
        precision={precision}
        formatter={formatter}
        parser={parser}
        controls={controls}
        keyboard={keyboard}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      />
    );
  }
);

RediaccInputNumber.displayName = 'RediaccInputNumber';

/**
 * RediaccSearchInput Component
 *
 * Search input with integrated search button.
 *
 * @example
 * // Basic search input
 * <RediaccSearchInput placeholder="Search..." onSearch={handleSearch} />
 *
 * // With custom search button
 * <RediaccSearchInput enterButton="Search" onSearch={handleSearch} />
 *
 * // Full-width with loading state
 * <RediaccSearchInput fullWidth loading={isSearching} onSearch={handleSearch} />
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccSearchInput = forwardRef<any, RediaccSearchInputProps>(
  (
    {
      size = 'md',
      fullWidth = false,
      placeholder,
      value,
      onChange,
      disabled = false,
      prefix,
      suffix,
      allowClear = false,
      maxLength,
      autoFocus = false,
      name,
      id,
      onBlur,
      onFocus,
      onPressEnter,
      tabIndex,
      readOnly = false,
      status,
      defaultValue,
      onSearch,
      loading = false,
      enterButton = false,
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccSearchInput
        ref={ref}
        $size={size}
        $fullWidth={fullWidth}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        prefix={prefix}
        suffix={suffix}
        allowClear={allowClear}
        maxLength={maxLength}
        autoFocus={autoFocus}
        name={name}
        id={id}
        onBlur={onBlur}
        onFocus={onFocus}
        onPressEnter={onPressEnter}
        tabIndex={tabIndex}
        readOnly={readOnly}
        status={status}
        defaultValue={defaultValue}
        onSearch={onSearch}
        loading={loading}
        enterButton={enterButton}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      />
    );
  }
);

RediaccSearchInput.displayName = 'RediaccSearchInput';
