import { resolveModalWidth, StyledRediaccModal } from './RediaccModal.styles';
import type { RediaccModalProps } from './RediaccModal.types';

export const RediaccModal: React.FC<RediaccModalProps> = ({
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
  extra: _extra, // Accept but don't use - antd Modal doesn't support this
  children,
  zIndex,
  width,
  ...rest
}) => {
  return (
    <StyledRediaccModal
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
      zIndex={zIndex}
      {...rest}
    >
      {children}
    </StyledRediaccModal>
  );
};

RediaccModal.displayName = 'RediaccModal';
