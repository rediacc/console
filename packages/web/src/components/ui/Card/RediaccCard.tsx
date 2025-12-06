import { forwardRef } from 'react';
import { StyledRediaccCard } from './RediaccCard.styles';
import type { RediaccCardProps } from './RediaccCard.types';

export const RediaccCard = forwardRef<HTMLDivElement, RediaccCardProps>(
  (
    {
      variant = 'default',
      size = 'md',
      selected = false,
      interactive = false,
      hoverable = false,
      fullWidth = false,
      noPadding = false,
      title,
      extra,
      children,
      onClick,
      ...rest
    },
    ref
  ) => {
    // Selectable cards should be interactive by default
    // hoverable is an alias for interactive
    const isInteractive = interactive || hoverable || variant === 'selectable';

    return (
      <StyledRediaccCard
        ref={ref}
        $variant={variant}
        $size={size}
        $selected={selected}
        $interactive={isInteractive}
        $fullWidth={fullWidth}
        $noPadding={noPadding}
        title={title}
        extra={extra}
        onClick={onClick}
        {...rest}
      >
        {children}
      </StyledRediaccCard>
    );
  }
);

RediaccCard.displayName = 'RediaccCard';
