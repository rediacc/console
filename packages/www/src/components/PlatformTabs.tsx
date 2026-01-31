import React from 'react';

export interface PlatformTab {
  key: string;
  label: string;
  icon?: React.FC;
}

interface PlatformTabsProps {
  tabs: PlatformTab[];
  activeTab: string;
  onTabChange: (key: string) => void;
  ariaLabel: string;
}

const PlatformTabs: React.FC<PlatformTabsProps> = ({ tabs, activeTab, onTabChange, ariaLabel }) => (
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
