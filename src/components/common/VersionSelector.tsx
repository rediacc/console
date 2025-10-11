import React, { useState, useEffect } from 'react';
import { Select, Typography } from 'antd';
import { TagOutlined } from '@/utils/optimizedIcons';
import { versionService } from '@/services/versionService';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

const { Option } = Select;
const { Text } = Typography;

const VersionSelector: React.FC = () => {
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

  // Don't show dropdown in local development
  if (versionService.isLocalDevelopment()) {
    return (
      <Text type="secondary" style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS, opacity: 0.6 }}>
        {displayVersion}
      </Text>
    );
  }

  // Show static text if loading or only one version
  if (loading || versions.length <= 1) {
    return (
      <Text type="secondary" style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS, opacity: 0.6 }}>
        {loading ? '...' : displayVersion}
      </Text>
    );
  }

  const handleVersionChange = (value: string) => {
    // Get current route path (e.g., /login, /dashboard)
    const currentPath = window.location.pathname;

    // Remove version prefix if exists to get the route
    const routePath = currentPath.replace(/^\/versions\/v\d+\.\d+\.\d+/, '') || '/login';

    let newUrl: string;
    if (value === 'latest') {
      // Navigate to root deployment
      newUrl = `${window.location.origin}${routePath}`;
    } else {
      // Navigate to versioned deployment
      newUrl = `${window.location.origin}/versions/${value}${routePath}`;
    }

    // Full page reload to ensure proper base path detection
    window.location.href = newUrl;
  };

  // Determine selected value
  const selectedValue = currentVersion || 'latest';

  return (
    <Select
      value={selectedValue}
      onChange={handleVersionChange}
      style={{
        fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
        width: 120
      }}
      size="small"
      suffixIcon={<TagOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS }} />}
      popupMatchSelectWidth={false}
      data-testid="version-selector"
      dropdownStyle={{
        fontSize: DESIGN_TOKENS.FONT_SIZE.XS
      }}
    >
      {/* Latest option */}
      <Option key="latest" value="latest" data-testid="version-option-latest">
        <span style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS }}>
          📍 Latest
        </span>
      </Option>

      {/* All version options */}
      {versions.map((version) => (
        <Option key={version} value={version} data-testid={`version-option-${version}`}>
          <span style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS }}>
            {version}
          </span>
        </Option>
      ))}
    </Select>
  );
};

export default VersionSelector;
