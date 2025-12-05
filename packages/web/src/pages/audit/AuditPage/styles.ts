import styled from 'styled-components';
import { Space, Typography, Button } from 'antd';
import { FilterOutlined } from '@/utils/optimizedIcons';
import { PageContainer } from '@/styles/primitives';

const { Text } = Typography;

export const PageWrapper = PageContainer;

export const ContentStack = styled(Space).attrs({ orientation: 'vertical', size: 'large' })`
  width: 100%;
`;

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
  min-height: ${({ theme }) => theme.spacing['6']}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
`;

export const LinkButton = styled(Button).attrs({ type: 'link' })`
  padding: 0;
  height: auto;
`;

export const TableHeader = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const TableActions = styled(Space)`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  justify-content: flex-end;
`;

export const NoResults = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.LG}px 0;
  color: ${({ theme }) => theme.colors.textSecondary};
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

export const ActionIcon = styled.span<{ $color: string }>`
  display: inline-flex;
  align-items: center;
  color: ${({ $color }) => $color};
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const DescriptionText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;
