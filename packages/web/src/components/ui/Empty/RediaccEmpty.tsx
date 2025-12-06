import { forwardRef } from 'react';
import { StyledRediaccEmpty, EmptyTitle, EmptyAction } from './RediaccEmpty.styles';
import type { RediaccEmptyProps } from './RediaccEmpty.types';

export const RediaccEmpty = forwardRef<HTMLDivElement, RediaccEmptyProps>(
  (
    {
      variant = 'default',
      size = 'md',
      title,
      description,
      image,
      action,
      ...rest
    },
    ref
  ) => {
    // Build description with optional title
    const descriptionContent = (
      <>
        {title && <EmptyTitle>{title}</EmptyTitle>}
        {description}
      </>
    );

    return (
      <StyledRediaccEmpty
        ref={ref}
        $variant={variant}
        $size={size}
        image={variant === 'minimal' ? null : image}
        description={descriptionContent}
        {...rest}
      >
        {action && <EmptyAction>{action}</EmptyAction>}
      </StyledRediaccEmpty>
    );
  }
);

RediaccEmpty.displayName = 'RediaccEmpty';
