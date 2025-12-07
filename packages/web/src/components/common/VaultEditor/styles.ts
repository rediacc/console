import { Form, Row } from 'antd';
import styled, { css } from 'styled-components';
import { RediaccButton, RediaccText, RediaccStack, RediaccAlert, RediaccDivider } from '@/components/ui';
import {
  RediaccInput,
  RediaccPasswordInput,
  RediaccTextArea,
  RediaccInputNumber,
  RediaccSelect,
} from '@/components/ui/Form';
import { FlexColumn, FlexRow } from '@/styles/primitives';
import {
  InfoCircleOutlined,
  BulbOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
} from '@/utils/optimizedIcons';

export const EditorContainer = styled(FlexColumn).attrs({ $gap: 'MD' })``;

export const InfoBanner = styled(RediaccAlert)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    flex-shrink: 0;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const EditorForm = styled(Form)`
  width: 100%;
`;

export const FormRow = styled(Row)`
  width: 100%;
`;

export const FieldItem = styled(Form.Item)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const FieldLabelStack = styled(FlexRow).attrs({
  $gap: 'XS',
  $align: 'center',
})``;

export const FieldInfoIcon = styled(InfoCircleOutlined)`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const FullWidthStack = styled(RediaccStack).attrs({ direction: 'vertical' })`
  width: 100%;
`;

export const InlineInfoAlert = styled(RediaccAlert)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const TestConnectionButton = styled(RediaccButton).attrs({
  fullWidth: true,
})`
  && {
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  }
`;

export const StatusHighlightText = styled(RediaccText)<{
  $status: 'success' | 'warning' | 'error' | 'info';
}>`
  && {
    color: ${({ theme, $status }) => theme.colors[$status]};
    text-transform: capitalize;
  }
`;

export const ListSection = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const IssueList = styled.ul`
  margin: ${({ theme }) => `${theme.spacing.XS}px 0 ${theme.spacing.SM}px`};
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`;

export const RecommendationList = styled(IssueList)`
  margin-bottom: 0;
`;

export const SectionDivider = styled(RediaccDivider)`
  && {
    margin: ${({ theme }) => theme.spacing.MD}px 0;
  }
`;

export const SectionAlert = styled(RediaccAlert)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const ProviderSectionSpacer = styled.div`
  margin-top: ${({ theme }) => theme.spacing.LG}px;
`;

export const TipsDividerIcon = styled(BulbOutlined)`
  color: ${({ theme }) => theme.colors.warning};
`;

export const TipsAlert = styled(RediaccAlert)`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const ExtraFieldsWarningIcon = styled(WarningOutlined)`
  color: ${({ theme }) => theme.colors.warning};
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
`;

export const ExtraFieldsAlert = styled(RediaccAlert)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const RawJsonPreview = styled.pre`
  margin: 0;
  overflow: auto;
`;

export const DangerAlertIcon = styled(ExclamationCircleOutlined)`
  color: ${({ theme }) => theme.colors.error};
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
`;

export const FormatActions = styled(FlexRow).attrs({
  $justify: 'flex-end',
})`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const FormatButton = styled(RediaccButton).attrs({
  size: 'sm',
})`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  }
`;

// =============================================================================
// FULL-WIDTH FORM COMPONENTS
// =============================================================================

/**
 * Full-width form control styling
 */
const fullWidthControlStyles = css`
  width: 100%;
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  background-color: ${({ theme }) => theme.colors.inputBg};
  border-color: ${({ theme }) => theme.colors.inputBorder};
  transition: ${({ theme }) => theme.transitions.DEFAULT};

  &:focus,
  &.ant-input-focused,
  &.ant-select-focused {
    border-color: ${({ theme }) => theme.colors.primary};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
  }
`;

/**
 * Full-width input wrappers for VaultEditor
 */
export const FullWidthInput = styled(RediaccInput)`
  && {
    ${fullWidthControlStyles}
  }
`;

export const FullWidthPasswordInput = styled(RediaccPasswordInput).attrs({
  fullWidth: true,
})``;

export const FullWidthTextArea = styled(RediaccTextArea).attrs({ fullWidth: true })``;

export const FullWidthInputNumber = styled(RediaccInputNumber).attrs({ fullWidth: true })``;

export const FullWidthSelect = styled(RediaccSelect).attrs({ fullWidth: true })``;
