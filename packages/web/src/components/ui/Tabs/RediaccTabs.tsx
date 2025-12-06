import { forwardRef } from 'react';
import { StyledRediaccTabs, mapVariantToAntType } from './RediaccTabs.styles';
import type { RediaccTabsProps } from './RediaccTabs.types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccTabs = forwardRef<any, RediaccTabsProps>(
  (
    {
      variant = 'default',
      size = 'md',
      centered = false,
      fullWidth = false,
      items,
      activeKey,
      defaultActiveKey,
      onChange,
      onTabClick,
      tabBarExtraContent,
      destroyInactiveTabPane = false,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccTabs
        ref={ref}
        type={mapVariantToAntType(variant)}
        $variant={variant}
        $size={size}
        $centered={centered}
        $fullWidth={fullWidth}
        items={items}
        activeKey={activeKey}
        defaultActiveKey={defaultActiveKey}
        onChange={onChange}
        onTabClick={onTabClick}
        tabBarExtraContent={tabBarExtraContent}
        destroyInactiveTabPane={destroyInactiveTabPane}
        {...rest}
      />
    );
  }
);

RediaccTabs.displayName = 'RediaccTabs';
