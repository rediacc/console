import { Form } from 'antd';
import styled from 'styled-components';
import { ActionsRow as CommonActionsRow } from '@/components/common/styled';
import { RediaccTabs, RediaccText } from '@/components/ui';
import { borderedCard } from '@/styles/mixins';
import { BaseModal, FlexColumn, FlexRow } from '@/styles/primitives';
import { ModalSize } from '@/types/modal';

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} local-command-modal`,
})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.LG}px;
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
  ${borderedCard('borderSecondary', 'XL')}
`;

export const PreviewHeader = styled(FlexRow).attrs({ $justify: 'space-between' })`
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const PreviewError = styled(FlexColumn).attrs({ $gap: 'XS' })`
  padding: ${({ theme }) => theme.spacing.SM}px 0;
`;

export const CommandParagraph = styled(RediaccText).attrs({ as: 'p' })`
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

export const ActionsRow = CommonActionsRow;

export const BlockText = styled(RediaccText)`
  display: block;
`;

export const HelperTextWithMargin = styled(RediaccText)`
  margin-left: ${({ theme }) => theme.spacing.SM}px;
`;

export const LoadingIndicatorWithMargin = styled.span`
  margin-left: ${({ theme }) => theme.spacing.SM}px;
`;
