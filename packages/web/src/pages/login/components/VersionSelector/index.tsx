import React, { useState, useEffect } from 'react';
import { versionService } from '@/services/versionService';
import { VersionText } from './styles';

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

  return <VersionText type="secondary">{loading ? '...' : displayVersion}</VersionText>;
};

export default VersionSelector;
