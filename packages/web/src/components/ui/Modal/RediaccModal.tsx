import { forwardRef } from 'react';
import { resolveModalWidth, StyledRediaccModal } from './RediaccModal.styles';
import type { RediaccModalProps } from './RediaccModal.types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccModal = forwardRef<any, RediaccModalProps>(
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
      okButtonProps,
      cancelButtonProps,
      extra,
      children,
      zIndex,
      width,
      ...rest
    },
    ref
  ) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const Component = StyledRediaccModal as any;
    return (
      <Component
        ref={ref}
        $size={size}
        $variant={variant}
        width={width ?? resolveModalWidth(size)}
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
        okButtonProps={okButtonProps}
        cancelButtonProps={cancelButtonProps}
        extra={extra}
        zIndex={zIndex}
        {...rest}
      >
        {children}
      </Component>
    );
  }
);

RediaccModal.displayName = 'RediaccModal';
