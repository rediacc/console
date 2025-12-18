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
  }
`;

export const SettingsForm = styled(Form)`
  && {

    .ant-form-item {
    }
  }
`;

export const TabsWrapper = styled(RediaccTabs)`
  && {
    .ant-tabs-nav {
    }
  }
`;

export const CommandPreview = styled(FlexColumn).attrs({})`
  ${borderedCard()}
`;

export const PreviewHeader = styled(FlexRow).attrs({ $justify: 'space-between' })`
`;

export const PreviewError = styled(FlexColumn).attrs({})`
`;

export const CommandParagraph = styled(RediaccText).attrs({ as: 'p' })`
  && {
    font-family: ${({ theme }) => theme.fontFamily.MONO};
    white-space: pre-wrap;
  }
`;

export const PreviewMetaRow = styled.div`
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
`;

export const ActionsRow = CommonActionsRow;

export const BlockText = styled(RediaccText)`
  display: block;
`;

export const HelperTextWithMargin = styled(RediaccText)`
`;

export const LoadingIndicatorWithMargin = styled.span`
`;
