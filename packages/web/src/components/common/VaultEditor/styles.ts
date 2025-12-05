import styled from 'styled-components';
import { Alert, Button, Divider, Form, Row, Space, Typography } from 'antd';
import {
  InfoCircleOutlined,
  BulbOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
} from '@/utils/optimizedIcons';

const { Text } = Typography;

export const EditorContainer = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

export const InfoBanner = styled(Alert)`
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

export const FieldLabelStack = styled(Space)`
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const FieldInfoIcon = styled(InfoCircleOutlined)`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const FullWidthStack = styled(Space)`
  width: 100%;
`;

export const InlineInfoAlert = styled(Alert)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const TestConnectionButton = styled(Button)`
  && {
    width: 100%;
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  }
`;

export const StatusHighlightText = styled(Text)<{
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

export const SectionDivider = styled(Divider)`
  && {
    margin: ${({ theme }) => theme.spacing.MD}px 0;
  }
`;

export const SectionAlert = styled(Alert)`
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

export const TipsAlert = styled(Alert)`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const ExtraFieldsWarningIcon = styled(WarningOutlined)`
  color: ${({ theme }) => theme.colors.warning};
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
`;

export const ExtraFieldsAlert = styled(Alert)`
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

export const FormatActions = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  display: flex;
  justify-content: flex-end;
`;

export const FormatButton = styled(Button)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export {
  FullWidthInput,
  FullWidthPasswordInput,
  FullWidthTextArea,
  FullWidthInputNumber,
  FullWidthSelect,
} from '@/styles/primitives';
