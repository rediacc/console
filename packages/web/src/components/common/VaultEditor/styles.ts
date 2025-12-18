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

export const EditorContainer = styled(FlexColumn).attrs({})``;

export const InfoBanner = styled(RediaccAlert)`
  && {
    flex-shrink: 0;
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
`;

export const FieldLabelStack = styled(FlexRow).attrs({
  $align: 'center',
})``;

export const FieldInfoIcon = styled(InfoCircleOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const TestConnectionButton = styled(RediaccButton).attrs({
  fullWidth: true,
})`
  && {
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

// Removed: Use <RediaccText> with inline styles for conditional color
// Example: style={{ color: `var(--color-${status})`, textTransform: 'capitalize' }}

export const ListSection = styled.div`
`;

export const IssueList = styled.ul`
`;

export const RecommendationList = styled(IssueList)`
`;

export const ProviderSectionSpacer = styled.div`
`;

export const TipsDividerIcon = styled(BulbOutlined)`
`;

export const TipsAlert = styled(RediaccAlert)`
  && {
  }
`;

export const ExtraFieldsWarningIcon = styled(WarningOutlined)`
  font-size: ${({ theme }) => theme.fontSize.MD}px;
`;

export const RawJsonPreview = styled.pre`
  overflow: auto;
`;

export const DangerAlertIcon = styled(ExclamationCircleOutlined)`
  font-size: ${({ theme }) => theme.fontSize.MD}px;
`;

export const FormatActions = styled(FlexRow).attrs({
  $justify: 'flex-end',
})`
`;

export const FormatButton = styled(RediaccButton)`
  && {
  }
`;

export const TestConnectionAlert = styled(RediaccAlert)`
  && {
  }
`;

export const CompatibilityStatusText = styled(RediaccText)<{ $variant: string }>`
  color: var(--color-${({ $variant }) => $variant});
  text-transform: capitalize;
`;

export const FieldDivider = styled.div`
  .ant-divider {
  }
`;
