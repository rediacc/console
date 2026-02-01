import React from 'react';
import type { Platform } from '../../config/install';

const LinuxIcon: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12.5 2c-1.6 0-2.9 1.3-3.1 2.9-.5.2-.9.5-1.3.9C7.1 6.7 6.5 8 6.5 9.5v3c0 .8-.3 1.6-.8 2.2l-1.5 1.8c-.4.5-.2 1.1.1 1.5.3.3.7.5 1.2.5h2.7c.3 1.5 1.5 2.5 3 2.5h1.6c1.5 0 2.7-1 3-2.5h2.7c.5 0 .9-.2 1.2-.5.3-.4.5-1 .1-1.5l-1.5-1.8c-.5-.6-.8-1.4-.8-2.2v-3c0-1.5-.6-2.8-1.6-3.7-.4-.4-.8-.7-1.3-.9C14.4 3.3 13.1 2 12.5 2zm0 1.5c.8 0 1.5.7 1.5 1.5 0 .1 0 .2-.1.3-.5-.1-.9-.2-1.4-.2s-1 .1-1.4.2c0-.1-.1-.2-.1-.3 0-.8.7-1.5 1.5-1.5zm0 3.1c1.9 0 3.5 1.6 3.5 3.5v3c0 1.1.4 2.2 1.2 3l.8 1H6l.8-1c.7-.8 1.2-1.9 1.2-3v-3c0-1.9 1.6-3.5 3.5-3.5zM11 18.5h3c-.2.6-.9 1-1.5 1h-1.6c-.3 0-.7-.4-.9-1z" />
  </svg>
);

const AppleIcon: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M18.7 19.4c-.7 1-1.4 2-2.6 2-1.1 0-1.4-.7-2.7-.7-1.3 0-1.7.7-2.7.7-1.2 0-2.1-1.1-2.8-2.1-1.5-2.1-2.6-6-.1-8.6.8-1.1 2.1-1.7 3.4-1.8 1.1 0 2.1.7 2.7.7.7 0 1.9-.9 3.2-.7.5 0 2 .2 3 1.6-.1.1-1.8 1-1.8 3.1 0 2.4 2.1 3.2 2.1 3.2-.1.1-.3 1.1-1.1 2.2l.4.4zM15 3.7c.7-.8 1.1-2 1-3.1-1 0-2.2.7-2.9 1.5-.7.7-1.2 1.8-1.1 2.9 1.1.1 2.3-.5 3-1.3z" />
  </svg>
);

const WindowsIcon: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M3 5.5l7.5-1v7H3V5.5zm0 13l7.5 1v-7H3v6zm8.5 1.2L21 21V12.5h-9.5v7.2zm0-15.4v7.2H21V3l-9.5 1.3z" />
  </svg>
);

export const PLATFORM_ICON_MAP: Record<Platform, React.FC> = {
  linux: LinuxIcon,
  macos: AppleIcon,
  windows: WindowsIcon,
};
