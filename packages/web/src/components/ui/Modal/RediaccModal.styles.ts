import { Modal as AntModal } from 'antd';
import styled, { css } from 'styled-components';
import type { ModalSize, ModalVariant } from './RediaccModal.types';

const MODAL_WIDTH_MAP: Record<ModalSize, string | number> = {
  sm: 400,
  md: 520,
  lg: 800,
  xl: 1200,
  fullscreen: '100vw',
};

export const resolveModalWidth = (size: ModalSize = 'md'): string | number => {
  return MODAL_WIDTH_MAP[size] ?? 520;
};

export const StyledRediaccModal = styled(AntModal).withConfig({
  shouldForwardProp: (prop) => !['$size', '$variant'].includes(prop),
})<{
  $size: ModalSize;
  $variant: ModalVariant;
}>`
  ${({ $size }) =>
    $size === 'fullscreen' &&
    css`
    &.ant-modal {
      max-width: 100vw;
      top: 0;
      padding: 0;
    }

    .ant-modal-content {
      height: 100vh;
    }

    .ant-modal-body {
      /* 120px = modal header(64) + modal footer(56) */
      max-height: calc(100vh - 120px);
      overflow-y: auto;
    }
  `}

  .ant-modal-content {
  }

  .ant-modal-header {
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
  }

  .ant-modal-title {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    font-size: ${({ theme }) => theme.fontSize.LG}px;
  }

  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.LG}px;

    ${({ $size }) =>
      $size === 'xl' &&
      css`
      max-height: 80vh;
      overflow-y: auto;
    `}
  }

  .ant-modal-footer {
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    display: flex;
    justify-content: flex-end;
    align-items: center;
  }

  .ant-modal-close {
    &:hover {
    }
  }
`;
