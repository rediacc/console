import React, { Component, ReactNode } from 'react';
import { BugOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Flex, Result, Typography } from 'antd';
import i18n from '@/i18n/config';
import { telemetryService } from '@/services/telemetryService';

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
  errorInfo?: React.ErrorInfo;
  errorId?: string;
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, errorInfo: React.ErrorInfo, retry: () => void) => ReactNode;
}

/**
 * Error boundary that catches JavaScript errors anywhere in the child component tree,
 * logs those errors, sends them to telemetry, and displays a fallback UI.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // Update state so the next render will show the fallback UI
    const errorId = `error_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    return {
      hasError: true,
      error,
      errorId,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log the error details
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    // Track error in telemetry
    try {
      telemetryService.trackError(error, {
        component_stack: errorInfo.componentStack || undefined,
        error_boundary: 'global',
        page_url: window.location.href,
        user_agent: navigator.userAgent,
        timestamp: Date.now(),
        error_id: this.state.errorId || 'unknown',
        react_error_info: JSON.stringify({
          componentStack: errorInfo.componentStack?.substring(0, 1000) || 'N/A', // Limit length
          // Add any other relevant React error info
        }),
      });
    } catch (telemetryError) {
      // Don't let telemetry errors crash the error boundary
      console.warn('Failed to track error in telemetry:', telemetryError);
    }

    // Store error info in state for display
    this.setState({
      error,
      errorInfo,
    });
  }

  handleRetry = () => {
    // Track retry attempt
    try {
      telemetryService.trackEvent('error_boundary.retry', {
        error_id: this.state.errorId || 'unknown',
        error_type: this.state.error?.constructor.name || 'unknown',
        page_url: window.location.href,
      });
    } catch (error) {
      console.warn('Failed to track retry in telemetry:', error);
    }

    // Reset the error boundary
    this.setState({ hasError: false, error: undefined, errorInfo: undefined, errorId: undefined });
  };

  handleReload = () => {
    // Track page reload
    try {
      telemetryService.trackEvent('error_boundary.reload', {
        error_id: this.state.errorId || 'unknown',
        error_type: this.state.error?.constructor.name || 'unknown',
        page_url: window.location.href,
      });
    } catch (error) {
      console.warn('Failed to track reload in telemetry:', error);
    }

    // Reload the page
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      // If a custom fallback is provided, use it
      if (this.props.fallback && this.state.error && this.state.errorInfo) {
        return this.props.fallback(this.state.error, this.state.errorInfo, this.handleRetry);
      }

      // Default error UI
      return (
        <Flex
          justify="center"
          align="center"
          style={{
            padding: 24,
            minHeight: 320,
          }}
        >
          <Result
            status="error"
            title={i18n.t('common:errorBoundary.title')}
            subTitle={
              <Flex vertical>
                <Typography.Text>{i18n.t('common:errorBoundary.description')}</Typography.Text>
                {import.meta.env.DEV && this.state.error && (
                  <details
                    style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontFamily: 'monospace',
                    }}
                  >
                    <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
                      {i18n.t('common:errorBoundary.errorDetails')}
                    </summary>
                    <Flex vertical gap={8}>
                      <Typography.Text strong>Error:</Typography.Text> {this.state.error.message}
                      <br />
                      <Typography.Text strong>Stack:</Typography.Text> {this.state.error.stack}
                      {this.state.errorInfo && (
                        <>
                          <br />
                          <Typography.Text strong>Component Stack:</Typography.Text>{' '}
                          {this.state.errorInfo.componentStack}
                        </>
                      )}
                    </Flex>
                  </details>
                )}
              </Flex>
            }
            extra={[
              <Button key="retry" onClick={this.handleRetry} icon={<BugOutlined />}>
                {i18n.t('common:errorBoundary.tryAgain')}
              </Button>,
              <Button
                key="reload"
                type="primary"
                onClick={this.handleReload}
                icon={<ReloadOutlined />}
              >
                {i18n.t('common:errorBoundary.reloadPage')}
              </Button>,
            ]}
          />
        </Flex>
      );
    }

    return this.props.children;
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
    );
  };

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name})`;
  return WrappedComponent;
};
