import styled, { css, keyframes } from 'styled-components';
import { Modal as AntModal } from 'antd';
import type { StyledTheme } from '@/styles/styledTheme';
import type { ModalSize, ModalVariant } from './RediaccModal.types';

export const fadeInAnimation = keyframes`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

export const resolveModalWidth = (size: ModalSize = 'md'): string | number => {
  switch (size) {
    case 'sm': return 400;
    case 'lg': return 800;
    case 'xl': return 1200;
    case 'fullscreen': return '100vw';
    case 'md':
    default: return 520;
  }
};

export const StyledRediaccModal = styled(AntModal)<{
  $size: ModalSize;
  $variant: ModalVariant;
}>`
  ${({ $size }) => $size === 'fullscreen' && css`
    &.ant-modal {
      max-width: 100vw;
      top: 0;
      padding: 0;
      margin: 0;
    }

    .ant-modal-content {
      height: 100vh;
      border-radius: 0;
    }

    .ant-modal-body {
      max-height: calc(100vh - 120px);
      overflow-y: auto;
    }
  `}

  .ant-modal-content {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    box-shadow: ${({ theme }) => theme.shadows.MODAL};
    animation: ${fadeInAnimation} 0.3s ease-in-out;
  }

  .ant-modal-header {
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    border-radius: ${({ theme }) => `${theme.borderRadius.XL}px ${theme.borderRadius.XL}px 0 0`};
  }

  .ant-modal-title {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    font-size: ${({ theme }) => theme.fontSize.LG}px;
  }

  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.LG}px;

    ${({ $size }) => $size === 'xl' && css`
      max-height: 80vh;
      overflow-y: auto;
    `}
  }

  .ant-modal-footer {
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.SM}px;
    border-radius: ${({ theme }) => `0 0 ${theme.borderRadius.XL}px ${theme.borderRadius.XL}px`};
  }

  .ant-modal-close {
    color: ${({ theme }) => theme.colors.textTertiary};

    &:hover {
      color: ${({ theme }) => theme.colors.textSecondary};
      background-color: ${({ theme }) => theme.colors.bgHover};
    }
  }
`;
