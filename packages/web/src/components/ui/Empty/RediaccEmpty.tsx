import { forwardRef } from 'react';
import { Empty } from 'antd';
import { EmptyAction, EmptyTitle, StyledRediaccEmpty } from './RediaccEmpty.styles';
import type { RediaccEmptyProps } from './RediaccEmpty.types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const RediaccEmptyComponent = forwardRef<any, RediaccEmptyProps>(
  ({ variant = 'default', size = 'md', title, description, image, action, ...rest }, ref) => {
    // Build description with optional title
    const descriptionContent = (
      <>
        {title && <EmptyTitle>{title}</EmptyTitle>}
        {description}
      </>
    );

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const Component = StyledRediaccEmpty as any;
    return (
      <Component
        ref={ref}
        $variant={variant}
        $size={size}
        image={variant === 'minimal' ? null : image}
        description={descriptionContent}
        {...rest}
      >
        {action && <EmptyAction>{action}</EmptyAction>}
      </Component>
    );
  }
);

RediaccEmptyComponent.displayName = 'RediaccEmpty';

// Export with static properties from antd Empty
export const RediaccEmpty = Object.assign(RediaccEmptyComponent, {
  PRESENTED_IMAGE_DEFAULT: Empty.PRESENTED_IMAGE_DEFAULT,
  PRESENTED_IMAGE_SIMPLE: Empty.PRESENTED_IMAGE_SIMPLE,
});
