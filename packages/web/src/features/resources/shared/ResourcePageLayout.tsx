import React, { type ReactNode } from 'react';
import { Breadcrumb, Card, Flex } from 'antd';
import {
  ResourceBody,
  ResourceBodyContent,
  ResourceHeaderText,
} from './ResourcePageLayout.styled';
import type { BreadcrumbProps } from 'antd';

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
            <ResourceHeaderText vertical>
              {header}
              {tags}
            </ResourceHeaderText>

            {actions ? (
              <Flex align="center" wrap>
                {actions}
              </Flex>
            ) : null}
          </Flex>
        </Flex>

        <ResourceBody>
          <ResourceBodyContent vertical>
            {content}
          </ResourceBodyContent>
          {drawer}
        </ResourceBody>
      </Flex>
    </Card>
  </Flex>
);
