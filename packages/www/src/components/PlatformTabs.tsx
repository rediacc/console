import React from 'react';

export interface PlatformTab<T extends string> {
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
  <div className="platform-tabs" role="tablist" aria-label={ariaLabel}>
    {tabs.map(({ key, label, icon: Icon }) => (
      <button
        type="button"
        key={key}
        role="tab"
        aria-selected={activeTab === key}
        className={`platform-tab${activeTab === key ? ' platform-tab--active' : ''}`}
        onClick={() => onTabChange(key)}
      >
        {Icon && <Icon />}
        <span>{label}</span>
      </button>
    ))}
  </div>
);

export default PlatformTabs;
