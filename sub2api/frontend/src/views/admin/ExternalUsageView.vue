<template>
  <AppLayout>
    <div class="space-y-6">
      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 class="text-2xl font-semibold text-gray-900 dark:text-white">CC-Switch 用量</h1>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">查看和管理由 cc-usage-reporter / sidecar 写入的外部使用记录与统计汇总</p>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div class="card flex items-center gap-3 p-4">
          <div class="rounded-lg bg-blue-100 p-2 text-blue-600 dark:bg-blue-900/30">
            <Icon name="document" size="md" />
          </div>
          <div>
            <p class="text-xs font-medium text-gray-500">总请求数</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">{{ formatNumber(externalStats?.total_requests || 0) }}</p>
            <p class="text-xs text-gray-400">所选范围内</p>
          </div>
        </div>

        <div class="card flex items-center gap-3 p-4">
          <div class="rounded-lg bg-amber-100 p-2 text-amber-600 dark:bg-amber-900/30">
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
            </svg>
          </div>
          <div>
            <p class="text-xs font-medium text-gray-500">总 Token</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">{{ formatNumber(externalStats?.total_tokens || 0) }}</p>
            <p class="text-xs text-gray-400">
              输入: {{ formatNumber(externalStats?.total_input_tokens || 0) }}
              /
              输出: {{ formatNumber(externalStats?.total_output_tokens || 0) }}
              /
              缓存: {{ formatNumber(totalCacheTokens) }}
            </p>
          </div>
        </div>

        <div class="card flex items-center gap-3 p-4">
          <div class="rounded-lg bg-green-100 p-2 text-green-600 dark:bg-green-900/30">
            <Icon name="dollar" size="md" />
          </div>
          <div>
            <p class="text-xs font-medium text-gray-500">总消费</p>
            <p class="text-xl font-bold text-green-600">${{ formatCost(externalStats?.total_cost || 0) }}</p>
            <p class="text-xs text-gray-400">外部上报聚合成本</p>
          </div>
        </div>

        <div class="card flex items-center gap-3 p-4">
          <div class="rounded-lg bg-purple-100 p-2 text-purple-600 dark:bg-purple-900/30">
            <Icon name="badge" size="md" />
          </div>
          <div>
            <p class="text-xs font-medium text-gray-500">成功率</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">{{ formatPercent(externalStats?.success_rate || 0) }}</p>
            <p class="text-xs text-gray-400">成功请求 / 总请求</p>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex items-center gap-3">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">时间范围:</span>
            <div class="flex flex-wrap items-center gap-2">
              <input v-model="filters.start_date" type="date" class="input w-[180px]" @change="applyFilters" />
              <span class="text-sm text-gray-400">至</span>
              <input v-model="filters.end_date" type="date" class="input w-[180px]" @change="applyFilters" />
            </div>
          </div>
          <div class="ml-auto flex flex-wrap items-center gap-3">
            <button class="btn btn-secondary" :disabled="loading || statsLoading" @click="refreshAll">
              {{ loading || statsLoading ? '刷新中...' : '刷新统计' }}
            </button>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ModelDistributionChart
          :model-stats="externalStats?.models || []"
          :loading="statsLoading"
          :metric="modelMetric"
          :show-source-toggle="false"
          :show-metric-toggle="true"
          :enable-breakdown="false"
          :show-account-cost="false"
          @update:metric="modelMetric = $event"
        />
        <EndpointDistributionChart
          title="应用使用分布"
          :endpoint-stats="externalStats?.apps || []"
          :loading="statsLoading"
          :metric="appMetric"
          :show-source-toggle="false"
          :show-metric-toggle="true"
          :enable-breakdown="false"
          @update:metric="appMetric = $event"
        />
      </div>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <EndpointDistributionChart
          title="来源分布"
          :endpoint-stats="externalStats?.sources || []"
          :loading="statsLoading"
          :metric="sourceMetric"
          :show-source-toggle="false"
          :show-metric-toggle="true"
          :enable-breakdown="false"
          @update:metric="sourceMetric = $event"
        />
        <TokenUsageTrend :trend-data="trendData" :loading="statsLoading" />
      </div>

      <div class="card p-6">
        <div class="flex flex-wrap items-end justify-between gap-4">
          <div class="flex flex-1 flex-wrap items-end gap-4">
            <label class="w-full space-y-1 sm:w-auto sm:min-w-[240px]">
              <span class="input-label">用户</span>
              <input
                v-model.trim="filters.user"
                type="text"
                class="input"
                placeholder="按邮箱或用户名搜索..."
                @keyup.enter="applyFilters"
              />
            </label>

            <label class="w-full space-y-1 sm:w-auto sm:min-w-[220px]">
              <span class="input-label">模型</span>
              <input
                v-model.trim="filters.model"
                type="text"
                class="input"
                placeholder="按模型搜索..."
                @keyup.enter="applyFilters"
              />
            </label>

            <label class="w-full space-y-1 sm:w-auto sm:min-w-[180px]">
              <span class="input-label">应用</span>
              <select v-model="filters.app_type" class="input" @change="applyFilters">
                <option value="">全部</option>
                <option value="claude">claude</option>
                <option value="codex">codex</option>
              </select>
            </label>

            <label class="w-full space-y-1 sm:w-auto sm:min-w-[180px]">
              <span class="input-label">来源</span>
              <input
                v-model.trim="filters.source"
                type="text"
                class="input"
                placeholder="cc-switch"
                @keyup.enter="applyFilters"
              />
            </label>
          </div>

          <div class="flex w-full flex-wrap items-center justify-end gap-3 sm:w-auto">
            <button class="btn btn-secondary" :disabled="loading" @click="loadData">
              {{ loading ? '加载中...' : '刷新列表' }}
            </button>
            <button class="btn btn-secondary" @click="resetFilters">重置</button>
          </div>
        </div>
      </div>

      <div class="mb-4 flex gap-2 border-b border-gray-200 dark:border-dark-700">
        <button class="tab tab-active">用量明细</button>
      </div>

      <div class="card overflow-hidden">
        <div class="overflow-auto">
          <table class="min-w-full divide-y divide-gray-200 dark:divide-dark-700">
            <thead class="bg-gray-50 dark:bg-dark-800">
              <tr>
                <th class="table-th whitespace-nowrap">日期</th>
                <th class="table-th">用户</th>
                <th class="table-th whitespace-nowrap">来源</th>
                <th class="table-th whitespace-nowrap">应用</th>
                <th class="table-th min-w-[220px]">模型</th>
                <th class="table-th text-right">请求</th>
                <th class="table-th text-right">Input</th>
                <th class="table-th text-right">Output</th>
                <th class="table-th text-right">Cache</th>
                <th class="table-th text-right">Token</th>
                <th class="table-th text-right">费用</th>
                <th class="table-th whitespace-nowrap">上报时间</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200 bg-white dark:divide-dark-700 dark:bg-dark-900">
              <tr v-if="loading">
                <td colspan="12" class="px-4 py-10 text-center text-sm text-gray-500">加载中...</td>
              </tr>

              <template v-else-if="rows.length > 0">
                <tr
                  v-for="row in rows"
                  :key="`${row.user_id}-${row.source}-${row.usage_date}-${row.app_type}-${row.model}-${row.requested_model}`"
                  class="hover:bg-gray-50 dark:hover:bg-dark-800"
                >
                  <td class="table-td whitespace-nowrap font-medium text-gray-900 dark:text-white">{{ row.usage_date }}</td>
                  <td class="table-td">
                    <div class="text-sm">
                      <div class="font-medium text-gray-900 dark:text-white">{{ row.username || '-' }}</div>
                      <div class="text-xs text-gray-500">{{ row.email || `用户 #${row.user_id}` }}</div>
                    </div>
                  </td>
                  <td class="table-td whitespace-nowrap">
                    <span class="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200">
                      {{ row.source }}
                    </span>
                  </td>
                  <td class="table-td whitespace-nowrap">
                    <span
                      class="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium"
                      :class="row.app_type === 'claude' ? 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200' : 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'"
                    >
                      {{ row.app_type }}
                    </span>
                  </td>
                  <td class="table-td">
                    <div class="font-medium text-gray-900 dark:text-white">{{ row.model }}</div>
                    <div v-if="row.requested_model && row.requested_model !== row.model" class="text-xs text-gray-500">
                      请求: {{ row.requested_model }}
                    </div>
                  </td>
                  <td class="table-td text-right tabular-nums">{{ formatNumber(row.request_count) }}</td>
                  <td class="table-td text-right tabular-nums">{{ formatNumber(row.input_tokens) }}</td>
                  <td class="table-td text-right tabular-nums">{{ formatNumber(row.output_tokens) }}</td>
                  <td class="table-td text-right tabular-nums">{{ formatNumber(row.cache_read_tokens + row.cache_creation_tokens) }}</td>
                  <td class="table-td text-right tabular-nums font-medium text-gray-900 dark:text-white">{{ formatNumber(row.total_tokens) }}</td>
                  <td class="table-td text-right tabular-nums font-medium text-green-600 dark:text-green-400">${{ formatCost(row.total_cost) }}</td>
                  <td class="table-td whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">{{ formatDateTime(row.reported_at) }}</td>
                </tr>
              </template>
            </tbody>
          </table>

          <div v-if="!loading && rows.length === 0" class="py-12">
            <EmptyState message="暂无数据" />
          </div>
        </div>

        <div v-if="pagination.total > 0" class="border-t border-gray-200 p-4 dark:border-dark-700">
          <Pagination
            :page="pagination.page"
            :total="pagination.total"
            :page-size="pagination.page_size"
            @update:page="handlePageChange"
            @update:pageSize="handlePageSizeChange"
          />
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import Pagination from '@/components/common/Pagination.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import Icon from '@/components/icons/Icon.vue'
import ModelDistributionChart from '@/components/charts/ModelDistributionChart.vue'
import EndpointDistributionChart from '@/components/charts/EndpointDistributionChart.vue'
import TokenUsageTrend from '@/components/charts/TokenUsageTrend.vue'
import { adminUsageAPI } from '@/api/admin/usage'
import type {
  ExternalUsageDailyRow,
  ExternalUsageQueryParams,
  ExternalUsageStatsResponse,
} from '@/api/admin/usage'
import type { TrendDataPoint } from '@/types'
import { useAppStore } from '@/stores/app'

