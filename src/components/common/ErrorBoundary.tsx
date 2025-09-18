import React, { Component, ReactNode } from 'react'
import { Result, Button } from 'antd'
import { ReloadOutlined, BugOutlined } from '@ant-design/icons'
import { telemetryService } from '@/services/telemetryService'

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
  errorInfo?: React.ErrorInfo
  errorId?: string
}

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: (error: Error, errorInfo: React.ErrorInfo, retry: () => void) => ReactNode
}

/**
 * Error boundary that catches JavaScript errors anywhere in the child component tree,
 * logs those errors, sends them to telemetry, and displays a fallback UI.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // Update state so the next render will show the fallback UI
    const errorId = `error_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`
    return {
      hasError: true,
      error,
      errorId
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log the error details
    console.error('ErrorBoundary caught an error:', error, errorInfo)

    // Track error in telemetry
    try {
      telemetryService.trackError(error, {
        component_stack: errorInfo.componentStack,
        error_boundary: 'global',
        page_url: window.location.href,
        user_agent: navigator.userAgent,
        timestamp: Date.now(),
        error_id: this.state.errorId || 'unknown',
        react_error_info: JSON.stringify({
          componentStack: errorInfo.componentStack.substring(0, 1000), // Limit length
          // Add any other relevant React error info
        })
      })
    } catch (telemetryError) {
      // Don't let telemetry errors crash the error boundary
      console.warn('Failed to track error in telemetry:', telemetryError)
    }

    // Store error info in state for display
    this.setState({
      error,
      errorInfo
    })
  }

  handleRetry = () => {
    // Track retry attempt
    try {
      telemetryService.trackEvent('error_boundary.retry', {
        error_id: this.state.errorId || 'unknown',
        error_type: this.state.error?.constructor.name || 'unknown',
        page_url: window.location.href
      })
    } catch (error) {
      console.warn('Failed to track retry in telemetry:', error)
    }

    // Reset the error boundary
    this.setState({ hasError: false, error: undefined, errorInfo: undefined, errorId: undefined })
  }

  handleReload = () => {
    // Track page reload
    try {
      telemetryService.trackEvent('error_boundary.reload', {
        error_id: this.state.errorId || 'unknown',
        error_type: this.state.error?.constructor.name || 'unknown',
        page_url: window.location.href
      })
    } catch (error) {
      console.warn('Failed to track reload in telemetry:', error)
    }

    // Reload the page
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      // If a custom fallback is provided, use it
      if (this.props.fallback && this.state.error && this.state.errorInfo) {
        return this.props.fallback(this.state.error, this.state.errorInfo, this.handleRetry)
      }

      // Default error UI
      return (
        <div style={{
          padding: '50px',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '400px'
        }}>
          <Result
            status="error"
            title="Something went wrong"
            subTitle={
              <div>
                <p>An unexpected error occurred. This has been automatically reported.</p>
                {import.meta.env.DEV && this.state.error && (
                  <details style={{
                    marginTop: '16px',
                    padding: '12px',
                    backgroundColor: '#f5f5f5',
                    borderRadius: '4px',
                    textAlign: 'left',
                    fontSize: '12px',
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap'
                  }}>
                    <summary style={{ cursor: 'pointer', marginBottom: '8px' }}>
                      Error Details (Development Mode)
                    </summary>
                    <div>
                      <strong>Error:</strong> {this.state.error.message}
                      <br />
                      <strong>Stack:</strong> {this.state.error.stack}
                      {this.state.errorInfo && (
                        <>
                          <br />
                          <strong>Component Stack:</strong> {this.state.errorInfo.componentStack}
                        </>
                      )}
                    </div>
                  </details>
                )}
              </div>
            }
            extra={[
              <Button key="retry" onClick={this.handleRetry} icon={<BugOutlined />}>
                Try Again
              </Button>,
              <Button key="reload" type="primary" onClick={this.handleReload} icon={<ReloadOutlined />}>
                Reload Page
              </Button>
            ]}
          />
        </div>
      )
    }

    return this.props.children
  }
}

/**
 * Hook-based error boundary wrapper for functional components
 */
export const withErrorBoundary = <P extends object>(
  Component: React.ComponentType<P>,
  fallback?: (error: Error, errorInfo: React.ErrorInfo, retry: () => void) => ReactNode
) => {
  const WrappedComponent: React.FC<P> = (props) => {
    return (
      <ErrorBoundary fallback={fallback}>
        <Component {...props} />
      </ErrorBoundary>
    )
  }

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name})`
  return WrappedComponent
}

export default ErrorBoundary