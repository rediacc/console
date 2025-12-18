import styled from 'styled-components';
import { ContentStack } from '@/components/common/styled';
import { RediaccButton, RediaccText } from '@/components/ui';
import { StyledIcon } from '@/styles/primitives';
import { FilterOutlined } from '@/utils/optimizedIcons';

// Re-export from common/styled
export { ContentStack };

export const FilterLabel = styled(RediaccText)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const PlaceholderLabel = styled(FilterLabel)`
  && {
  }
`;

export const ActionButtonFull = styled(RediaccButton)`
  && {
    width: 100%;
    min-height: ${({ theme }) => theme.spacing.XXXL}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`;

export const LinkButton = styled(RediaccButton).attrs({ variant: 'link' })`
  && {
    height: auto;
  }
`;

export const FilterHintIcon = styled(FilterOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const ColumnFilterIcon = styled(FilterOutlined)<{ $active?: boolean }>`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

// Use StyledIcon from primitives
export const ActionIcon = styled(StyledIcon).attrs<{ $color: string }>(({ $color }) => ({
  $size: 'MD',
  $color,
}))<{ $color: string }>``;

// DescriptionText removed - use RediaccText variant="caption" directly
