import React, { useEffect, useRef } from 'react';

declare global {
  interface Window {
    turnstile?: {
      render: (container: HTMLElement, options: Record<string, unknown>) => string;
      remove: (id: string) => void;
      ready: (cb: () => void) => void;
    };
  }
}

const TURNSTILE_SCRIPT_URL =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

async function ensureTurnstileScript(): Promise<void> {
  if (window.turnstile) return;

  const existing = document.querySelector(`script[src="${TURNSTILE_SCRIPT_URL}"]`);
  if (existing) {
    await new Promise<void>((resolve) => {
      const interval = window.setInterval(() => {
        if (window.turnstile) {
          window.clearInterval(interval);
          resolve();
        }
      }, 50);
    });
    return;
  }

  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = TURNSTILE_SCRIPT_URL;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Turnstile script'));
    document.head.appendChild(script);
  });
}

interface Props {
  siteKey: string;
  action: string;
  onVerify: (token: string) => void;
  onExpire: () => void;
}

const TurnstileWidget: React.FC<Props> = ({ siteKey, action, onVerify, onExpire }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const mount = async () => {
      await ensureTurnstileScript();
      if (!mounted || !window.turnstile || !containerRef.current) return;
      window.turnstile.ready(() => {
        if (!mounted || !window.turnstile || !containerRef.current) return;
        if (widgetIdRef.current) {
          window.turnstile.remove(widgetIdRef.current);
          widgetIdRef.current = null;
        }
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action,
          callback: (token: string) => onVerify(token),
          'expired-callback': () => onExpire(),
          'error-callback': () => onExpire(),
        });
      });
    };

    mount().catch(() => onExpire());
    return () => {
      mounted = false;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
      }
      widgetIdRef.current = null;
    };
  }, [action, onExpire, onVerify, siteKey]);

  return <div ref={containerRef} />;
};

export default TurnstileWidget;
