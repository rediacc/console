export interface SSHTestResult {
  status: string;
  machine?: string;
  ip: string;
  user: string;
  auth_method: string;
  ssh_key_configured: boolean;
  kernel_compatibility: {
    kernel_version: string;
    btrfs_available: boolean;
    sudo_available: string;
    compatibility_status: 'compatible' | 'warning' | 'incompatible' | 'unknown';
    compatibility_issues?: string[];
    recommendations?: string[];
    os_info?: {
      pretty_name?: string;
      id?: string;
      version_id?: string;
    };
  };
}

export interface ParsedSSHTestResult {
  isSSHTest: boolean;
  result?: SSHTestResult;
}

/**
 * Attempts to parse vault content as an SSH test result.
 * Returns an object indicating whether this is an SSH test result and the parsed data if applicable.
 */
export const parseSSHTestResults = (vaultContent: unknown): ParsedSSHTestResult => {
  try {
    // Handle both string and object content
    const content =
      typeof vaultContent === 'string' ? JSON.parse(vaultContent) : vaultContent || {};

    // Check if this has a result field (SSH test structure)
    if (!content.result || typeof content.result !== 'string') {
      return { isSSHTest: false };
    }

    // Try to parse the nested result
    const result = JSON.parse(content.result);

    // Validate it's an SSH test result by checking for kernel_compatibility
    if (!result.status || !result.kernel_compatibility) {
      return { isSSHTest: false };
    }

    return {
      isSSHTest: true,
      result: result as SSHTestResult,
    };
  } catch {
    return { isSSHTest: false };
  }
};
