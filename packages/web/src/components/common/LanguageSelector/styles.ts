import styled from 'styled-components';
import { RediaccButton as Button } from '@/components/ui';
import { RediaccSelect } from '@/components/ui/Form';

export const LanguageButton = styled(Button).attrs({ iconOnly: true })`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};

    &:not(:disabled):hover {
      color: ${({ theme }) => theme.colors.primary};
      background-color: ${({ theme }) => theme.colors.bgHover};
    }
  }
`;

export const LanguageSelect = styled(RediaccSelect)`
  &.ant-select {
    width: 140px;

    .ant-select-selector {
      border-radius: ${({ theme }) => theme.borderRadius.MD}px;
      min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
      color: ${({ theme }) => theme.colors.textPrimary};
    }

    .ant-select-arrow .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
    }
  }
`;
