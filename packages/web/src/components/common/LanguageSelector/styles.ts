import styled from 'styled-components';
import { RediaccButton, RediaccSelect } from '@/components/ui';
import { media } from '@/styles/mixins';

export const LanguageButton = styled(RediaccButton).attrs({ iconOnly: true })`
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
    width: ${({ theme }) => theme.dimensions.DROPDOWN_WIDTH_SM}px;
    max-width: 100%;

    .ant-select-selector {
      border-radius: ${({ theme }) => theme.borderRadius.MD}px;
      min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
      color: ${({ theme }) => theme.colors.textPrimary};
    }

    .ant-select-arrow .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
    }
  }

  ${media.mobile`
    &.ant-select {
      width: 100%;
    }
  `}
`;
