import { RightOutlined } from '@/utils/optimizedIcons';

interface ExpandIconProps {
  isExpanded: boolean;
}

export const ExpandIcon = ({ isExpanded }: ExpandIconProps) => (
  <RightOutlined className={`expand-icon ${isExpanded ? 'expand-icon-rotated' : ''}`} />
);
