import styled from 'styled-components';
import { Card, Collapse, Typography, Tag, Button, Input, Form } from 'antd';
import {
  PrimaryButton as PrimitivePrimaryButton,
  SecondaryButton as PrimitiveSecondaryButton,
} from '@/styles/primitives';

const { Title, Text } = Typography;

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

export const SummaryTitle = styled(Title)`
  && {
    margin: 0;
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-size: ${({ theme }) => theme.fontSize.H5}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const SummaryDescription = styled(Text)`
  && {
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    line-height: ${({ theme }) => theme.lineHeight.NORMAL};
  }
`;

export const SummaryBadgeRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const UniformTag = styled(Tag)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const FieldsBadge = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    font-family: 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace;
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    padding: ${({ theme }) => `${theme.spacing.XS}px ${theme.spacing.SM}px`};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const EditorStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
  width: 100%;
`;

export const AddEntryCard = styled(Card)`
  && {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border: 1px solid ${({ theme }) => theme.colors.borderPrimary};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    box-shadow: ${({ theme }) => theme.shadows.CARD};
  }
`;

export const CardHeading = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const EntryActionsRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const KeyInputWrapper = styled.div`
  flex: 1 1 60%;
  min-width: 220px;
`;

export const KeyInput = styled(Input)`
  && {
    width: 100%;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const PrimaryActionButton = styled(PrimitivePrimaryButton).attrs({
  $size: 'SM',
})`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const SecondaryActionButton = styled(PrimitiveSecondaryButton).attrs({
  $size: 'SM',
})``;

export const CollapseWrapper = styled(Collapse)`
  && {
    background-color: transparent;
    border: none;
  }
`;

export const EntryHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  flex-wrap: wrap;
`;

export const KeyTag = styled(Tag)`
  && {
    font-family: 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    padding: ${({ theme }) => `${theme.spacing.XS}px ${theme.spacing.SM}px`};
  }
`;

export const TypeTag = styled(Tag)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const PanelActions = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const PanelDeleteButton = styled(Button)`
  && {
    padding: 0;
  }
`;

export const RawJsonCard = styled(Card)`
  && {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border: 1px solid ${({ theme }) => theme.colors.borderPrimary};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    box-shadow: ${({ theme }) => theme.shadows.CARD};
  }
`;

export const RawJsonTitle = styled(Text)`
  && {
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const RawJsonError = styled(Text)`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.error};
  }
`;

export const InlineLabel = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const InlineFormItem = styled(Form.Item)`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const ImagePatternCard = styled(Card)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
    background-color: ${({ theme }) => theme.colors.bgTertiary};
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    box-shadow: ${({ theme }) => theme.shadows.CARD};
  }
`;

export const NumericInput = styled(Input)`
  && {
    width: 100%;
    max-width: 200px;
  }
`;
