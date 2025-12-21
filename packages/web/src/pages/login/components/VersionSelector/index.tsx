import React, { useEffect, useState } from 'react';
import { Typography } from 'antd';
import { versionService } from '@/services/versionService';

const VersionSelector: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [displayVersion, setDisplayVersion] = useState<string>('Development');

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const versionInfo = await versionService.getVersion();
        setDisplayVersion(versionService.formatVersion(versionInfo.version));
      } catch (error) {
        console.warn('Failed to fetch version information', error);
      } finally {
        setLoading(false);
      }
    };

    fetchVersion();
  }, []);

  return (
    <Typography.Text style={{ fontSize: 12, color: 'var(--ant-color-text-secondary)' }}>
      {loading ? '...' : displayVersion}
    </Typography.Text>
  );
};

export default VersionSelector;
