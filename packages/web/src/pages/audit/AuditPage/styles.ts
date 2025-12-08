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
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const PlaceholderLabel = styled(FilterLabel)`
  && {
    color: transparent;
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
    padding: 0;
    height: auto;
  }
`;

export const FilterHintIcon = styled(FilterOutlined)`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  opacity: 0.7;
`;

export const ColumnFilterIcon = styled(FilterOutlined)<{ $active?: boolean }>`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ $active, theme }) =>
    $active ? theme.colors.textPrimary : theme.colors.textTertiary};
  transition: color ${({ theme }) => theme.transitions.FAST};
`;

// Use StyledIcon from primitives
export const ActionIcon = styled(StyledIcon).attrs<{ $color: string }>(({ $color }) => ({
  $size: 'MD',
  $color,
}))<{ $color: string }>``;

// DescriptionText removed - use RediaccText variant="caption" directly
