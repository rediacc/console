import { Typography } from 'antd';
import styled from 'styled-components';
import { RediaccAlert, RediaccModal, RediaccText } from '@/components/ui';
import { LoadingState as BaseLoadingState } from '@/styles/primitives';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

const { Title } = Typography;

export const WizardModal = styled(RediaccModal).attrs({
  width: DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_XL,
})`
  && {
    max-width: calc(100vw - ${DESIGN_TOKENS.SPACING.XL}px);
  }

  .ant-modal-content {
  }

  .ant-modal-header {
  }

  .ant-modal-body {
  }

  .ant-modal-footer {
  }
`;

export const UploadStepWrapper = styled.div`
`;

export const StepsContainer = styled.div`
`;

export const LoadingState = styled(BaseLoadingState).attrs({})``;

export const LoadingTitle = styled(Title)`
  && {
  }
`;

export const StatusMessage = styled(RediaccText)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.XS}px;
  }
`;

export const ParsingErrorAlert = styled(RediaccAlert)`
  && {
  }
`;

export const NameText = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;
