import styled from 'styled-components';
import { RediaccCard } from '@/components/ui';
import { FlexRow, StyledIcon } from '@/styles/primitives';
import { ReloadOutlined } from '@/utils/optimizedIcons';

export const LoadingContent = styled(FlexRow).attrs({ $justify: 'center' })`
`;

export const RefreshButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;

  &:hover {
  }
`;

export const RefreshIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: ReloadOutlined,
  $size: theme.spacing.MD,
}))``;

export const StatCard = styled(RediaccCard)`
  text-align: center;
`;

export const PercentageSuffix = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const StyledRediaccCard = styled(RediaccCard)`
  && {
  }
`;