type DistributionMetric = 'tokens' | 'actual_cost'

const appStore = useAppStore()
const loading = ref(false)
const statsLoading = ref(false)
const rows = ref<ExternalUsageDailyRow[]>([])
const externalStats = ref<ExternalUsageStatsResponse | null>(null)
const trendData = ref<TrendDataPoint[]>([])

const modelMetric = ref<DistributionMetric>('tokens')
const appMetric = ref<DistributionMetric>('tokens')
const sourceMetric = ref<DistributionMetric>('tokens')

const filters = reactive({
  start_date: '',
  end_date: '',
  user: '',
  source: 'cc-switch',
  app_type: '',
  model: ''
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

const totalCacheTokens = computed(
  () => (externalStats.value?.total_cache_creation_tokens || 0) + (externalStats.value?.total_cache_read_tokens || 0)
)

const buildQueryParams = (): ExternalUsageQueryParams => ({
  start_date: filters.start_date || undefined,
  end_date: filters.end_date || undefined,
  user: filters.user || undefined,
  source: filters.source || undefined,
  app_type: filters.app_type || undefined,
  model: filters.model || undefined,
})

const loadOverview = async () => {
  statsLoading.value = true
  try {
    const params = buildQueryParams()
    const [stats, trend] = await Promise.all([
      adminUsageAPI.getExternalStats(params),
      adminUsageAPI.getExternalTrend(params),
    ])
    externalStats.value = stats
    trendData.value = trend
  } catch (error) {
    console.error('Failed to load external usage overview:', error)
    appStore.showError('加载 CC-Switch 统计失败')
  } finally {
    statsLoading.value = false
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const response = await adminUsageAPI.listExternal({
      page: pagination.page,
      page_size: pagination.page_size,
      ...buildQueryParams(),
      sort_by: 'usage_date',
      sort_order: 'desc'
    })

    rows.value = response.items || []
    pagination.total = response.total || 0
    pagination.page = response.page || pagination.page
    pagination.page_size = response.page_size || pagination.page_size
  } catch (error) {
    console.error('Failed to load external usage:', error)
    appStore.showError('加载 CC-Switch 用量失败')
  } finally {
    loading.value = false
  }
}

const refreshAll = async () => {
  await Promise.all([loadOverview(), loadData()])
}

const applyFilters = () => {
  pagination.page = 1
  refreshAll()
}

const resetFilters = () => {
  filters.start_date = ''
  filters.end_date = ''
  filters.user = ''
  filters.source = 'cc-switch'
  filters.app_type = ''
  filters.model = ''
  pagination.page = 1
  refreshAll()
}

const handlePageChange = (page: number) => {
  pagination.page = page
  loadData()
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.page_size = pageSize
  pagination.page = 1
  loadData()
}

const formatNumber = (value: number) => new Intl.NumberFormat().format(value || 0)
const formatCost = (value: number) => (value || 0).toFixed(4)
const formatPercent = (value: number) => `${(value || 0).toFixed(1)}%`
const formatDateTime = (value: string) => (value ? new Date(value).toLocaleString() : '-')

onMounted(refreshAll)
</script>
