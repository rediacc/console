import { forwardRef } from 'react';
import { StyledRediaccModal, resolveModalWidth } from './RediaccModal.styles';
import type { RediaccModalProps } from './RediaccModal.types';

export const RediaccModal = forwardRef<HTMLDivElement, RediaccModalProps>(
  (
    {
      size = 'md',
      variant = 'default',
      centered = true,
      closable = true,
      maskClosable = true,
      destroyOnClose = false,
      open,
      title,
      footer,
      onCancel,
      onOk,
      confirmLoading,
      okText,
      cancelText,
      children,
      zIndex,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccModal
        ref={ref}
        $size={size}
        $variant={variant}
        width={resolveModalWidth(size)}
        centered={centered}
        closable={closable}
        maskClosable={maskClosable}
        destroyOnClose={destroyOnClose}
        open={open}
        title={title}
        footer={footer}
        onCancel={onCancel}
        onOk={onOk}
        confirmLoading={confirmLoading}
        okText={okText}
        cancelText={cancelText}
        zIndex={zIndex}
        {...rest}
      >
        {children}
      </StyledRediaccModal>
    );
  }
);

RediaccModal.displayName = 'RediaccModal';
