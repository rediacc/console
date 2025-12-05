import styled from 'styled-components';
import { Select } from 'antd';
import { IconButton } from '@/styles/primitives';

export const LanguageButton = styled(IconButton)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};

    &:not(:disabled):hover {
      color: ${({ theme }) => theme.colors.primary};
      background-color: ${({ theme }) => theme.colors.bgHover};
    }
  }
`;

export const LanguageSelect = styled(Select)`
  && {
    width: 140px;

    .ant-select-selector {
      border-radius: ${({ theme }) => theme.borderRadius.MD}px !important;
      min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
      color: ${({ theme }) => theme.colors.textPrimary};
    }

    .ant-select-arrow .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
    }
  }
`;

export const LanguageOption = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;
