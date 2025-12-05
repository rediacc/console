import styled from 'styled-components';
import { Card, Space, Input, Typography, Button, Tag, Empty, Row } from 'antd';
import { HelperText as PrimitiveHelperText, MutedCaption } from '@/styles/primitives';

const { Text, Paragraph } = Typography;

export const SelectorContainer = styled.div`
  width: 100%;
`;

export const HeaderStack = styled(Space)`
  && {
    width: 100%;
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const HelperRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const HelperText = PrimitiveHelperText;

export const ClearButton = styled(Button)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
  }
`;

export const SearchInput = styled(Input.Search)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const ResultCount = styled(MutedCaption)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    display: block;
  }
`;

export const NoResultsEmpty = styled(Empty)`
  && {
    margin: ${({ theme }) => theme.spacing.MD}px 0;
  }
`;

export const TemplateGrid = styled(Row)`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const TemplateCard = styled(Card)<{ $selected?: boolean; $variant?: 'default' | 'none' }>`
  height: 100%;
  border-color: ${({ theme, $selected, $variant }) =>
    $selected
      ? $variant === 'none'
        ? theme.colors.success
        : theme.colors.primary
      : theme.colors.borderSecondary};
  border-width: ${({ $selected }) => ($selected ? '2px' : '1px')};
  border-style: ${({ $variant }) => ($variant === 'none' ? 'dashed' : 'solid')};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  position: relative;
  cursor: pointer;
  transition: ${({ theme }) => theme.transitions.HOVER};
  padding: ${({ theme }) => theme.spacing.MD}px;
`;

export const SelectionIndicator = styled.span<{ $variant?: 'default' | 'none' }>`
  position: absolute;
  top: ${({ theme }) => theme.spacing.SM}px;
  right: ${({ theme }) => theme.spacing.SM}px;
  color: ${({ theme, $variant }) =>
    $variant === 'none' ? theme.colors.success : theme.colors.primary};
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const CardStack = styled(Space)`
  && {
    width: 100%;
  }
`;

export const TemplateIconWrapper = styled.div<{ $muted?: boolean }>`
  text-align: center;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  color: ${({ theme, $muted }) => ($muted ? theme.colors.textTertiary : theme.colors.textPrimary)};

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_LG}px;
  }
`;

export const TemplateTitle = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
  }
`;

export const TemplateDescription = styled(Paragraph)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    line-height: ${({ theme }) => theme.lineHeight.RELAXED};
  }
`;

export const DetailsButton = styled(Button)`
  && {
    padding: 0;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;

    .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
    }
  }
`;

export const DefaultTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    margin: 0;
  }
`;

export const LoadingText = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const ErrorState = styled.div`
  text-align: center;
  padding: ${({ theme }) => `${theme.spacing.MD}px 0`};
`;

export { LoadingState } from '@/styles/primitives';
