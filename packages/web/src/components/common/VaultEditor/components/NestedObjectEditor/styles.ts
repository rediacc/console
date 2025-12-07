import { Collapse, Form } from 'antd';
import styled from 'styled-components';
import { InlineStack, ActionGroup } from '@/components/common/styled';
import { RediaccButton, RediaccCard, RediaccText, RediaccTag, RediaccInput } from '@/components/ui';
import { FlexColumn } from '@/styles/primitives';

export const EditorContainer = styled.div`
  width: 100%;
`;

export const SummaryCard = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.MD}px;
  background-color: ${({ theme }) => theme.colors.bgTertiary};
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

export const SummaryTitle = styled(RediaccText).attrs({
  size: 'lg',
  weight: 'semibold',
})`
  && {
    margin: 0;
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
    display: block;
  }
`;

export const SummaryDescription = styled(RediaccText).attrs({
  size: 'sm',
  color: 'secondary',
})`
  && {
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const SummaryBadgeRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const UniformTag = styled(RediaccTag)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const FieldsBadge = styled(RediaccText).attrs({
  variant: 'caption',
  color: 'secondary',
})`
  && {
    font-family: 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace;
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    padding: ${({ theme }) => `${theme.spacing.XS}px ${theme.spacing.SM}px`};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

export const EditorStack = styled(FlexColumn).attrs({ $gap: 'LG' })`
  width: 100%;
`;

export const AddEntryCard = styled(RediaccCard)`
  && {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border: 1px solid ${({ theme }) => theme.colors.borderPrimary};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    box-shadow: ${({ theme }) => theme.shadows.CARD};
  }
`;

export const CardHeading = styled(RediaccText).attrs({
  size: 'sm',
  weight: 'semibold',
})`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const EntryActionsRow = ActionGroup;

export const KeyInputWrapper = styled.div`
  flex: 1 1 60%;
  min-width: 220px;
`;

export const KeyInput = styled(RediaccInput).attrs({
  size: 'sm',
  fullWidth: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const PrimaryActionButton = styled(RediaccButton).attrs({
  variant: 'primary',
  size: 'sm',
})`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const SecondaryActionButton = styled(RediaccButton).attrs({
  size: 'sm',
})``;

export const CollapseWrapper = styled(Collapse)`
  && {
    background-color: transparent;
    border: none;
  }
`;

export const EntryHeader = styled(InlineStack)`
  flex-wrap: wrap;
`;

export const KeyTag = styled(RediaccTag).attrs({
  size: 'md',
})`
  && {
    font-family: 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const TypeTag = styled(RediaccTag).attrs({
  size: 'sm',
})`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const PanelActions = InlineStack;

export const PanelDeleteButton = styled(RediaccButton).attrs({ iconOnly: true, variant: 'danger' })`
  && {
    padding: 0;
  }
`;

export const RawJsonCard = styled(RediaccCard)`
  && {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border: 1px solid ${({ theme }) => theme.colors.borderPrimary};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    box-shadow: ${({ theme }) => theme.shadows.CARD};
  }
`;

export const RawJsonTitle = styled(RediaccText).attrs({
  size: 'sm',
  weight: 'semibold',
})`
  && {
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const RawJsonError = styled(RediaccText).attrs({
  color: 'danger',
})`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const InlineLabel = styled(RediaccText).attrs({
  size: 'sm',
  weight: 'medium',
})`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const InlineFormItem = styled(Form.Item)`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const ImagePatternCard = styled(RediaccCard)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
    background-color: ${({ theme }) => theme.colors.bgTertiary};
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    box-shadow: ${({ theme }) => theme.shadows.CARD};
  }
`;

export const NumericInput = styled(RediaccInput)`
  && {
    width: 100%;
    max-width: 200px;
  }
`;
