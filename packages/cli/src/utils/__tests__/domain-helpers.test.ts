import { describe, expect, it } from 'vitest';
import { extractAutoRoute } from '../domain-helpers.js';

describe('extractAutoRoute', () => {
  it('returns dash for missing labels', () => {
    expect(extractAutoRoute(undefined, 'example.com', 'server-1')).toBe('-');
  });

  it('returns dash when required labels are missing', () => {
    expect(extractAutoRoute({}, 'example.com', 'server-1')).toBe('-');
  });

  it('builds grand repo URL: {service}.{repo}.{machine}.{baseDomain}', () => {
    const labels = {
      'rediacc.service_name': 'myapp',
      'rediacc.repo_name': 'marketing',
    };
    expect(extractAutoRoute(labels, 'example.com', 'server-1')).toBe(
      'myapp.marketing.server-1.example.com'
    );
  });

  it('builds fork URL: {service}-fork-{tag}.{repo}.{machine}.{baseDomain}', () => {
    const labels = {
      'rediacc.service_name': 'myapp',
      'rediacc.repo_name': 'marketing:staging',
      'rediacc.is_fork': 'true',
      'rediacc.fork_tag': 'staging',
    };
    expect(extractAutoRoute(labels, 'example.com', 'server-1')).toBe(
      'myapp-fork-staging.marketing.server-1.example.com'
    );
  });

  it('strips :tag from repoName for fork parent', () => {
    const labels = {
      'rediacc.service_name': 'pgadmin',
      'rediacc.repo_name': 'demo-stackoverflow:iso-test',
      'rediacc.is_fork': 'true',
      'rediacc.fork_tag': 'iso-test',
    };
    expect(extractAutoRoute(labels, 'rediacc.io', 'hostinger')).toBe(
      'pgadmin-fork-iso-test.demo-stackoverflow.hostinger.rediacc.io'
    );
  });

  it('works without machineName', () => {
    const labels = {
      'rediacc.service_name': 'app',
      'rediacc.repo_name': 'myrepo',
    };
    expect(extractAutoRoute(labels, 'example.com')).toBe('app.myrepo.example.com');
  });

  it('non-fork with is_fork=false uses grand repo pattern', () => {
    const labels = {
      'rediacc.service_name': 'api',
      'rediacc.repo_name': 'backend',
      'rediacc.is_fork': 'false',
    };
    expect(extractAutoRoute(labels, 'example.com', 'srv')).toBe('api.backend.srv.example.com');
  });
});
