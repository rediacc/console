import styled from 'styled-components';
import { RediaccButton } from '@/components/ui/Button';

export const ToggleButton = styled(RediaccButton)`
  && {
    min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: ${({ theme }) => theme.colors.textPrimary};
    transition: ${({ theme }) => theme.transitions.BUTTON};

    &:not(:disabled):hover {
      color: ${({ theme }) => theme.colors.primary};
      background-color: ${({ theme }) => theme.colors.bgHover};
    }

    .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
    }
  }
`;
