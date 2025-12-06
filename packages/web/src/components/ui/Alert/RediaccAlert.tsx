import { forwardRef } from 'react';
import { StyledRediaccAlert, mapVariantToAntType } from './RediaccAlert.styles';
import type { RediaccAlertProps } from './RediaccAlert.types';

export const RediaccAlert = forwardRef<HTMLDivElement, RediaccAlertProps>(
  (
    {
      variant = 'info',
      size = 'md',
      showIcon = true,
      closable = false,
      banner = false,
      rounded = true,
      message,
      description,
      icon,
      onClose,
      children,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccAlert
        ref={ref}
        type={mapVariantToAntType(variant)}
        $variant={variant}
        $size={size}
        $rounded={rounded}
        $banner={banner}
        showIcon={showIcon}
        closable={closable}
        banner={banner}
        message={message ?? children}
        description={description}
        icon={icon}
        onClose={onClose}
        {...rest}
      />
    );
  }
);

RediaccAlert.displayName = 'RediaccAlert';
