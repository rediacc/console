import { Collapse, Form } from 'antd';
import styled from 'styled-components';
import { ActionGroup, InlineStack } from '@/components/common/styled';
import { RediaccButton, RediaccCard, RediaccInput, RediaccTag, RediaccText } from '@/components/ui';
import { borderedCard, media } from '@/styles/mixins';
import { FlexColumn } from '@/styles/primitives';

export const EditorContainer = styled.div`
  width: 100%;
`;

export const SummaryCard = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.MD}px;
  background-color: ${({ theme }) => theme.colors.bgTertiary};
  ${borderedCard()}
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

// Removed: Use <RediaccText size="lg" weight="semibold" style={{ marginBottom: theme.spacing.XS }}>
// directly in components

// Removed: Use <RediaccText variant="description"> with inline styles
// for display: flex, align-items: center, gap

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

// Removed: Use <RediaccText variant="caption" color="secondary"> with inline styles
// for font-family, background-color, padding, border-radius

export const EditorStack = styled(FlexColumn).attrs({ $gap: 'LG' })`
  width: 100%;
`;

export const AddEntryCard = styled(RediaccCard)`
  && {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    ${borderedCard('borderPrimary')}
    box-shadow: ${({ theme }) => theme.shadows.CARD};
  }
`;

// Removed: Use <RediaccText size="sm" weight="semibold"> directly

export const EntryActionsRow = ActionGroup;

export const KeyInputWrapper = styled.div`
  flex: 1 1 60%;
  min-width: 220px;
  max-width: 100%;

  ${media.mobile`
    min-width: 0;
    flex: 1 1 100%;
  `}
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

// Removed: Use <RediaccText size="sm" weight="semibold"> with inline styles
// for display: flex, align-items: center, gap

// Removed: Use <RediaccText color="danger"> with inline styles
// for display: block, margin-bottom

// Removed: Use <RediaccText variant="label"> directly (or size="sm" weight="medium")

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

export const NumericInput = styled(RediaccInput).attrs({ fullWidth: true })`
  && {
    max-width: 200px;
  }
`;

export const TitleText = styled(RediaccText).attrs({
  size: 'lg',
  weight: 'semibold',
})`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.XS / 2}px;
  }
`;

export const DescriptionWrapper = styled(RediaccText).attrs({
  variant: 'description',
})`
  && {
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const FieldsText = styled(RediaccText).attrs({
  variant: 'caption',
  color: 'secondary',
})`
  && {
    font-family: 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace;
    background-color: var(--rediacc-color-bg-secondary);
    padding: ${({ theme }) => theme.spacing.XS}px ${({ theme }) => theme.spacing.SM}px;
    border-radius: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const JsonEditorTitleWrapper = styled(RediaccText).attrs({
  size: 'sm',
  weight: 'semibold',
})`
  && {
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const JsonErrorText = styled(RediaccText).attrs({
  color: 'danger',
})`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  }
`;
