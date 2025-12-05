import styled from 'styled-components';
import { Space, Typography, Button } from 'antd';
import { FilterOutlined } from '@/utils/optimizedIcons';
import { PageContainer, StyledIcon } from '@/styles/primitives';
import { ContentStack } from '@/components/common/styled';

const { Text } = Typography;

export const PageWrapper = PageContainer;

// Re-export from common/styled
export { ContentStack };

export const FilterField = styled(Space).attrs({ orientation: 'vertical', size: 'small' })`
  width: 100%;
`;

export const FilterLabel = styled(Text)`
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

export const ActionButtonFull = styled(Button)`
  width: 100%;
  min-height: ${({ theme }) => theme.spacing.XXXL}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
`;

export const LinkButton = styled(Button).attrs({ type: 'link' })`
  padding: 0;
  height: auto;
`;

// Use HeaderRow from common/styled (space-between layout with MD gap)
export { HeaderRow as TableHeader } from '@/components/common/styled';

// Use ActionGroup from common/styled (flex-wrap with SM gap)
export { ActionGroup as TableActions } from '@/components/common/styled';

// Use CenteredState from common/styled
export { CenteredState as NoResults } from '@/components/common/styled';

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

// Use CaptionText from primitives
export { CaptionText as DescriptionText } from '@/styles/primitives';
