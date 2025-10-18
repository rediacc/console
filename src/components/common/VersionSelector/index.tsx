import React, { useState, useEffect } from 'react';
import { TagOutlined } from '@/utils/optimizedIcons';
import { versionService } from '@/services/versionService';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import {
  StyledSelect,
  VersionText,
  OptionContent,
  EmojiIcon
} from './styles';

const { Option } = StyledSelect;

interface VersionSelectorProps {
  showDropdown?: boolean;
}

const VersionSelector: React.FC<VersionSelectorProps> = ({ showDropdown }) => {
  const [versions, setVersions] = useState<string[]>([]);
  const [currentVersion, setCurrentVersion] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayVersion, setDisplayVersion] = useState<string>('Development');

  useEffect(() => {
    const fetchVersions = async () => {
      try {
        // Get current version and all available versions
        const [versionInfo, versionsManifest] = await Promise.all([
          versionService.getVersion(),
          versionService.getAllVersions()
        ]);

        setVersions(versionsManifest.versions);
        setCurrentVersion(versionService.getCurrentVersion());
        setDisplayVersion(versionService.formatVersion(versionInfo.version));
      } catch (error) {
        console.warn('Failed to fetch version information', error);
      } finally {
        setLoading(false);
      }
    };

    fetchVersions();
  }, []);

  // If showDropdown is explicitly false, always show static text
  if (showDropdown === false) {
    return (
      <VersionText type="secondary">
        {loading ? '...' : displayVersion}
      </VersionText>
    );
  }

  // If showDropdown is explicitly true, always show dropdown (even if loading or single version)
  // If undefined, use auto-detect logic for backward compatibility
  if (showDropdown === undefined) {
    // Auto-detect: Don't show dropdown in local development
    if (versionService.isLocalDevelopment()) {
      return (
        <VersionText type="secondary">
          {displayVersion}
        </VersionText>
      );
    }

    // Auto-detect: Show static text if loading or only one version
    if (loading || versions.length <= 1) {
      return (
        <VersionText type="secondary">
          {loading ? '...' : displayVersion}
        </VersionText>
      );
    }
  }

  const handleVersionChange = (value: unknown) => {
    const versionValue = value as string;
    // Get current route path (e.g., /login, /dashboard)
    const currentPath = window.location.pathname;

    // Remove version prefix if exists to get the route
    const routePath = currentPath.replace(/^\/versions\/v\d+\.\d+\.\d+/, '') || '/login';

    let newUrl: string;
    if (versionValue === 'latest') {
      // Navigate to root deployment
      newUrl = `${window.location.origin}${routePath}`;
    } else {
      // Navigate to versioned deployment
      newUrl = `${window.location.origin}/versions/${versionValue}${routePath}`;
    }

    // Full page reload to ensure proper base path detection
    window.location.href = newUrl;
  };

  // Determine selected value
  const selectedValue = currentVersion || 'latest';

  return (
    <StyledSelect
      value={selectedValue}
      onChange={handleVersionChange}
      style={{ width: 120 }}
      size="small"
      suffixIcon={<TagOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS }} />}
      popupMatchSelectWidth={false}
      data-testid="version-selector"
    >
      {/* Latest option */}
      <Option key="latest" value="latest" data-testid="version-option-latest">
        <OptionContent>
          <EmojiIcon>📍</EmojiIcon>
          Latest
        </OptionContent>
      </Option>

      {/* All version options */}
      {versions.map((version) => (
        <Option key={version} value={version} data-testid={`version-option-${version}`}>
          <OptionContent>
            {version}
          </OptionContent>
        </Option>
      ))}
    </StyledSelect>
  );
};

export default VersionSelector;
