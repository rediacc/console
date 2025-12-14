import { StyledRediaccDropdown } from './RediaccDropdown.styles';
import type { RediaccDropdownProps } from './RediaccDropdown.types';

/**
 * RediaccDropdown - Themed dropdown component
 *
 * A wrapper around Ant Design's Dropdown with consistent defaults.
 * Use RediaccActionMenu for table row action menus.
 *
 * @example
 * // Simple menu dropdown
 * <RediaccDropdown menu={{ items }} trigger={['click']}>
 *   <RediaccButton>Options</RediaccButton>
 * </RediaccDropdown>
 *
 * @example
 * // Custom popup content
 * <RediaccDropdown
 *   popupRender={() => <CustomPanel />}
 *   placement="bottomRight"
 *   overlayStyle={{ minWidth: 300 }}
 * >
 *   <RediaccButton icon={<UserOutlined />} />
 * </RediaccDropdown>
 */
export const RediaccDropdown = ({
  menu,
  popupRender,
  trigger = ['click'],
  placement = 'bottomLeft',
  disabled = false,
  open,
  onOpenChange,
  overlayStyle,
  overlayClassName,
  autoAdjustOverflow = true,
  arrow = false,
  destroyPopupOnHide = false,
  getPopupContainer,
  children,
  'data-testid': testId,
  ...rest
}: RediaccDropdownProps) => {
  return (
    <StyledRediaccDropdown
      menu={menu}
      dropdownRender={popupRender}
      trigger={trigger}
      placement={placement}
      disabled={disabled}
      open={open}
      onOpenChange={onOpenChange}
      overlayStyle={overlayStyle}
      overlayClassName={overlayClassName}
      autoAdjustOverflow={autoAdjustOverflow}
      arrow={arrow}
      destroyPopupOnHide={destroyPopupOnHide}
      getPopupContainer={getPopupContainer}
      data-testid={testId}
      {...rest}
    >
      {children}
    </StyledRediaccDropdown>
  );
};
