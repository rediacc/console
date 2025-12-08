import { Empty } from 'antd';
import { EmptyAction, EmptyTitle, StyledRediaccEmpty } from './RediaccEmpty.styles';
import type { RediaccEmptyProps } from './RediaccEmpty.types';

const RediaccEmptyComponent: React.FC<RediaccEmptyProps> = ({
  variant = 'default',
  size = 'md',
  title,
  description,
  image,
  action,
  ...rest
}) => {
  // Build description with optional title
  const descriptionContent = (
    <>
      {title && <EmptyTitle>{title}</EmptyTitle>}
      {description}
    </>
  );

  return (
    <StyledRediaccEmpty
      $variant={variant}
      $size={size}
      image={variant === 'minimal' ? null : image}
      description={descriptionContent}
      {...rest}
    >
      {action && <EmptyAction>{action}</EmptyAction>}
    </StyledRediaccEmpty>
  );
};

RediaccEmptyComponent.displayName = 'RediaccEmpty';

// Export with static properties from antd Empty
export const RediaccEmpty = Object.assign(RediaccEmptyComponent, {
  PRESENTED_IMAGE_DEFAULT: Empty.PRESENTED_IMAGE_DEFAULT,
  PRESENTED_IMAGE_SIMPLE: Empty.PRESENTED_IMAGE_SIMPLE,
});
