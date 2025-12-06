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
      fullWidth = false,
      noPadding = false,
      children,
      onClick,
      ...rest
    },
    ref
  ) => {
    // Selectable cards should be interactive by default
    const isInteractive = interactive || variant === 'selectable';

    return (
      <StyledRediaccCard
        ref={ref}
        $variant={variant}
        $size={size}
        $selected={selected}
        $interactive={isInteractive}
        $fullWidth={fullWidth}
        $noPadding={noPadding}
        onClick={onClick}
        {...rest}
      >
        {children}
      </StyledRediaccCard>
    );
  }
);

RediaccCard.displayName = 'RediaccCard';
