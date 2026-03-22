import type { BreadcrumbProps } from 'antd';
import { Breadcrumb, Card, Flex } from 'antd';
import React, { type ReactNode } from 'react';

interface ResourcePageLayoutProps {
  breadcrumbItems: BreadcrumbProps['items'];
  breadcrumbTestId: string;
  header: ReactNode;
  tags?: ReactNode;
  actions?: ReactNode;
  content: ReactNode;
  drawer?: ReactNode;
}

export const ResourcePageLayout: React.FC<ResourcePageLayoutProps> = ({
  breadcrumbItems,
  breadcrumbTestId,
  header,
  tags,
  actions,
  content,
  drawer,
}) => (
  <Flex vertical>
    <Card>
      <Flex vertical>
        <Flex vertical>
          <Breadcrumb items={breadcrumbItems} data-testid={breadcrumbTestId} />

          <Flex align="center" justify="space-between" wrap>
            <Flex vertical className="flex-1 min-w-0">
              {header}
              {tags}
            </Flex>

            {actions ? (
              <Flex align="center" wrap>
                {actions}
              </Flex>
            ) : null}
          </Flex>
        </Flex>

        <Flex className="flex-1 overflow-hidden relative">
          <Flex vertical className="w-full h-full overflow-auto">
            {content}
          </Flex>
          {drawer}
        </Flex>
      </Flex>
    </Card>
  </Flex>
);
