import styled from 'styled-components';
import { RediaccInput, RediaccSelect } from '@/components/ui/Form';
import { RediaccTag } from '@/components/ui/Tag';
import { InlineStack } from '@/components/common/styled';

export const TeamSelect = styled(RediaccSelect)`
  && {
    width: 100%;
  }

  && .ant-select-selector {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  }
`;

export const TeamTag = styled(RediaccTag).attrs({
  preset: 'team',
})`
  && {
    margin-right: ${({ theme }) => theme.spacing.XS}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
  }
`;

export const DropdownSearchContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px;
`;

export const DropdownMenuWrapper = styled.div`
  border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const SearchInput = styled(RediaccInput)`
  && {
    .ant-input-prefix {
      color: ${({ theme }) => theme.colors.textSecondary};
    }
  }
`;

export const OptionLabel = styled(InlineStack)`
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const OptionIcon = styled(InlineStack)`
  color: ${({ theme }) => theme.colors.primary};
`;
