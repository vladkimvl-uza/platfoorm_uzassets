import { mount } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { describe, expect, it } from 'vitest';
import RoleAssignmentPicker from '../RoleAssignmentPicker.vue';
import type { RbacV3Role } from '@/api/rbacV3';

const roles: RbacV3Role[] = [
  {
    id: 'role-viewer',
    code: 'viewer',
    name_ru: 'Наблюдатель',
    name_en: 'Viewer',
    description_ru: 'Просмотр данных без редактирования',
    is_system: true,
    sort_order: 10,
    permission_count: 4,
  },
  {
    id: 'role-financier',
    code: 'financier',
    name_ru: 'Финансист',
    name_en: 'Financier',
    description_ru: 'Работа с финансовыми данными',
    is_system: true,
    sort_order: 20,
    permission_count: 8,
  },
];

function mountPicker(props: { roles: RbacV3Role[]; modelValue: string[]; multiple?: boolean }) {
  return mount(RoleAssignmentPicker, {
    props,
    global: { plugins: [createPinia()] },
  });
}

describe('RoleAssignmentPicker', () => {
  it('adds a role without dropping existing selections in multiple mode', async () => {
    const wrapper = mountPicker({ roles, modelValue: ['viewer'] });

    await wrapper.get('button[aria-pressed="false"]').trigger('click');

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([
      ['viewer', 'financier'],
    ]);
  });

  it('emits only the picked role in single mode', async () => {
    const wrapper = mountPicker({ roles, modelValue: ['viewer'], multiple: false });

    await wrapper.get('button[aria-pressed="false"]').trigger('click');

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([
      ['financier'],
    ]);
  });

  it('filters roles by their localized name', async () => {
    const wrapper = mountPicker({ roles, modelValue: [] });

    await wrapper.get('input[type="search"]').setValue('финанс');

    expect(wrapper.findAll('.rap-role')).toHaveLength(1);
    expect(wrapper.text()).toContain('Финансист');
    expect(wrapper.text()).not.toContain('Наблюдатель');
  });
});
