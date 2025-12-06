import styled from 'styled-components';
import { Form, Typography } from 'antd';
import { BaseModal, FlexColumn, FlexRow } from '@/styles/primitives';
import { RediaccText, RediaccTabs } from '@/components/ui';
import { ActionsRow as CommonActionsRow } from '@/components/common/styled';
import { ModalSize } from '@/types/modal';

const { Paragraph } = Typography;

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} local-command-modal`,
})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const Description = styled(RediaccText).attrs({
  color: 'secondary',
})`
  && {
    display: block;
  }
`;

export const SettingsForm = styled(Form)`
  && {
    margin-bottom: 0;

    .ant-form-item {
      margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    }
  }
`;

export const CheckboxHelper = styled(RediaccText).attrs({
  size: 'sm',
  color: 'secondary',
})`
  && {
    margin-left: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const TabsWrapper = styled(RediaccTabs)`
  && {
    .ant-tabs-nav {
      margin-bottom: ${({ theme }) => theme.spacing.MD}px;
    }
  }
`;

export const CommandPreview = styled(FlexColumn).attrs({ $gap: 'SM' })`
  padding: ${({ theme }) => theme.spacing.LG}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.XL}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const PreviewHeader = styled(FlexRow).attrs({ $justify: 'space-between' })`
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const PreviewTitle = styled(RediaccText).attrs({
  weight: 'semibold',
})`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const PreviewError = styled(FlexColumn).attrs({ $gap: 'XS' })`
  padding: ${({ theme }) => theme.spacing.SM}px 0;
`;

export const PreviewErrorText = styled(RediaccText).attrs({
  color: 'danger',
})``;

export const PreviewHelper = styled(RediaccText).attrs({
  size: 'xs',
  color: 'secondary',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const CommandParagraph = styled(Paragraph)`
  && {
    margin: 0;
    font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    white-space: pre-wrap;
  }
`;

export const PreviewMetaRow = styled.div`
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const PreviewMetaText = styled(RediaccText).attrs({
  size: 'xs',
  color: 'secondary',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const ActionsRow = CommonActionsRow;
