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

interface ParsedSSHTestResult {
  isSSHTest: boolean;
  result?: SSHTestResult;
}

/**
 * Attempts to parse vault content as an SSH test result.
 * Returns an object indicating whether this is an SSH test result and the parsed data if applicable.
 *
 * Supports both:
 * - Nested format: { result: "{...json string...}" } (old bridge)
 * - Direct format: { status: "...", kernel_compatibility: {...} } (renet bridge)
 */
export const parseSSHTestResults = (vaultContent: unknown): ParsedSSHTestResult => {
  try {
    // Handle both string and object content
    let content: Record<string, unknown>;
    if (typeof vaultContent === 'string') {
      content = JSON.parse(vaultContent);
    } else {
      content = (vaultContent ?? {}) as Record<string, unknown>;
    }

    let result: Record<string, unknown>;

    // Check for nested format: { result: "{...}" }
    if (content.result && typeof content.result === 'string') {
      result = JSON.parse(content.result);
    }
    // Check for direct format: { status: "...", kernel_compatibility: {...} }
    else if (content.status !== undefined && content.kernel_compatibility) {
      result = content;
    } else {
      return { isSSHTest: false };
    }

    // Validate it's an SSH test result by checking for kernel_compatibility
    if (!result.status || !result.kernel_compatibility) {
      return { isSSHTest: false };
    }

    return {
      isSSHTest: true,
      result: result as unknown as SSHTestResult,
    };
  } catch {
    return { isSSHTest: false };
  }
};
