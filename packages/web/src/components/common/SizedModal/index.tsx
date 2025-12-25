import { Modal, type ModalProps } from 'antd';
import { ModalSize, MODAL_WIDTHS } from '@/types/modal';

interface SizedModalProps extends Omit<ModalProps, 'width'> {
  size: ModalSize;
}

export const SizedModal: React.FC<SizedModalProps> = ({
  size,
  className,
  wrapClassName,
  centered = true,
  ...props
}) => (
  <Modal
    className={className ? `${size} ${className}` : size}
    wrapClassName={wrapClassName ? `${size} ${wrapClassName}` : size}
    width={MODAL_WIDTHS[size]}
    centered={centered}
    {...props}
  />
);
