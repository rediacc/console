import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag } from '@/components/ui';
import { RediaccInput, RediaccSelect } from '@/components/ui/Form';

export const TeamSelect = styled(RediaccSelect).attrs({ fullWidth: true })`
  && .ant-select-selector {
  }
`;

export const TeamTag = styled(RediaccTag).attrs({
  preset: 'team',
})`
  && {
    display: inline-flex;
    align-items: center;
  }
`;

export const DropdownSearchContainer = styled.div`
`;

export const DropdownMenuWrapper = styled.div`
`;

export const SearchInput = styled(RediaccInput)`
  && {
    .ant-input-prefix {
    }
  }
`;

export const OptionLabel = styled(InlineStack)`
`;

export const OptionIcon = styled(InlineStack)`
`;
