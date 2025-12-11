import { Form, Row } from 'antd';
import styled from 'styled-components';
import { RediaccAlert, RediaccButton, RediaccText } from '@/components/ui';
import { FlexColumn, FlexRow } from '@/styles/primitives';
import {
  BulbOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
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

export const TestConnectionButton = styled(RediaccButton).attrs({
  fullWidth: true,
})`
  && {
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  }
`;

// Removed: Use <RediaccText> with inline styles for conditional color
// Example: style={{ color: `var(--rediacc-color-${status})`, textTransform: 'capitalize' }}

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

export const TestConnectionAlert = styled(RediaccAlert)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const CompatibilityStatusText = styled(RediaccText)<{ $variant: string }>`
  color: var(--rediacc-color-${({ $variant }) => $variant});
  text-transform: capitalize;
`;

export const FieldDivider = styled.div`
  margin: ${({ theme }) => theme.spacing.MD}px 0;

  .ant-divider {
    margin: 0;
  }
`;
