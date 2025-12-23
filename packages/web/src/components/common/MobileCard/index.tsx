import type { ReactNode } from 'react';
import { Card, Flex } from 'antd';

export interface MobileCardProps {
  /** Content to display on the left side of the card */
  children: ReactNode;
  /** Optional click handler - when present, adds cursor-pointer styling */
  onClick?: () => void;
  /** Optional additional CSS classes (w-full is always included) */
  className?: string;
  /** Optional action buttons/dropdown to display on the right side */
  actions?: ReactNode;
}

export function MobileCard({ children, onClick, className, actions }: MobileCardProps) {
  const baseClassName = 'w-full';
  const cursorClassName = onClick ? 'cursor-pointer' : '';
  const combinedClassName = [baseClassName, cursorClassName, className].filter(Boolean).join(' ');

  return (
    <Card size="small" className={combinedClassName} onClick={onClick}>
      <Flex justify="space-between" align="flex-start">
        <Flex vertical gap={4} className="flex-1 min-w-0">
          {children}
        </Flex>
        {actions}
      </Flex>
    </Card>
  );
}

export default MobileCard;
