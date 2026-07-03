import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ExternalUsageView from '../ExternalUsageView.vue'

const {
  adminListExternal,
  adminGetExternalStats,
  adminGetExternalTrend,
  adminListExternalUsers,
  userListExternal,
  userGetExternalStats,
  userGetExternalTrend,
  userListExternalUsers,
  showError,
} = vi.hoisted(() => ({
  adminListExternal: vi.fn(),
  adminGetExternalStats: vi.fn(),
  adminGetExternalTrend: vi.fn(),
  adminListExternalUsers: vi.fn(),
  userListExternal: vi.fn(),
  userGetExternalStats: vi.fn(),
  userGetExternalTrend: vi.fn(),
  userListExternalUsers: vi.fn(),
  showError: vi.fn(),
}))

const authState = vi.hoisted(() => ({
  isAdmin: false,
}))

vi.mock('@/api/admin/usage', () => ({
  adminUsageAPI: {
    listExternal: adminListExternal,
    getExternalStats: adminGetExternalStats,
    getExternalTrend: adminGetExternalTrend,
    listExternalUsers: adminListExternalUsers,
  },
}))

vi.mock('@/api/usage', () => ({
  usageAPI: {
    listExternal: userListExternal,
    getExternalStats: userGetExternalStats,
    getExternalTrend: userGetExternalTrend,
    listExternalUsers: userListExternalUsers,
  },
}))

vi.mock('@/stores/app', () => ({
  useAppStore: () => ({ showError }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authState,
}))

const simpleStub = { template: '<div><slot /></div>' }
const chartStub = { template: '<div />' }

function mountView() {
  return mount(ExternalUsageView, {
    global: {
      stubs: {
        AppLayout: simpleStub,
        Pagination: true,
        EmptyState: true,
        Icon: true,
        ModelDistributionChart: chartStub,
        EndpointDistributionChart: chartStub,
        TokenUsageTrend: chartStub,
      },
    },
  })
}

const paginatedUsers = {
  items: [
    {
      user_id: 1,
      username: 'alice',
      email: 'alice@example.com',
      active_days: 3,
      models_count: 2,
      app_types_count: 1,
      request_count: 12,
      success_count: 10,
      input_tokens: 100,
      output_tokens: 200,
      cache_read_tokens: 0,
      cache_creation_tokens: 0,
      total_tokens: 300,
      total_cost: 1.23,
      last_reported_at: '2026-07-03T00:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 15,
}

const paginatedDetails = {
  items: [
    {
      user_id: 1,
      username: 'alice',
      email: 'alice@example.com',
      source: 'cc-switch',
      usage_date: '2026-07-03',
      app_type: 'claude',
      model: 'claude-sonnet-4',
      requested_model: 'claude-sonnet-4',
      request_count: 12,
      success_count: 10,
      input_tokens: 100,
      output_tokens: 200,
      cache_read_tokens: 0,
      cache_creation_tokens: 0,
      total_tokens: 300,
      total_cost: 1.23,
      reported_at: '2026-07-03T00:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
}

const statsResponse = {
  total_requests: 12,
  total_success_requests: 10,
  total_input_tokens: 100,
  total_output_tokens: 200,
  total_cache_read_tokens: 0,
  total_cache_creation_tokens: 0,
  total_tokens: 300,
  total_cost: 1.23,
  total_actual_cost: 1.23,
  total_records: 1,
  total_users: 1,
  success_rate: 83.3,
  models: [],
  apps: [],
  sources: [],
}

describe('ExternalUsageView', () => {
  beforeEach(() => {
    authState.isAdmin = false

    adminListExternal.mockReset()
    adminGetExternalStats.mockReset()
    adminGetExternalTrend.mockReset()
    adminListExternalUsers.mockReset()
    userListExternal.mockReset()
    userGetExternalStats.mockReset()
    userGetExternalTrend.mockReset()
    userListExternalUsers.mockReset()
    showError.mockReset()

    userListExternal.mockResolvedValue(paginatedDetails)
    userGetExternalStats.mockResolvedValue(statsResponse)
    userGetExternalTrend.mockResolvedValue([])
    userListExternalUsers.mockResolvedValue(paginatedUsers)
  })

  it('shows the full module for non-admin users and loads detail data', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(userGetExternalStats).toHaveBeenCalled()
    expect(userGetExternalTrend).toHaveBeenCalled()
    expect(userListExternal).toHaveBeenCalled()
    expect(userListExternalUsers).toHaveBeenCalled()
    expect(adminListExternal).not.toHaveBeenCalled()

    expect(wrapper.text()).toContain('用量明细')
    expect(wrapper.text()).toContain('按桶明细')
    expect(wrapper.text()).toContain('按用户汇总统计')
    expect(wrapper.text()).toContain('用户')
  })
})
