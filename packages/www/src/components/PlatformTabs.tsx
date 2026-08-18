import React from 'react';

interface PlatformTab<T extends string> {
  key: T;
  label: string;
  icon?: React.FC;
}

interface PlatformTabsProps<T extends string> {
  tabs: PlatformTab<T>[];
  activeTab: T;
  onTabChange: (key: T) => void;
  ariaLabel: string;
}

const PlatformTabs = <T extends string>({
  tabs,
  activeTab,
  onTabChange,
  ariaLabel,
}: PlatformTabsProps<T>) => (
  <div className="segmented" role="tablist" aria-label={ariaLabel}>
    {tabs.map(({ key, label, icon: Icon }) => (
      <button
        type="button"
        key={key}
        role="tab"
        aria-selected={activeTab === key}
        className="segmented__item"
        onClick={() => onTabChange(key)}
        data-track="cta_click"
        data-track-label="platform-tab"
      >
        {Icon && <Icon />}
        <span>{label}</span>
      </button>
    ))}
  </div>
);

export default PlatformTabs;
