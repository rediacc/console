import { Flex } from 'antd';
import React, { ReactNode, useEffect, useRef } from 'react';
import { useTelemetry } from '@/components/common/TelemetryProvider';

type TelemetryAttributes = Record<string, string | number | boolean>;

interface ClickContext {
  shouldTrack: true;
  target: string;
  elementType: string;
  text: string;
  testId?: string;
  customData: TelemetryAttributes;
}

type ClickContextResult = ClickContext | { shouldTrack: false };

interface FormContext {
  formName: string;
  testId?: string;
}

interface InteractionTrackerProps {
  children: ReactNode;
}

/**
 * Global interaction tracker that automatically captures user interactions
 * without requiring individual components to add tracking code.
 *
 * This component wraps the entire app and listens for:
 * - Button clicks
 * - Form submissions
 * - Link clicks
 * - Modal interactions
 * - Table actions
 *
 * It intelligently extracts context from DOM elements and their data attributes.
 */
export const InteractionTracker: React.FC<InteractionTrackerProps> = ({ children }) => {
  const { trackUserAction, isInitialized } = useTelemetry();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isInitialized || !containerRef.current) return;

    const container = containerRef.current;

    const handleClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (target === null) return;

      // Extract contextual information
      const context = extractClickContext(target);
      if (!context.shouldTrack) return;

      const details: TelemetryAttributes = {
        element_type: context.elementType,
        element_text: context.text,
        page_url: window.location.pathname,
      };

      if (context.testId) {
        details.data_testid = context.testId;
      }

      Object.entries(context.customData).forEach(([key, value]) => {
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
          details[key] = value;
        }
      });

      trackUserAction('click', context.target, details);
    };

    const handleSubmit = (event: SubmitEvent) => {
      const target = event.target as HTMLFormElement | null;
      if (target === null) return;

      const context = extractFormContext(target);

      const details: TelemetryAttributes = {
        form_action: target.action || 'unknown',
        form_method: target.method || 'GET',
        field_count: target.elements.length,
        page_url: window.location.pathname,
      };

      if (context.testId) {
        details.data_testid = context.testId;
      }

      trackUserAction('form_submit', context.formName, details);
    };

    // Use capture phase to catch events before they bubble
    container.addEventListener('click', handleClick, { capture: true });
    container.addEventListener('submit', handleSubmit, { capture: true });

    return () => {
      container.removeEventListener('click', handleClick, { capture: true });
      container.removeEventListener('submit', handleSubmit, { capture: true });
    };
  }, [isInitialized, trackUserAction]);

  return (
    <Flex ref={containerRef} className="w-full h-full">
      {children}
    </Flex>
  );
};

/**
 * Extracts contextual information from a clicked element
 */
function extractClickContext(element: HTMLElement): ClickContextResult {
  // Skip tracking for certain elements to avoid noise
  const skipSelectors = [
    'input[type="text"]',
    'input[type="email"]',
    'input[type="password"]',
    'textarea',
    '.ant-select-dropdown',
    '.ant-tooltip',
    '.ant-popover',
    'svg path', // Skip SVG path elements
  ];

  if (skipSelectors.some((selector) => element.matches(selector))) {
    return { shouldTrack: false };
  }

  const clickableElement = findClickableParent(element);

  const elementType = getElementType(clickableElement);
  const text = extractElementText(clickableElement);
  const testId =
    clickableElement.getAttribute('data-testid') ??
    clickableElement.closest('[data-testid]')?.getAttribute('data-testid') ??
    undefined;

  const customData: TelemetryAttributes = {};
  Array.from(clickableElement.attributes).forEach((attr) => {
    if (attr.name.startsWith('data-track-')) {
      const key = attr.name.replace('data-track-', '');
      customData[key] = attr.value;
    }
  });

  return {
    shouldTrack: true,
    target: testId ?? (text || elementType),
    elementType,
    text,
    testId,
    customData,
  };
}

/**
 * Finds the most relevant clickable parent element
 */
function findClickableParent(element: HTMLElement): HTMLElement {
  const clickableSelectors = [
    'button',
    'a',
    '[role="button"]',
    '[role="menuitem"]',
    '[role="tab"]',
    '.ant-btn',
    '.ant-menu-item',
    '.ant-table-row',
    '.ant-card',
    '.ant-list-item',
  ];

  let current: HTMLElement | null = element;

  while (current && current !== document.body) {
    if (clickableSelectors.some((selector) => current!.matches(selector))) {
      return current;
    }
    current = current.parentElement;
  }

  return element;
}

/**
 * Determines the type of element that was clicked
 */
function getElementType(element: HTMLElement): string {
  if (element.matches('button, .ant-btn')) return 'button';
  if (element.matches('a')) return 'link';
  if (element.matches('.ant-menu-item')) return 'menu_item';
  if (element.matches('.ant-table-row')) return 'table_row';
  if (element.matches('.ant-card')) return 'card';
  if (element.matches('.ant-list-item')) return 'list_item';
  if (element.matches('[role="tab"]')) return 'tab';
  if (element.matches('[role="button"]')) return 'button';
  if (element.matches('input')) return 'input';
  if (element.matches('select')) return 'select';

  return element.tagName.toLowerCase();
}

/**
 * Extracts meaningful text from an element
 */
function extractElementText(element: HTMLElement): string {
  // For buttons, prefer aria-label or title
  const ariaLabel = element.getAttribute('aria-label');
  if (ariaLabel) return ariaLabel.substring(0, 50);

  const title = element.getAttribute('title');
  if (title) return title.substring(0, 50);

  // For links, get href if no text
  if (element.matches('a')) {
    const href = element.getAttribute('href');
    // textContent can be null at runtime for certain DOM nodes
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (href && !element.textContent?.trim()) {
      return href.substring(0, 50);
    }
  }

  // Get text content, but limit length (textContent can be null at runtime)
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  const text = element.textContent?.trim() ?? '';
  return text.substring(0, 50);
}

/**
 * Extracts contextual information from a form
 */
function extractFormContext(form: HTMLFormElement): FormContext {
  const testId =
    form.getAttribute('data-testid') ??
    form.closest('[data-testid]')?.getAttribute('data-testid') ??
    undefined;

  // Try to determine form name from various sources - using || for empty string coalescing
  const formName =
    // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty strings should fall through
    form.name || form.id || testId || form.getAttribute('aria-label') || 'unknown_form';

  return {
    formName,
    testId,
  };
}
