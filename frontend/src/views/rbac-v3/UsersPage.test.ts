import { flushPromises, shallowMount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { rbacV3Api, type RbacV3Overview, type RbacV3UserBrief } from '@/api/rbacV3';
import UsersPage from './UsersPage.vue';

vi.mock('@/api/rbacV3', () => ({
  rbacV3Api: {
    overview: vi.fn(),
    listUsers: vi.fn(),
    deactivate: vi.fn(),
  },
}));

vi.mock('@/composables/useConfirm', () => ({
  useConfirm: () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }),
}));

vi.mock('@/composables/usePresence', () => ({
  presenceStatus: () => 'offline',
}));

const overview: RbacV3Overview = {
  users_total: 3,
  users_active: 2,
  users_inactive: 1,
  roles_total: 8,
  permissions_total: 42,
  users_without_roles: 0,
  most_assigned_roles: [],
};

const users: RbacV3UserBrief[] = [
  {
    id: 'user-owner',
    email: 'owner@example.com',
    full_name: 'Алина Владелец',
    department: 'Администрация',
    job_title: 'Руководитель',
    is_active: true,
    is_owner: true,
    must_change_password: false,
    last_login_at: '2026-07-29T08:00:00Z',
    last_seen_at: '2026-07-29T08:30:00Z',
    locked_until: null,
    created_at: '2026-01-10T08:00:00Z',
    role_codes: ['admin'],
    role_names: ['Администратор'],
    organization_id: 'company-alpha',
    company: 'UzAssets Alpha',
    allowed_companies: null,
    company_memberships: [
      {
        company_id: 'company-alpha',
        company_name: 'UzAssets Alpha',
        group_id: 'group-alpha',
        group_name: 'UzAssets Alpha',
        role_code: 'admin',
        role_name: 'Администратор',
      },
      {
        company_id: 'company-beta',
        company_name: 'UzAssets Beta',
        group_id: 'group-beta',
        group_name: 'UzAssets Beta',
        role_code: 'viewer',
        role_name: 'Наблюдатель',
      },
    ],
  },
  {
    id: 'user-active',
    email: 'active@example.com',
    full_name: 'Бахтиёр Аналитик',
    department: 'Аналитика',
    is_active: true,
    is_owner: false,
    must_change_password: true,
    last_login_at: null,
    last_seen_at: null,
    locked_until: null,
    created_at: '2026-04-10T08:00:00Z',
    role_codes: [],
    role_names: [],
    organization_id: 'company-alpha',
    company: 'UzAssets Alpha',
    allowed_companies: null,
    company_memberships: [{
      company_id: 'company-alpha',
      company_name: 'UzAssets Alpha',
      group_id: 'group-alpha',
      group_name: 'UzAssets Alpha',
      role_code: 'analyst',
      role_name: 'Аналитик',
    }],
  },
  {
    id: 'user-blocked',
    email: 'blocked@example.com',
    full_name: 'Дилноза Архив',
    department: 'Финансы',
    is_active: false,
    is_owner: false,
    must_change_password: false,
    last_login_at: '2026-05-01T08:00:00Z',
    last_seen_at: '2026-05-01T08:30:00Z',
    locked_until: null,
    created_at: '2026-03-10T08:00:00Z',
    role_codes: ['viewer'],
    role_names: ['Наблюдатель'],
    organization_id: 'company-beta',
    company: 'UzAssets Beta',
    allowed_companies: null,
    company_memberships: [{
      company_id: 'company-beta',
      company_name: 'UzAssets Beta',
      group_id: 'group-beta',
      group_name: 'UzAssets Beta',
      role_code: 'viewer',
      role_name: 'Наблюдатель',
    }],
  },
];

describe('UsersPage', () => {
  beforeEach(() => {
    vi.mocked(rbacV3Api.overview).mockResolvedValue(overview);
    vi.mocked(rbacV3Api.listUsers).mockResolvedValue({ items: users, total: users.length });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders authoritative overview metrics and the loaded registry', async () => {
    const wrapper = shallowMount(UsersPage);
    await flushPromises();

    expect(wrapper.findAll('.summary-metric strong').map(node => node.text())).toEqual(['3', '2', '1', '0']);
    expect(wrapper.findAll('.company-group-header')).toHaveLength(2);
    expect(wrapper.findAll('.user-row')).toHaveLength(4);
    expect(wrapper.text()).toContain('UzAssets Alpha');
    expect(wrapper.text()).toContain('UzAssets Beta');
    expect(wrapper.text()).toContain('Алина Владелец');
    expect(wrapper.text()).toContain('Дилноза Архив');

    wrapper.unmount();
  });

  it('switches between company groups and a deduplicated flat list', async () => {
    const wrapper = shallowMount(UsersPage);
    await flushPromises();

    expect(wrapper.findAll('.company-group-header')).toHaveLength(2);
    expect(wrapper.findAll('.user-row')).toHaveLength(4);

    await wrapper.get('button[title="Показать единым списком"]').trigger('click');

    expect(wrapper.findAll('.company-group-header')).toHaveLength(0);
    expect(wrapper.findAll('.user-row')).toHaveLength(3);

    wrapper.unmount();
  });

  it('selects and collapses a whole company section', async () => {
    const wrapper = shallowMount(UsersPage);
    await flushPromises();

    const alphaGroup = wrapper.findAll('.company-group-header')
      .find(group => group.text().includes('UzAssets Alpha'));
    expect(alphaGroup).toBeDefined();

    await alphaGroup!.get('input[type="checkbox"]').trigger('change');
    expect(wrapper.get('.bulk-count > span').text()).toBe('2');

    await alphaGroup!.get('.company-collapse').trigger('click');
    expect(wrapper.findAll('.user-row')).toHaveLength(2);

    wrapper.unmount();
  });

  it('filters blocked users and exposes bulk actions after selection', async () => {
    const wrapper = shallowMount(UsersPage);
    await flushPromises();

    const blockedFilter = wrapper.findAll('.filter-tab').find(button => button.text().includes('Заблокированные'));
    expect(blockedFilter).toBeDefined();
    await blockedFilter!.trigger('click');

    expect(wrapper.findAll('.user-row')).toHaveLength(1);
    expect(wrapper.text()).toContain('Дилноза Архив');
    expect(wrapper.text()).not.toContain('Бахтиёр Аналитик');

    await wrapper.get('input[aria-label="Выбрать Дилноза Архив"]').trigger('change');
    expect(wrapper.get('.bulk-actions').text()).toContain('Выбрано');
    expect(wrapper.get('.bulk-actions').text()).toContain('Изменить роли');

    wrapper.unmount();
  });
});
