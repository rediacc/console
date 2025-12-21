import React from 'react';
import { Button, Card, Divider, Flex, Typography } from 'antd';

const { Title, Text } = Typography;
const PANEL_WIDTH = 520;

export const DetailPanelSurface: React.FC<
  React.ComponentProps<typeof Flex> & { $splitView?: boolean; $visible?: boolean }
> = ({ $splitView, $visible = true, style, ...props }) => (
  <Flex
    vertical
    style={{
      height: '100%',
      position: $splitView ? 'relative' : 'fixed',
      top: $splitView ? undefined : 0,
      right: $splitView ? undefined : $visible ? 0 : -PANEL_WIDTH,
      bottom: $splitView ? undefined : 0,
      width: $splitView ? '100%' : PANEL_WIDTH,
      maxWidth: '100vw',
      zIndex: 1000,
      ...style,
    }}
    {...props}
  />
);

export const DetailPanelHeader = (props: React.ComponentProps<typeof Flex>) => (
  <Flex vertical style={{ position: 'sticky', top: 0, zIndex: 10 }} {...props} />
);

export const DetailPanelHeaderRow = (props: React.ComponentProps<typeof Flex>) => (
  <Flex justify="space-between" align="center" style={{ width: '100%' }} {...props} />
);

export const DetailPanelTitleGroup = (props: React.ComponentProps<typeof Flex>) => (
  <Flex align="center" {...props} />
);

export const DetailPanelTitle = (props: React.ComponentProps<typeof Title>) => (
  <Title level={4} {...props} />
);

export const DetailPanelCollapseButton = (props: React.ComponentProps<typeof Button>) => (
  <Button type="text" {...props} />
);

export const DetailPanelTagGroup = (props: React.ComponentProps<typeof Flex>) => (
  <Flex wrap {...props} />
);

export const DetailPanelBody = (props: React.ComponentProps<typeof Flex>) => (
  <Flex vertical {...props} />
);

export const DetailPanelSectionHeader = (props: React.ComponentProps<typeof Flex>) => (
  <Flex align="center" {...props} />
);

export const DetailPanelSectionTitle = (props: React.ComponentProps<typeof Title>) => (
  <Title level={5} {...props} />
);

export const DetailPanelSectionCard = (props: React.ComponentProps<typeof Card>) => (
  <Card size="small" {...props} />
);

export const DetailPanelFieldList = (props: React.ComponentProps<typeof Flex>) => (
  <Flex vertical style={{ width: '100%' }} {...props} />
);

export const DetailPanelFieldRow = (props: React.ComponentProps<typeof Flex>) => (
  <Flex justify="space-between" align="baseline" style={{ width: '100%' }} {...props} />
);

export const DetailPanelFieldLabel: React.FC<
  React.ComponentProps<typeof Text> & { $minWidth?: number }
> = ({ $minWidth = 160, style, ...props }) => (
  <Text type="secondary" style={{ minWidth: $minWidth, flexShrink: 0, letterSpacing: '0.01em', ...style }} {...props} />
);

export const DetailPanelFieldValue = (props: React.ComponentProps<typeof Text>) => (
  <Text style={{ wordBreak: 'break-word' }} {...props} />
);

export const DetailPanelFieldStrongValue = (props: React.ComponentProps<typeof Text>) => (
  <Text strong style={{ wordBreak: 'break-word' }} {...props} />
);

export const DetailPanelFieldMonospaceValue = (props: React.ComponentProps<typeof Text>) => (
  <Text code style={{ wordBreak: 'break-word' }} {...props} />
);

export const DetailPanelDivider = (props: React.ComponentProps<typeof Divider>) => (
  <Divider style={{ margin: '24px 0' }} {...props} />
);
