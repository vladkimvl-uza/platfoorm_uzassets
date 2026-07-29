import { describe, expect, it } from 'vitest';

import { deriveAccessMap } from '@/api/rbacV3';

describe('deriveAccessMap', () => {
  it('marks a direct module grant as personal even when the user has a role', () => {
    const access = deriveAccessMap({
      is_owner: false,
      role_codes: ['viewer'],
      effective_permissions: ['exec_dashboard.view'],
      direct_permissions: ['exec_dashboard.view'],
      denied_permissions: [],
    } as any);

    expect(access.levels.exec_dashboard).toBe('read');
    expect(access.sources.exec_dashboard).toBe('персональный доступ');
  });

  it('keeps the role as source when there is no personal override', () => {
    const access = deriveAccessMap({
      is_owner: false,
      role_codes: ['viewer'],
      effective_permissions: ['exec_dashboard.view'],
      direct_permissions: [],
      denied_permissions: [],
    } as any);

    expect(access.levels.exec_dashboard).toBe('read');
    expect(access.sources.exec_dashboard).toContain('viewer');
  });
});
