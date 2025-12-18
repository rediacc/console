import styled from 'styled-components';
import { RediaccButton } from '@/components/ui';

export const ToggleButton = styled(RediaccButton)`
  && {
    min-width: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;

    &:not(:disabled):hover {
    }

    .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
    }
  }
`;
