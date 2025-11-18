import React, { useEffect, useRef } from 'react'

// Extend Window interface to include turnstile API
// Official Cloudflare Turnstile API: https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/
declare global {
  interface Window {
    turnstile?: {
      ready: (callback: () => void) => void
      render: (container: string | HTMLElement, options: TurnstileRenderOptions) => string
      reset: (widgetId: string) => void
      remove: (widgetId: string) => void
      getResponse: (widgetId: string) => string | undefined
      isExpired: (widgetId: string) => boolean
      execute: (container: string | HTMLElement, options?: TurnstileRenderOptions) => void
    }
  }
}

interface TurnstileRenderOptions {
  sitekey: string
  action?: string
  cData?: string
  callback?: (token: string) => void
  'error-callback'?: (errorCode?: string) => void
  'expired-callback'?: () => void
  'timeout-callback'?: () => void
  'before-interactive-callback'?: () => void
  'after-interactive-callback'?: () => void
  'unsupported-callback'?: () => void
  theme?: 'light' | 'dark' | 'auto'
  size?: 'normal' | 'flexible' | 'compact'
  tabindex?: number
  'response-field'?: boolean
  'response-field-name'?: string
  execution?: 'render' | 'execute'
  appearance?: 'always' | 'execute' | 'interaction-only'
  retry?: 'auto' | 'never'
  'retry-interval'?: number
  'refresh-expired'?: 'auto' | 'manual' | 'never'
  language?: string
}

export interface TurnstileProps {
  sitekey: string
  action?: string
  cData?: string
  theme?: 'light' | 'dark' | 'auto'
  size?: 'normal' | 'flexible' | 'compact'
  tabindex?: number
  execution?: 'render' | 'execute'
  appearance?: 'always' | 'execute' | 'interaction-only'
  retry?: 'auto' | 'never'
  retryInterval?: number
  refreshExpired?: 'auto' | 'manual' | 'never'
  language?: string
  responseField?: boolean
  responseFieldName?: string
  onVerify?: (token: string) => void
  onExpire?: () => void
  onError?: (errorCode?: string) => void
  onTimeout?: () => void
  onBeforeInteractive?: () => void
  onAfterInteractive?: () => void
  onUnsupported?: () => void
}

/**
 * Official Cloudflare Turnstile React wrapper component
 * Uses the official Cloudflare Turnstile script loaded via index.html
 *
 * Documentation: https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/
 *
 * Important: This component uses explicit rendering for proper lifecycle management in React/SPAs.
 * The script must be loaded with ?render=explicit parameter.
 */
export const Turnstile: React.FC<TurnstileProps> = ({
  sitekey,
  action,
  cData,
  theme = 'light',
  size = 'normal',
  tabindex,
  execution = 'render',
  appearance = 'always',
  retry = 'auto',
  retryInterval,
  refreshExpired = 'auto',
  language,
  responseField = true,
  responseFieldName = 'cf-turnstile-response',
  onVerify,
  onExpire,
  onError,
  onTimeout,
  onBeforeInteractive,
  onAfterInteractive,
  onUnsupported,
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const widgetIdRef = useRef<string | null>(null)
  const mountedRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true

    const renderTurnstile = () => {
      if (!window.turnstile || !containerRef.current || !mountedRef.current) {
        return
      }

      // Clean up existing widget if any
      if (widgetIdRef.current) {
        try {
          window.turnstile.remove(widgetIdRef.current)
          widgetIdRef.current = null
        } catch (e) {
          console.warn('[Turnstile] Failed to remove existing widget:', e)
        }
      }

      // Render new widget using official Cloudflare API
      try {
        const widgetId = window.turnstile.render(containerRef.current, {
          sitekey,
          action,
          cData,
          theme,
          size,
          tabindex,
          execution,
          appearance,
          retry,
          'retry-interval': retryInterval,
          'refresh-expired': refreshExpired,
          language,
          'response-field': responseField,
          'response-field-name': responseFieldName,
          callback: (token: string) => {
            if (mountedRef.current) {
              onVerify?.(token)
            }
          },
          'expired-callback': () => {
            if (mountedRef.current) {
              onExpire?.()
            }
          },
          'error-callback': (errorCode?: string) => {
            if (mountedRef.current) {
              onError?.(errorCode)
            }
          },
          'timeout-callback': () => {
            if (mountedRef.current) {
              onTimeout?.()
            }
          },
          'before-interactive-callback': () => {
            if (mountedRef.current) {
              onBeforeInteractive?.()
            }
          },
          'after-interactive-callback': () => {
            if (mountedRef.current) {
              onAfterInteractive?.()
            }
          },
          'unsupported-callback': () => {
            if (mountedRef.current) {
              onUnsupported?.()
            }
          },
        })

        widgetIdRef.current = widgetId
      } catch (error) {
        console.error('[Turnstile] Failed to render widget:', error)
        onError?.()
      }
    }

    // Wait for script to load, then use turnstile.ready()
    let attempts = 0
    const maxAttempts = 100 // 10 seconds
    const checkInterval = setInterval(() => {
      attempts++
      if (window.turnstile?.ready) {
        clearInterval(checkInterval)
        // Now safe to call ready() - script is loaded
        window.turnstile.ready(() => {
          renderTurnstile()
        })
      } else if (attempts >= maxAttempts) {
        clearInterval(checkInterval)
        console.error('[Turnstile] Script failed to load after 10 seconds')
        onError?.()
      }
    }, 100)

    // Cleanup on unmount
    return () => {
      clearInterval(checkInterval)
      mountedRef.current = false
      if (widgetIdRef.current && window.turnstile) {
        try {
          window.turnstile.remove(widgetIdRef.current)
        } catch (e) {
          console.warn('[Turnstile] Failed to cleanup widget:', e)
        }
      }
    }
  }, [
    sitekey,
    action,
    cData,
    theme,
    size,
    tabindex,
    execution,
    appearance,
    retry,
    retryInterval,
    refreshExpired,
    language,
    responseField,
    responseFieldName,
    onVerify,
    onExpire,
    onError,
    onTimeout,
    onBeforeInteractive,
    onAfterInteractive,
    onUnsupported,
  ])

  return <div ref={containerRef} />
}

export default Turnstile
