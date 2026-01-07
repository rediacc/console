import { Flex, Typography } from 'antd';

interface PageHeaderProps {
  /** Page title text */
  title: React.ReactNode;
  /** Optional subtitle/description text */
  subtitle?: React.ReactNode;
  /** Optional data-testid for testing */
  'data-testid'?: string;
}

/**
 * Standardized page header with title and optional subtitle.
 * Uses Typography.Title level={4} for consistent styling across pages.
 */
export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  'data-testid': testId,
}) => (
  <Flex vertical className="gap-0" data-testid={testId}>
    <Typography.Title level={4} className="mb-0">
      {title}
    </Typography.Title>
    {subtitle && <Typography.Text type="secondary">{subtitle}</Typography.Text>}
  </Flex>
);

export default PageHeader;
