/** Resolve a short domain name (no dots) to FQDN using baseDomain. */
export function resolveDomain(domain: string, baseDomain?: string): string {
  if (!domain || domain.includes('.')) return domain;
  return baseDomain ? `${domain}.${baseDomain}` : domain;
}

/** Extract the custom domain from container labels (Traefik Host rule or rediacc.domain). */
export function extractCustomDomain(labels?: Record<string, string>, baseDomain?: string): string {
  if (!labels) return '-';

  if (labels['rediacc.domain']) return resolveDomain(labels['rediacc.domain'], baseDomain);

  for (const [key, value] of Object.entries(labels)) {
    if (key.startsWith('traefik.http.routers.') && key.endsWith('.rule')) {
      const match = /Host\(`([^`]+)`\)/.exec(value);
      if (match) return match[1];
    }
  }

  return '-';
}

/** Derive the auto-route domain from service labels + machineName + baseDomain. */
export function extractAutoRoute(
  labels?: Record<string, string>,
  baseDomain?: string,
  machineName?: string
): string {
  if (!labels) return '-';
  const repoName = labels['rediacc.repo_name'];
  const serviceName = labels['rediacc.service_name'];
  const isFork = labels['rediacc.is_fork'] === 'true';
  const forkTag = labels['rediacc.fork_tag'];
  if (serviceName && repoName && baseDomain) {
    const machineDomain = machineName ? `${machineName}.${baseDomain}` : baseDomain;
    // Strip :tag suffix from repoName to get the parent repo name
    const parentName = repoName.includes(':') ? repoName.split(':')[0] : repoName;
    const repoDomain = `${parentName}.${machineDomain}`;
    if (isFork && forkTag) {
      return `${serviceName}-fork-${forkTag}.${repoDomain}`;
    }
    return `${serviceName}.${repoDomain}`;
  }
  return '-';
}
