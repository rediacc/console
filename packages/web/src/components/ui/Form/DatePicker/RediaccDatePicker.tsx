import { forwardRef } from 'react';
import { StyledRediaccDatePicker, StyledRediaccRangePicker } from './RediaccDatePicker.styles';
import type { RediaccDatePickerProps, RediaccRangePickerProps } from './RediaccDatePicker.types';

/**
 * RediaccRangePicker Component
 *
 * Date range picker for selecting start and end dates.
 *
 * @example
 * <RediaccDatePicker.RangePicker
 *   value={dateRange}
 *   onChange={setDateRange}
 *   placeholder={['Start date', 'End date']}
 * />
 */
const RediaccRangePicker = forwardRef<any, RediaccRangePickerProps>(
  (
    {
      value,
      defaultValue,
      onChange,
      disabled = false,
      placeholder,
      format,
      minWidth,
      allowClear = true,
      showTime = false,
      id,
      autoFocus = false,
      getPopupContainer,
      status,
      picker,
      disabledDate,
      separator,
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccRangePicker
        ref={ref}
        $minWidth={minWidth}
        value={value}
        defaultValue={defaultValue}
        onChange={onChange}
        disabled={disabled}
        placeholder={placeholder}
        format={format}
        allowClear={allowClear}
        showTime={showTime}
        id={id}
        autoFocus={autoFocus}
        getPopupContainer={getPopupContainer}
        status={status}
        picker={picker}
        disabledDate={disabledDate}
        separator={separator}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      />
    );
  }
);

RediaccRangePicker.displayName = 'RediaccRangePicker';

/**
 * RediaccDatePicker Component
 *
 * A theme-aware date picker component that replaces direct antd imports.
 *
 * @example
 * // Basic date picker
 * <RediaccDatePicker value={date} onChange={setDate} />
 *
 * // With placeholder
 * <RediaccDatePicker placeholder="Select date" onChange={handleChange} />
 *
 * // With minimum width
 * <RediaccDatePicker minWidth={200} value={date} onChange={setDate} />
 *
 * // Month picker
 * <RediaccDatePicker picker="month" value={month} onChange={setMonth} />
 *
 * // With time selection
 * <RediaccDatePicker showTime value={dateTime} onChange={setDateTime} />
 */
const RediaccDatePickerBase = forwardRef<any, RediaccDatePickerProps>(
  (
    {
      value,
      defaultValue,
      onChange,
      disabled = false,
      placeholder,
      format,
      minWidth,
      allowClear = true,
      showTime = false,
      showToday = true,
      id,
      autoFocus = false,
      getPopupContainer,
      status,
      picker,
      disabledDate,
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccDatePicker
        ref={ref}
        $minWidth={minWidth}
        value={value}
        defaultValue={defaultValue}
        onChange={onChange}
        disabled={disabled}
        placeholder={placeholder}
        format={format}
        allowClear={allowClear}
        showTime={showTime}
        showToday={showToday}
        id={id}
        autoFocus={autoFocus}
        getPopupContainer={getPopupContainer}
        status={status}
        picker={picker}
        disabledDate={disabledDate}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      />
    );
  }
);

RediaccDatePickerBase.displayName = 'RediaccDatePicker';

/**
 * RediaccDatePicker Component with RediaccRangePicker
 *
 * Provides RediaccDatePicker and RediaccDatePicker.RangePicker for date selection.
 *
 * @example
 * import { RediaccDatePicker } from '@/components/ui/Form';
 *
 * // Single date
 * <RediaccDatePicker value={date} onChange={setDate} />
 *
 * // Date range
 * <RediaccDatePicker.RangePicker value={range} onChange={setRange} />
 */
export const RediaccDatePicker = Object.assign(RediaccDatePickerBase, {
  RangePicker: RediaccRangePicker,
});

// Named exports for direct imports
export { RediaccRangePicker };
