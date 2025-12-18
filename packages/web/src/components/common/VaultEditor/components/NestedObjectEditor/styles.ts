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
  ${borderedCard()}
`;

// Removed: Use <RediaccText size="lg" weight="semibold" style={{ marginBottom: theme.spacing.XS }}>
// directly in components

// Removed: Use <RediaccText variant="description"> with inline styles
// for display: flex, align-items: center, gap

export const SummaryBadgeRow = styled.div`
  display: flex;
  flex-wrap: wrap;
`;

export const UniformTag = styled(RediaccTag)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

// Removed: Use <RediaccText variant="caption" color="secondary"> with inline styles
// for font-family, background-color, padding, border-radius

export const EditorStack = styled(FlexColumn).attrs({})`
  width: 100%;
`;

export const AddEntryCard = styled(RediaccCard)`
  && {
    ${borderedCard()}
  }
`;

// Removed: Use <RediaccText size="sm" weight="semibold"> directly

export const EntryActionsRow = ActionGroup;

export const KeyInputWrapper = styled.div`
  flex: 1 1 60%;
  min-width: ${({ theme }) => theme.dimensions.FILTER_INPUT_WIDTH}px;
  max-width: 100%;

  ${media.mobile`
    min-width: 0;
    flex: 1 1 100%;
  `}
`;

export const KeyInput = styled(RediaccInput).attrs({
  fullWidth: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const PrimaryActionButton = styled(RediaccButton).attrs({
  variant: 'primary',
})`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const SecondaryActionButton = styled(RediaccButton)``;

export const CollapseWrapper = styled(Collapse)`
  && {
    background-color: transparent;
  }
`;

export const EntryHeader = styled(InlineStack)`
  flex-wrap: wrap;
`;

export const KeyTag = styled(RediaccTag).attrs({
  size: 'md',
})`
  && {
    font-family: ${({ theme }) => theme.fontFamily.MONO};
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
  }
`;

export const RawJsonCard = styled(RediaccCard)`
  && {
  }
`;

// Removed: Use <RediaccText size="sm" weight="semibold"> with inline styles
// for display: flex, align-items: center, gap

// Removed: Use <RediaccText color="danger"> with inline styles
// for display: block, margin-bottom

// Removed: Use <RediaccText variant="label"> directly (or size="sm" weight="medium")

export const InlineFormItem = styled(Form.Item)`
`;

export const ImagePatternCard = styled(RediaccCard)`
  && {
  }
`;

export const NumericInput = styled(RediaccInput).attrs({ fullWidth: true })`
  && {
    max-width: ${({ theme }) => theme.dimensions.FILTER_INPUT_WIDTH}px;
  }
`;

export const TitleText = styled(RediaccText).attrs({
  size: 'lg',
  weight: 'semibold',
})`
  && {
  }
`;

export const DescriptionWrapper = styled(RediaccText).attrs({
  variant: 'description',
})`
  && {
    display: flex;
    align-items: center;
  }
`;

export const FieldsText = styled(RediaccText).attrs({
  variant: 'caption',
  color: 'secondary',
})`
  && {
    font-family: ${({ theme }) => theme.fontFamily.MONO};
  }
`;

export const JsonEditorTitleWrapper = styled(RediaccText).attrs({
  size: 'sm',
  weight: 'semibold',
})`
  && {
    display: flex;
    align-items: center;
  }
`;

export const JsonErrorText = styled(RediaccText).attrs({
  color: 'danger',
})`
  && {
    display: block;
  }
`;
