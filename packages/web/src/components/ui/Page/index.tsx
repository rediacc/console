/**
 * Page-level layout components
 *
 * Base building blocks for page structure:
 * - PageWrapper: Main container for all pages
 * - SectionStack: Vertical stack for grouping related content
 * - SectionHeading: Heading for page sections
 * - SectionHeaderRow: Row for section headers with actions
 */

import { Typography } from 'antd';
import styled from 'styled-components';
import { PageContainer, SectionHeaderRow as PrimitiveSectionHeaderRow } from '@/styles/primitives';

const { Title } = Typography;

export const SectionHeaderRow = PrimitiveSectionHeaderRow;

/**
 * PageWrapper - Main container for all pages
 * Use this as the root element in your page components
 */
export const PageWrapper = styled(PageContainer)`
  display: flex;
  flex-direction: column;
`;

/**
 * SectionStack - Vertical stack for grouping related content
 * Use for major page sections
 */
export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

/**
 * SectionHeading - Heading for page sections
 */
export const SectionHeading = styled(Title)`
  && {
  }
`;
