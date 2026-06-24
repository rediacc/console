import React from 'react';
import { ACCOUNT_PATH } from '../config/constants';
import { getLocalAccountUrl } from '../utils/account-url';

declare global {
  interface Window {
    openRegionPicker?: (targetPath: string) => void;
  }
}

export interface AccountCtaProps {
  origin?: string;
  label: string;
  className?: string;
  ariaLabel?: string;
  tabIndex?: number;
  track?: {
    event?: string;
    label?: string;
    dest?: string;
  };
  onClick?: () => void;
}

export const AccountCta: React.FC<AccountCtaProps> = ({
  origin,
  label,
  className,
  ariaLabel,
  tabIndex,
  track,
  onClick,
}) => {
  const accountUrl = getLocalAccountUrl(origin);

  const trackProps = {
    'data-track': track?.event,
    'data-track-label': track?.label,
    'data-track-dest': track?.dest,
  };

  const handleClick = (): void => {
    onClick?.();
    window.openRegionPicker?.(ACCOUNT_PATH);
  };

  if (accountUrl) {
    return (
      <a
        href={accountUrl}
        className={className}
        aria-label={ariaLabel ?? label}
        tabIndex={tabIndex}
        onClick={onClick}
        {...trackProps}
      >
        {label}
      </a>
    );
  }

  return (
    <button
      type="button"
      className={className}
      aria-label={ariaLabel ?? label}
      tabIndex={tabIndex}
      onClick={handleClick}
      {...trackProps}
    >
      {label}
    </button>
  );
};
