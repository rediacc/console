import { Button } from 'antd';
import type { ButtonProps } from 'antd';

interface SubmitButtonProps extends Omit<ButtonProps, 'type' | 'htmlType'> {
  /** Children are optional - defaults to "Submit" */
  children?: React.ReactNode;
}

/**
 * Pre-configured submit button with primary styling.
 * Use in forms for the main submission action.
 */
export const SubmitButton: React.FC<SubmitButtonProps> = ({ children = 'Submit', ...props }) => (
  <Button type="primary" htmlType="submit" {...props}>
    {children}
  </Button>
);
