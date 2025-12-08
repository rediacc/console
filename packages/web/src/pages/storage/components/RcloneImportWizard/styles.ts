import { Typography } from 'antd';
import styled from 'styled-components';
import { RediaccText, RediaccModal } from '@/components/ui';
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
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    box-shadow: ${({ theme }) => theme.shadows.MODAL};
    border: none;
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }

  .ant-modal-header {
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }

  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.XL}px;
  }

  .ant-modal-footer {
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const UploadStepWrapper = styled.div`
  padding: ${({ theme }) => `${theme.spacing.LG}px 0`};
`;

export const StepsContainer = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const LoadingState = styled(BaseLoadingState).attrs({
  $paddingY: 'XXL',
})``;

export const LoadingTitle = styled(Title)`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const StatusMessage = styled(RediaccText)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;
