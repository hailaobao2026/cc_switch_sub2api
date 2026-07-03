<template>
  <AppLayout>
    <div class="space-y-6">
      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 class="text-2xl font-semibold text-gray-900 dark:text-white">CC-Switch 用量</h1>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
            按 sidecar 汇总数据查看总览、用户消费排行榜与按用户聚合后的统计结果
          </p>
        </div>
        <div class="flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300">
          <span class="h-2 w-2 rounded-full bg-sky-500"></span>
          汇总口径: user + day + app + model
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
            <p class="text-xs text-gray-400">当前筛选范围内</p>
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
              输入 {{ formatNumber(externalStats?.total_input_tokens || 0) }}
              / 输出 {{ formatNumber(externalStats?.total_output_tokens || 0) }}
              / 缓存 {{ formatNumber(totalCacheTokens) }}
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
            <p class="text-xs text-gray-400">Top 用户: {{ topUserName }}</p>
          </div>
        </div>

        <div class="card flex items-center gap-3 p-4">
          <div class="rounded-lg bg-purple-100 p-2 text-purple-600 dark:bg-purple-900/30">
            <Icon name="badge" size="md" />
          </div>
          <div>
            <p class="text-xs font-medium text-gray-500">总用户数</p>
            <p class="text-xl font-bold text-gray-900 dark:text-white">{{ formatNumber(externalStats?.total_users || 0) }}</p>
            <p class="text-xs text-gray-400">成功率 {{ formatPercent(externalStats?.success_rate || 0) }}</p>
          </div>
        </div>
      </div>

      <div class="card p-5">
        <div class="flex flex-col gap-4">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">快捷范围</span>
            <button
              v-for="option in quickRanges"
              :key="option.value"
              class="rounded-full border px-3 py-1.5 text-xs font-medium transition"
              :class="activeRange === option.value
                ? 'border-blue-600 bg-blue-600 text-white'
                : 'border-gray-300 bg-white text-gray-600 hover:border-blue-300 hover:text-blue-700 dark:border-dark-600 dark:bg-dark-800 dark:text-gray-300'"
              @click="applyQuickRange(option.value)"
            >
              {{ option.label }}
            </button>
          </div>

          <div class="flex flex-wrap items-end gap-4">
            <label class="space-y-1">
              <span class="input-label">开始日期</span>
              <input v-model="filters.start_date" type="date" class="input w-[180px]" @change="handleDateChange" />
            </label>
            <label class="space-y-1">
              <span class="input-label">结束日期</span>
              <input v-model="filters.end_date" type="date" class="input w-[180px]" @change="handleDateChange" />
            </label>
            <label class="min-w-[240px] flex-1 space-y-1">
              <span class="input-label">用户</span>
              <input
                v-model.trim="filters.user"
                type="text"
                class="input"
                placeholder="按邮箱或用户名搜索..."
                @keyup.enter="applyFilters"
              />
            </label>
            <label class="min-w-[220px] flex-1 space-y-1">
              <span class="input-label">模型</span>
              <input
                v-model.trim="filters.model"
                type="text"
                class="input"
                placeholder="按模型搜索..."
                @keyup.enter="applyFilters"
              />
            </label>
            <label class="min-w-[180px] space-y-1">
              <span class="input-label">应用</span>
              <select v-model="filters.app_type" class="input" @change="applyFilters">
                <option value="">全部</option>
                <option value="claude">claude</option>
                <option value="codex">codex</option>
              </select>
            </label>
            <label class="min-w-[180px] space-y-1">
              <span class="input-label">来源</span>
              <input
                v-model.trim="filters.source"
                type="text"
                class="input"
                placeholder="cc-switch"
                @keyup.enter="applyFilters"
              />
            </label>
            <div class="ml-auto flex flex-wrap items-center gap-3">
              <button class="btn btn-secondary" :disabled="isRefreshing" @click="refreshAll">
                {{ isRefreshing ? '刷新中...' : '刷新统计' }}
              </button>
              <button class="btn btn-secondary" @click="resetFilters">重置</button>
            </div>
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

      <div class="grid grid-cols-1 gap-6 xl:grid-cols-[1.4fr_0.9fr]">
        <div class="card overflow-hidden">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-4 dark:border-dark-700">
            <div class="min-w-0">
              <h2 class="text-base font-semibold text-gray-900 dark:text-white">用户消费排行榜</h2>
              <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                按当前筛选条件汇总到用户维度，日/月/年以结束日期为锚点；未设置结束日期时取今天
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-3">
              <div class="flex overflow-hidden rounded-lg border border-gray-300 dark:border-dark-600">
                <button
                  v-for="option in rankingPeriodOptions"
                  :key="option.value"
                  class="border-r px-3 py-1.5 text-xs font-medium transition last:border-r-0"
                  :class="rankingPeriod === option.value
                    ? 'border-blue-600 bg-blue-600 text-white'
                    : 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50 dark:border-dark-600 dark:bg-dark-800 dark:text-gray-300 dark:hover:bg-dark-700'"
                  @click="changeRankingPeriod(option.value)"
                >
                  {{ option.label }}
                </button>
              </div>
              <button class="btn btn-secondary" :disabled="rankingLoading || rankingExporting" @click="exportRankingCsv">
                {{ rankingExporting ? '导出中...' : '导出 CSV' }}
              </button>
              <div class="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
                {{ rankingPeriodLabel }} Top 10
              </div>
            </div>
          </div>

          <div class="grid gap-4 border-b border-gray-200 bg-slate-50/70 p-5 dark:border-dark-700 dark:bg-dark-900/40 md:grid-cols-3">
            <div
              v-for="(user, index) in podiumUsers"
              :key="`podium-${user.user_id}`"
              class="rounded-2xl border p-4"
              :class="podiumCardClass(index)"
            >
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold uppercase tracking-[0.2em] opacity-80">#{{ index + 1 }}</span>
                <span class="rounded-full px-2 py-1 text-[11px] font-medium" :class="podiumBadgeClass(index)">
                  {{ podiumLabel(index) }}
                </span>
              </div>
              <div class="mt-4">
                <div class="truncate text-sm font-semibold text-gray-900 dark:text-white">{{ displayUserName(user) }}</div>
                <div class="truncate text-xs text-gray-500 dark:text-gray-400">{{ user.email || `用户 #${user.user_id}` }}</div>
              </div>
              <div class="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">总消费</div>
                  <div class="font-semibold text-emerald-600 dark:text-emerald-400">${{ formatCost(user.total_cost) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">总 Token</div>
                  <div class="font-semibold text-gray-900 dark:text-white">{{ formatNumber(user.total_tokens) }}</div>
                </div>
              </div>
            </div>

            <div
              v-if="podiumUsers.length === 0 && !rankingLoading"
              class="md:col-span-3"
            >
              <EmptyState message="当前筛选条件下暂无排行榜数据" />
            </div>
          </div>

          <div class="overflow-auto">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-dark-700">
              <thead class="bg-gray-50 dark:bg-dark-800">
                <tr>
                  <th class="table-th w-16">排名</th>
                  <th class="table-th">用户</th>
                  <th class="table-th text-right">活跃天数</th>
                  <th class="table-th text-right">请求数</th>
                  <th class="table-th text-right">Token</th>
                  <th class="table-th text-right">费用</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200 bg-white dark:divide-dark-700 dark:bg-dark-900">
                <tr v-if="rankingLoading">
                  <td colspan="6" class="px-4 py-10 text-center text-sm text-gray-500">加载排行榜中...</td>
                </tr>
                <template v-else-if="rankingRows.length > 0">
                  <tr
                    v-for="(row, index) in rankingRows"
                    :key="`ranking-${row.user_id}`"
                    class="hover:bg-gray-50 dark:hover:bg-dark-800"
                  >
                    <td class="table-td">
                      <span class="inline-flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 text-sm font-semibold text-gray-700 dark:bg-dark-700 dark:text-gray-200">
                        {{ index + 1 }}
                      </span>
                    </td>
                    <td class="table-td">
                      <div class="font-medium text-gray-900 dark:text-white">{{ displayUserName(row) }}</div>
                      <div class="text-xs text-gray-500">{{ row.email || `用户 #${row.user_id}` }}</div>
                    </td>
                    <td class="table-td text-right tabular-nums">{{ formatNumber(row.active_days) }}</td>
                    <td class="table-td text-right tabular-nums">{{ formatNumber(row.request_count) }}</td>
                    <td class="table-td text-right tabular-nums font-medium text-gray-900 dark:text-white">{{ formatNumber(row.total_tokens) }}</td>
                    <td class="table-td text-right tabular-nums font-medium text-green-600 dark:text-green-400">${{ formatCost(row.total_cost) }}</td>
                  </tr>
                </template>
              </tbody>
            </table>

            <div v-if="!rankingLoading && rankingRows.length === 0" class="py-12">
              <EmptyState message="暂无排行数据" />
            </div>
          </div>
        </div>

        <div class="space-y-4">
          <div class="card p-5">
            <div class="text-xs font-medium uppercase tracking-[0.24em] text-gray-400">用户维度摘要</div>
            <div class="mt-4 space-y-4">
              <div class="rounded-2xl bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 p-4 text-white">
                <div class="text-xs text-blue-100/80">平均每用户消费</div>
                <div class="mt-2 text-3xl font-semibold">${{ formatCost(averageCostPerUser) }}</div>
                <div class="mt-2 text-xs text-blue-100/80">总消费 / 总用户数</div>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div class="rounded-xl border border-gray-200 p-4 dark:border-dark-700">
                  <div class="text-xs text-gray-500 dark:text-gray-400">平均每用户 Token</div>
                  <div class="mt-2 text-lg font-semibold text-gray-900 dark:text-white">{{ formatNumber(averageTokensPerUser) }}</div>
                </div>
                <div class="rounded-xl border border-gray-200 p-4 dark:border-dark-700">
                  <div class="text-xs text-gray-500 dark:text-gray-400">榜首用户消费</div>
                  <div class="mt-2 text-lg font-semibold text-emerald-600 dark:text-emerald-400">${{ formatCost(topUserCost) }}</div>
                </div>
                <div class="rounded-xl border border-gray-200 p-4 dark:border-dark-700">
                  <div class="text-xs text-gray-500 dark:text-gray-400">总记录数</div>
                  <div class="mt-2 text-lg font-semibold text-gray-900 dark:text-white">{{ formatNumber(externalStats?.total_records || 0) }}</div>
                </div>
                <div class="rounded-xl border border-gray-200 p-4 dark:border-dark-700">
                  <div class="text-xs text-gray-500 dark:text-gray-400">总用户数</div>
                  <div class="mt-2 text-lg font-semibold text-gray-900 dark:text-white">{{ formatNumber(externalStats?.total_users || 0) }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="card p-5">
            <div class="flex items-center justify-between">
              <div>
                <h2 class="text-base font-semibold text-gray-900 dark:text-white">用户聚合排序</h2>
                <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">排序规则会影响下方汇总表，不影响榜单</p>
              </div>
              <select v-model="userSortBy" class="input w-[160px]" @change="handleUserSortChange">
                <option value="total_cost">按消费排序</option>
                <option value="total_tokens">按 Token 排序</option>
                <option value="request_count">按请求排序</option>
                <option value="active_days">按活跃天数排序</option>
              </select>
            </div>
            <div class="mt-4 rounded-xl border border-dashed border-gray-300 p-4 text-sm text-gray-500 dark:border-dark-600 dark:text-gray-400">
              用户聚合表会把同一用户在选定时间内的多个 `usage_date / model / app_type` 桶再次汇总，适合看员工总体消耗，而不是单日明细。
            </div>
          </div>
        </div>
      </div>

      <div class="mb-4 flex gap-2 border-b border-gray-200 dark:border-dark-700">
        <button class="tab" :class="{ 'tab-active': activeTab === 'users' }" @click="activeTab = 'users'">用户汇总</button>
        <button class="tab" :class="{ 'tab-active': activeTab === 'detail' }" @click="activeTab = 'detail'">用量明细</button>
      </div>

      <div v-if="activeTab === 'users'" class="card overflow-hidden">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-4 dark:border-dark-700">
          <div>
            <h2 class="text-base font-semibold text-gray-900 dark:text-white">按用户汇总统计</h2>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">同一用户的请求、Token 和费用在当前筛选范围内进行二次聚合</p>
          </div>
          <button class="btn btn-secondary" :disabled="summaryLoading" @click="loadUserSummary">
            {{ summaryLoading ? '加载中...' : '刷新用户表' }}
          </button>
        </div>

        <div class="overflow-auto">
          <table class="min-w-full divide-y divide-gray-200 dark:divide-dark-700">
            <thead class="bg-gray-50 dark:bg-dark-800">
              <tr>
                <th class="table-th w-16">排名</th>
                <th class="table-th">用户</th>
                <th class="table-th text-right">活跃天数</th>
                <th class="table-th text-right">模型数</th>
                <th class="table-th text-right">应用数</th>
                <th class="table-th text-right">请求</th>
                <th class="table-th text-right">成功率</th>
                <th class="table-th text-right">Token</th>
                <th class="table-th text-right">费用</th>
                <th class="table-th whitespace-nowrap">最近上报</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200 bg-white dark:divide-dark-700 dark:bg-dark-900">
              <tr v-if="summaryLoading">
                <td colspan="10" class="px-4 py-10 text-center text-sm text-gray-500">加载用户汇总中...</td>
              </tr>

              <template v-else-if="userSummaryRows.length > 0">
                <tr
                  v-for="(row, index) in userSummaryRows"
                  :key="`summary-${row.user_id}`"
                  class="hover:bg-gray-50 dark:hover:bg-dark-800"
                >
                  <td class="table-td text-center">
                    <span class="text-sm font-semibold text-gray-500 dark:text-gray-400">
                      {{ summaryRank(index) }}
                    </span>
                  </td>
                  <td class="table-td">
                    <div class="font-medium text-gray-900 dark:text-white">{{ displayUserName(row) }}</div>
                    <div class="text-xs text-gray-500">{{ row.email || `用户 #${row.user_id}` }}</div>
                  </td>
                  <td class="table-td text-right tabular-nums">{{ formatNumber(row.active_days) }}</td>
                  <td class="table-td text-right tabular-nums">{{ formatNumber(row.models_count) }}</td>
                  <td class="table-td text-right tabular-nums">{{ formatNumber(row.app_types_count) }}</td>
                  <td class="table-td text-right tabular-nums">{{ formatNumber(row.request_count) }}</td>
                  <td class="table-td text-right tabular-nums">{{ formatPercent(calcSuccessRate(row.success_count, row.request_count)) }}</td>
                  <td class="table-td text-right tabular-nums font-medium text-gray-900 dark:text-white">{{ formatNumber(row.total_tokens) }}</td>
                  <td class="table-td text-right tabular-nums font-medium text-green-600 dark:text-green-400">${{ formatCost(row.total_cost) }}</td>
                  <td class="table-td whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">{{ formatDateTime(row.last_reported_at) }}</td>
                </tr>
              </template>
            </tbody>
          </table>

          <div v-if="!summaryLoading && userSummaryRows.length === 0" class="py-12">
            <EmptyState message="暂无用户汇总数据" />
          </div>
        </div>

        <div v-if="userPagination.total > 0" class="border-t border-gray-200 p-4 dark:border-dark-700">
          <Pagination
            :page="userPagination.page"
            :total="userPagination.total"
            :page-size="userPagination.page_size"
            @update:page="handleUserPageChange"
            @update:pageSize="handleUserPageSizeChange"
          />
        </div>
      </div>

      <div v-else class="card overflow-hidden">
        <div class="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-dark-700">
          <div>
            <h2 class="text-base font-semibold text-gray-900 dark:text-white">按桶明细</h2>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">保留原始 `user + day + app + model` 粒度，适合排查某天某模型的具体使用情况</p>
          </div>
          <button class="btn btn-secondary" :disabled="detailLoading" @click="loadData">
            {{ detailLoading ? '加载中...' : '刷新明细' }}
          </button>
        </div>

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
              <tr v-if="detailLoading">
                <td colspan="12" class="px-4 py-10 text-center text-sm text-gray-500">加载明细中...</td>
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

          <div v-if="!detailLoading && rows.length === 0" class="py-12">
            <EmptyState message="暂无明细数据" />
          </div>
        </div>

        <div v-if="detailPagination.total > 0" class="border-t border-gray-200 p-4 dark:border-dark-700">
          <Pagination
            :page="detailPagination.page"
            :total="detailPagination.total"
            :page-size="detailPagination.page_size"
            @update:page="handleDetailPageChange"
            @update:pageSize="handleDetailPageSizeChange"
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
import { usageAPI } from '@/api/usage'
import type {
  ExternalUsageDailyRow,
  ExternalUsageQueryParams,
  ExternalUsageStatsResponse,
  ExternalUsageUserSummaryRow,
} from '@/api/admin/usage'
import type { TrendDataPoint } from '@/types'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

type DistributionMetric = 'tokens' | 'actual_cost'
type QuickRangeValue = 'today' | 'week' | 'month' | 'all'
type UserSortBy = 'total_cost' | 'total_tokens' | 'request_count' | 'active_days'
type ActiveTab = 'users' | 'detail'
type RankingPeriod = 'day' | 'month' | 'year'

const quickRanges: Array<{ label: string; value: QuickRangeValue }> = [
  { label: '今日', value: 'today' },
  { label: '本周', value: 'week' },
  { label: '本月', value: 'month' },
  { label: '全部', value: 'all' },
]
const rankingPeriodOptions: Array<{ label: string; value: RankingPeriod }> = [
  { label: '日榜', value: 'day' },
  { label: '月榜', value: 'month' },
  { label: '年榜', value: 'year' },
]

const appStore = useAppStore()
const authStore = useAuthStore()
const detailLoading = ref(false)
const statsLoading = ref(false)
const summaryLoading = ref(false)
const rankingLoading = ref(false)
const rankingExporting = ref(false)
const activeTab = ref<ActiveTab>('users')
const activeRange = ref<QuickRangeValue>('month')
const userSortBy = ref<UserSortBy>('total_cost')
const rankingPeriod = ref<RankingPeriod>('month')
const rows = ref<ExternalUsageDailyRow[]>([])
const rankingRows = ref<ExternalUsageUserSummaryRow[]>([])
const userSummaryRows = ref<ExternalUsageUserSummaryRow[]>([])
const externalStats = ref<ExternalUsageStatsResponse | null>(null)
const trendData = ref<TrendDataPoint[]>([])
const externalUsageAPI = computed(() => (authStore.isAdmin ? adminUsageAPI : usageAPI))

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

const detailPagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

const userPagination = reactive({
  page: 1,
  page_size: 15,
  total: 0
})

const isRefreshing = computed(
  () => detailLoading.value || statsLoading.value || summaryLoading.value || rankingLoading.value
)

const totalCacheTokens = computed(
  () => (externalStats.value?.total_cache_creation_tokens || 0) + (externalStats.value?.total_cache_read_tokens || 0)
)
const topUser = computed(() => rankingRows.value[0] || null)
const topUserName = computed(() => (topUser.value ? displayUserName(topUser.value) : '-'))
const topUserCost = computed(() => topUser.value?.total_cost || 0)
const podiumUsers = computed(() => rankingRows.value.slice(0, 3))
const rankingPeriodLabel = computed(() => {
  if (rankingPeriod.value === 'day') {
    return '日榜'
  }
  if (rankingPeriod.value === 'year') {
    return '年榜'
  }
  return '月榜'
})
const averageCostPerUser = computed(() => {
  const totalUsers = externalStats.value?.total_users || 0
  return totalUsers > 0 ? (externalStats.value?.total_cost || 0) / totalUsers : 0
})
const averageTokensPerUser = computed(() => {
  const totalUsers = externalStats.value?.total_users || 0
  return totalUsers > 0 ? Math.round((externalStats.value?.total_tokens || 0) / totalUsers) : 0
})

const buildQueryParams = (): ExternalUsageQueryParams => ({
  start_date: filters.start_date || undefined,
  end_date: filters.end_date || undefined,
  user: filters.user || undefined,
  source: filters.source || undefined,
  app_type: filters.app_type || undefined,
  model: filters.model || undefined,
})

const formatDateForInput = (date: Date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const getRangeDates = (range: QuickRangeValue) => {
  if (range === 'all') {
    return { start: '', end: '' }
  }

  const today = new Date()
  const end = formatDateForInput(today)

  if (range === 'today') {
    return { start: end, end }
  }

  if (range === 'week') {
    const startDate = new Date(today)
    const day = startDate.getDay()
    const diff = day === 0 ? 6 : day - 1
    startDate.setDate(startDate.getDate() - diff)
    return { start: formatDateForInput(startDate), end }
  }

  const startDate = new Date(today.getFullYear(), today.getMonth(), 1)
  return { start: formatDateForInput(startDate), end }
}

const getRankingRangeDates = (period: RankingPeriod) => {
  const anchor = filters.end_date ? new Date(`${filters.end_date}T00:00:00`) : new Date()
  const end = formatDateForInput(anchor)

  if (period === 'day') {
    return { start: end, end }
  }

  if (period === 'year') {
    const startDate = new Date(anchor.getFullYear(), 0, 1)
    return { start: formatDateForInput(startDate), end }
  }

  const startDate = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  return { start: formatDateForInput(startDate), end }
}

const buildRankingQueryParams = (
  page: number,
  pageSize: number
): ExternalUsageQueryParams => {
  const { start, end } = getRankingRangeDates(rankingPeriod.value)
  return {
    ...buildQueryParams(),
    start_date: start,
    end_date: end,
    page,
    page_size: pageSize,
    sort_by: 'total_cost',
    sort_order: 'desc'
  }
}

const loadOverview = async () => {
  statsLoading.value = true
  try {
    const params = buildQueryParams()
    const [stats, trend] = await Promise.all([
      externalUsageAPI.value.getExternalStats(params),
      externalUsageAPI.value.getExternalTrend(params),
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
  detailLoading.value = true
  try {
    const response = await externalUsageAPI.value.listExternal({
      page: detailPagination.page,
      page_size: detailPagination.page_size,
      ...buildQueryParams(),
      sort_by: 'usage_date',
      sort_order: 'desc'
    })

    rows.value = response.items || []
    detailPagination.total = response.total || 0
    detailPagination.page = response.page || detailPagination.page
    detailPagination.page_size = response.page_size || detailPagination.page_size
  } catch (error) {
    console.error('Failed to load external usage detail:', error)
    appStore.showError('加载 CC-Switch 明细失败')
  } finally {
    detailLoading.value = false
  }
}

const loadRanking = async () => {
  rankingLoading.value = true
  try {
    const response = await externalUsageAPI.value.listExternalUsers(buildRankingQueryParams(1, 10))
    rankingRows.value = response.items || []
  } catch (error) {
    console.error('Failed to load external usage ranking:', error)
    appStore.showError('加载用户消费排行榜失败')
  } finally {
    rankingLoading.value = false
  }
}

const loadUserSummary = async () => {
  summaryLoading.value = true
  try {
    const response = await externalUsageAPI.value.listExternalUsers({
      page: userPagination.page,
      page_size: userPagination.page_size,
      ...buildQueryParams(),
      sort_by: userSortBy.value,
      sort_order: 'desc'
    })

    userSummaryRows.value = response.items || []
    userPagination.total = response.total || 0
    userPagination.page = response.page || userPagination.page
    userPagination.page_size = response.page_size || userPagination.page_size
  } catch (error) {
    console.error('Failed to load external usage user summary:', error)
    appStore.showError('加载用户汇总失败')
  } finally {
    summaryLoading.value = false
  }
}

const refreshAll = async () => {
  const tasks = [loadOverview(), loadRanking(), loadUserSummary(), loadData()]
  await Promise.all(tasks)
}

const applyFilters = async () => {
  detailPagination.page = 1
  userPagination.page = 1
  await refreshAll()
}

const applyQuickRange = async (range: QuickRangeValue) => {
  activeRange.value = range
  const { start, end } = getRangeDates(range)
  filters.start_date = start
  filters.end_date = end
  await applyFilters()
}

const handleDateChange = async () => {
  activeRange.value = 'all'
  await applyFilters()
}

const resetFilters = async () => {
  filters.user = ''
  filters.source = 'cc-switch'
  filters.app_type = ''
  filters.model = ''
  userSortBy.value = 'total_cost'
  await applyQuickRange('month')
}

const handleDetailPageChange = (page: number) => {
  detailPagination.page = page
  loadData()
}

const handleDetailPageSizeChange = (pageSize: number) => {
  detailPagination.page_size = pageSize
  detailPagination.page = 1
  loadData()
}

const handleUserPageChange = (page: number) => {
  userPagination.page = page
  loadUserSummary()
}

const handleUserPageSizeChange = (pageSize: number) => {
  userPagination.page_size = pageSize
  userPagination.page = 1
  loadUserSummary()
}

const handleUserSortChange = () => {
  userPagination.page = 1
  loadUserSummary()
}

const changeRankingPeriod = (period: RankingPeriod) => {
  if (rankingPeriod.value === period) {
    return
  }
  rankingPeriod.value = period
  loadRanking()
}

const fetchAllRankingRows = async (): Promise<ExternalUsageUserSummaryRow[]> => {
  const pageSize = 500
  let page = 1
  let total = 0
  const items: ExternalUsageUserSummaryRow[] = []

  do {
    const response = await externalUsageAPI.value.listExternalUsers(buildRankingQueryParams(page, pageSize))
    const batch = response.items || []
    items.push(...batch)
    total = response.total || items.length
    if (batch.length < pageSize) {
      break
    }
    page += 1
  } while (items.length < total)

  return items
}

const exportRankingCsv = async () => {
  rankingExporting.value = true
  try {
    const exportRows = await fetchAllRankingRows()
    if (exportRows.length === 0) {
      appStore.showError('当前排行没有可导出的数据')
      return
    }

    const lines = [
      [
        '排名',
        '用户名',
        '邮箱',
        '活跃天数',
        '模型数',
        '应用数',
        '请求数',
        '成功数',
        '成功率',
        '输入Token',
        '输出Token',
        '缓存读Token',
        '缓存写Token',
        '总Token',
        '总费用USD',
        '最近上报时间',
      ].join(','),
    ]

    exportRows.forEach((row, index) => {
      const values = [
        index + 1,
        displayUserName(row),
        row.email || '',
        row.active_days,
        row.models_count,
        row.app_types_count,
        row.request_count,
        row.success_count,
        calcSuccessRate(row.success_count, row.request_count).toFixed(2) + '%',
        row.input_tokens,
        row.output_tokens,
        row.cache_read_tokens,
        row.cache_creation_tokens,
        row.total_tokens,
        row.total_cost.toFixed(4),
        formatDateTime(row.last_reported_at),
      ]
      lines.push(values.map(csvEscape).join(','))
    })

    const blob = new Blob([`\ufeff${lines.join('\n')}`], { type: 'text/csv;charset=utf-8;' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    const anchorDate = filters.end_date || formatDateForInput(new Date())
    link.href = url
    link.download = `cc-switch-ranking-${rankingPeriod.value}-${anchorDate}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (error) {
    console.error('Failed to export ranking csv:', error)
    appStore.showError('导出排行榜 CSV 失败')
  } finally {
    rankingExporting.value = false
  }
}

const displayUserName = (row: { username: string; email: string; user_id: number }) =>
  row.username || row.email || `用户 #${row.user_id}`

const calcSuccessRate = (successCount: number, requestCount: number) =>
  requestCount > 0 ? (successCount * 100) / requestCount : 0

const summaryRank = (index: number) => (userPagination.page - 1) * userPagination.page_size + index + 1
const formatNumber = (value: number) => new Intl.NumberFormat().format(value || 0)
const formatCost = (value: number) => (value || 0).toFixed(4)
const formatPercent = (value: number) => `${(value || 0).toFixed(1)}%`
const formatDateTime = (value: string) => (value ? new Date(value).toLocaleString() : '-')
const csvEscape = (value: string | number) => `"${String(value ?? '').replace(/"/g, '""')}"`

const podiumCardClass = (index: number) => {
  if (index === 0) {
    return 'border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/20'
  }
  if (index === 1) {
    return 'border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/30'
  }
  return 'border-orange-200 bg-orange-50 dark:border-orange-900/40 dark:bg-orange-950/20'
}

const podiumBadgeClass = (index: number) => {
  if (index === 0) {
    return 'bg-amber-200/80 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200'
  }
  if (index === 1) {
    return 'bg-slate-200/80 text-slate-900 dark:bg-slate-800 dark:text-slate-200'
  }
  return 'bg-orange-200/80 text-orange-900 dark:bg-orange-900/40 dark:text-orange-200'
}

const podiumLabel = (index: number) => {
  if (index === 0) {
    return 'Champion'
  }
  if (index === 1) {
    return 'Runner-up'
  }
  return 'Top 3'
}

onMounted(async () => {
  await applyQuickRange('month')
})
</script>
