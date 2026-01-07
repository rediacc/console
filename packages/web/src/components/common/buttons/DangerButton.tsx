import { Button } from 'antd';
import type { ButtonProps } from 'antd';

type DangerButtonProps = Omit<ButtonProps, 'type' | 'danger'>;

/**
 * Pre-configured danger button for destructive actions.
 * Use for delete, remove, or other dangerous operations.
 */
export const DangerButton: React.FC<DangerButtonProps> = (props) => (
  <Button type="primary" danger {...props} />
);
