import { Dropdown } from 'antd';
import styled from 'styled-components';

/**
 * Styled dropdown wrapper
 *
 * Note: The dropdown popup/menu renders in a portal outside the component tree,
 * so styling the menu items requires global CSS or antd's ConfigProvider.
 * This wrapper primarily serves to provide a consistent component interface.
 */
export const StyledRediaccDropdown = styled(Dropdown)`
  /* Trigger element inherits parent styles */
`;
