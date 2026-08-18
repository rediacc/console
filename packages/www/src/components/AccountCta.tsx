import React from 'react';
import { ACCOUNT_PATH } from '../config/constants';
import { getLocalAccountUrl } from '../utils/account-url';

export interface AccountCtaProps {
  origin?: string;
  label: string;
  className?: string;
  ariaLabel?: string;
  tabIndex?: number;
  /**
   * ARIA role for the rendered element. The nav's split-button menu needs
   * `menuitem` here: this component decides at render time whether it emits an
   * <a> or a <button>, so the role cannot be put on a wrapper without lying
   * about which element is the menu item.
   */
  role?: string;
  /** Ref to the rendered element, for roving-focus menus. */
  elementRef?: (el: HTMLElement | null) => void;
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
  role,
  elementRef,
  track,
  onClick,
}) => {
  const accountUrl = getLocalAccountUrl(origin);

  const trackProps = {
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
        ref={elementRef}
        href={accountUrl}
        className={className}
        aria-label={ariaLabel ?? label}
        tabIndex={tabIndex}
        role={role}
        onClick={onClick}
        data-track={track?.event}
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
      data-track={track?.event}
      {...trackProps}
    >
      {label}
    </button>
  );
};
