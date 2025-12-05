import styled from 'styled-components';
import { Select, Tag, Input } from 'antd';

export const TeamSelect = styled(Select)`
  && {
    width: 100%;
  }

  && .ant-select-selector {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  }
`;

export const TeamTag = styled(Tag)`
  && {
    margin-right: ${({ theme }) => theme.spacing.XS}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    background-color: ${({ theme }) => theme.colors.primaryBg};
    color: ${({ theme }) => theme.colors.primary};
    border: 1px solid ${({ theme }) => theme.colors.primary};
  }
`;

export const DropdownSearchContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px;
`;

export const DropdownMenuWrapper = styled.div`
  border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const SearchInput = styled(Input)`
  && {
    .ant-input-prefix {
      color: ${({ theme }) => theme.colors.textSecondary};
    }
  }
`;

export const OptionLabel = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const OptionIcon = styled.span`
  display: inline-flex;
  align-items: center;
  color: ${({ theme }) => theme.colors.primary};
`;
