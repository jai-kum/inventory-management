<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-header">
          <div>
            <div class="stat-label">{{ t('restocking.budget') }}</div>
            <div class="budget-value">{{ formatMoney(budget) }}</div>
          </div>
          <label class="budget-input-label">
            <span>{{ t('restocking.budgetInputLabel', { currency: currentCurrency }) }}</span>
            <input
              type="number"
              class="budget-input"
              min="0"
              :max="maxBudgetDisplay"
              :step="budgetStepDisplay"
              :value="budgetDisplay"
              :disabled="maxBudget === 0"
              @change="onBudgetInput"
            />
          </label>
        </div>
        <input
          v-model.number="budget"
          type="range"
          class="budget-slider"
          min="0"
          :max="maxBudget"
          :step="BUDGET_STEP"
          :disabled="maxBudget === 0"
          :aria-label="t('restocking.budgetLabel')"
        />
        <div class="slider-scale">
          <span>{{ formatMoney(0) }}</span>
          <span>{{ formatMoney(maxBudget) }}</span>
        </div>
      </div>

      <div v-if="lastOrder" class="confirmation">
        <div class="confirmation-header">
          <div>
            <div class="confirmation-title">{{ t('restocking.orderPlaced') }}</div>
            <div class="confirmation-text">
              {{ t('restocking.orderPlacedDetail', { orderNumber: lastOrder.order_number }) }}
            </div>
          </div>
          <button type="button" class="link-button" @click="lastOrder = null">
            {{ t('restocking.dismiss') }}
          </button>
        </div>
        <div class="confirmation-grid">
          <div>
            <div class="confirmation-label">{{ t('restocking.orderNumber') }}</div>
            <div class="confirmation-value">{{ lastOrder.order_number }}</div>
          </div>
          <div>
            <div class="confirmation-label">{{ t('restocking.orderTotal') }}</div>
            <div class="confirmation-value">{{ formatMoney(lastOrder.total_value) }}</div>
          </div>
          <div>
            <div class="confirmation-label">{{ t('restocking.leadTime') }}</div>
            <div class="confirmation-value">{{ t('restocking.daysCount', { days: lastOrder.lead_time_days }) }}</div>
          </div>
          <div>
            <div class="confirmation-label">{{ t('restocking.expectedDelivery') }}</div>
            <div class="confirmation-value">{{ formatDate(lastOrder.expected_delivery) }}</div>
          </div>
        </div>
        <router-link to="/orders" class="confirmation-link">{{ t('restocking.viewOrders') }}</router-link>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.budget') }}</div>
          <div class="stat-value">{{ formatMoney(summary.budget) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.recommendedTotal') }}</div>
          <div class="stat-value">{{ formatMoney(summary.totalCost) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ formatMoney(summary.remaining) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.coverage') }}</div>
          <div class="stat-value">{{ summary.coverage.toFixed(1) }}%</div>
          <div class="stat-detail">
            {{ t('restocking.coverageDetail', { funded: formatMoney(summary.totalCost), needed: formatMoney(summary.totalNeeded) }) }}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">
            {{ t('restocking.recommendations') }} ({{ items.length }})
            <span v-if="refreshing" class="updating">{{ t('restocking.updating') }}</span>
          </h3>
          <div class="order-actions">
            <span v-if="fundedItems.length > 0" class="order-summary">
              {{ t('restocking.itemsToOrder', { count: fundedItems.length, total: formatMoney(summary.totalCost) }) }}
            </span>
            <span v-else-if="items.length > 0" class="order-summary">{{ t('restocking.nothingToOrder') }}</span>
            <button
              type="button"
              class="btn-primary"
              :disabled="!canPlaceOrder"
              @click="placeOrder"
            >
              {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
            </button>
          </div>
        </div>

        <div v-if="refreshError" class="error">{{ refreshError }}</div>
        <div v-if="submitError" class="error">{{ submitError }}</div>

        <div v-if="items.length === 0" class="empty-state">{{ t('restocking.noNeed') }}</div>
        <div v-else :class="['table-container', { stale: refreshing }]">
          <table class="restock-table">
            <thead>
              <tr>
                <th class="num">{{ t('restocking.table.priority') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.category') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.forecastedDemand') }}</th>
                <th class="num">{{ t('restocking.table.onHand') }}</th>
                <th class="num">{{ t('restocking.table.onOrder') }}</th>
                <th class="num">{{ t('restocking.table.needed') }}</th>
                <th class="num">{{ t('restocking.table.recommendedQty') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.lineTotal') }}</th>
                <th class="num">{{ t('restocking.table.leadTimeDays') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in items"
                :key="item.sku"
                :class="{ 'row-unfunded': item.recommended_quantity === 0, 'row-partial': isPartial(item) }"
              >
                <td class="num">{{ item.priority }}</td>
                <td>
                  <div class="item-name">{{ translateProductName(item.name) }}</div>
                  <div class="item-sku">{{ item.sku }}</div>
                </td>
                <td>{{ translateCategory(item.category) }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="num">{{ formatNumber(item.forecasted_demand) }}</td>
                <td class="num">{{ formatNumber(item.on_hand) }}</td>
                <td class="num">{{ formatNumber(item.on_order) }}</td>
                <td class="num">{{ formatNumber(item.needed_quantity) }}</td>
                <td class="num">
                  <strong>{{ formatNumber(item.recommended_quantity) }}</strong>
                  <span v-if="isPartial(item)" class="tag tag-partial">{{ t('restocking.partial') }}</span>
                  <span v-else-if="item.recommended_quantity === 0" class="tag tag-unfunded">{{ t('restocking.notFunded') }}</span>
                </td>
                <td class="num">{{ formatMoneyPrecise(item.unit_cost) }}</td>
                <td class="num"><strong>{{ formatMoney(item.line_total) }}</strong></td>
                <td class="num">{{ item.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals, convertAmount } from '../utils/currency'

const BUDGET_STEP = 500
const DEFAULT_BUDGET = 25000
const DEBOUNCE_MS = 250

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const refreshing = ref(false)
    const refreshError = ref(null)
    const submitting = ref(false)
    const submitError = ref(null)
    const lastOrder = ref(null)

    const budget = ref(DEFAULT_BUDGET)
    const maxBudget = ref(0)
    const recommendations = ref(null)

    let requestSeq = 0
    let lastRequestedBudget = null
    let debounceTimer = null

    const items = computed(() => recommendations.value?.items || [])
    const fundedItems = computed(() => items.value.filter(item => item.recommended_quantity > 0))

    const summary = computed(() => {
      const rec = recommendations.value
      const totalCost = rec?.total_cost || 0
      const totalNeeded = rec?.total_needed_cost || 0
      return {
        budget: rec?.budget ?? budget.value,
        totalCost,
        remaining: rec?.remaining_budget || 0,
        totalNeeded,
        coverage: totalNeeded > 0 ? Math.min(100, (totalCost / totalNeeded) * 100) : 100
      }
    })

    const canPlaceOrder = computed(() =>
      fundedItems.value.length > 0 && !submitting.value && !refreshing.value
    )

    // Currency helpers: amounts from the API are USD; convert for display
    const formatMoney = (amount) => formatCurrency(Number(amount) || 0, currentCurrency.value)
    const formatMoneyPrecise = (amount) =>
      formatCurrencyWithDecimals(Number(amount) || 0, currentCurrency.value, 2)

    const formatNumber = (value) => {
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return (Number(value) || 0).toLocaleString(locale)
    }

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return '-'
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    const translateCategory = (category) => {
      const categoryMap = {
        'Circuit Boards': 'categories.circuitBoards',
        'Sensors': 'categories.sensors',
        'Actuators': 'categories.actuators',
        'Controllers': 'categories.controllers',
        'Power Supplies': 'categories.powerSupplies',
        'Components': 'spendingCategories.components',
        'Consumables': 'spendingCategories.consumables'
      }
      return categoryMap[category] ? t(categoryMap[category]) : category
    }

    const isPartial = (item) =>
      item.recommended_quantity > 0 && item.recommended_quantity < item.needed_quantity

    // Numeric input works in the display currency and converts back to USD
    const currencyRate = computed(() => convertAmount(1, currentCurrency.value))
    const budgetDisplay = computed(() => convertAmount(budget.value, currentCurrency.value))
    const maxBudgetDisplay = computed(() => convertAmount(maxBudget.value, currentCurrency.value))
    const budgetStepDisplay = computed(() => convertAmount(BUDGET_STEP, currentCurrency.value))

    const clampBudget = (value) => {
      if (!Number.isFinite(value)) return 0
      return Math.min(Math.max(0, Math.round(value)), maxBudget.value)
    }

    const onBudgetInput = (event) => {
      const entered = parseFloat(event.target.value)
      const next = clampBudget(entered / currencyRate.value)
      budget.value = next
      // Reflect clamped value even if the budget did not change
      event.target.value = convertAmount(next, currentCurrency.value)
    }

    const fetchRecommendations = async (value) => {
      const seq = ++requestSeq
      lastRequestedBudget = value
      refreshing.value = true
      try {
        const data = await api.getRestockRecommendations(value)
        if (seq !== requestSeq) return // stale response
        recommendations.value = data
        refreshError.value = null
      } catch (err) {
        if (seq !== requestSeq) return
        refreshError.value = t('restocking.loadError')
        console.error('Failed to load restock recommendations:', err)
      } finally {
        if (seq === requestSeq) refreshing.value = false
      }
    }

    // Learn the total need (budget 0) to size the slider, then load the current budget
    const loadBounds = async () => {
      const data = await api.getRestockRecommendations(0)
      const needed = Number(data?.total_needed_cost) || 0
      maxBudget.value = Math.ceil(needed / 1000) * 1000
      budget.value = clampBudget(budget.value)
    }

    const loadInitial = async () => {
      try {
        loading.value = true
        error.value = null
        await loadBounds()
        await fetchRecommendations(budget.value)
        if (refreshError.value) {
          error.value = refreshError.value
        }
      } catch (err) {
        error.value = t('restocking.loadError')
        console.error('Failed to load restock recommendations:', err)
      } finally {
        loading.value = false
      }
    }

    watch(budget, (value) => {
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        if (value === lastRequestedBudget) return
        fetchRecommendations(value)
      }, DEBOUNCE_MS)
    })

    const placeOrder = async () => {
      if (!canPlaceOrder.value) return
      submitting.value = true
      submitError.value = null
      try {
        const order = await api.createRestockOrder({
          budget: recommendations.value.budget,
          items: fundedItems.value.map(item => ({ sku: item.sku, quantity: item.recommended_quantity }))
        })
        lastOrder.value = order
      } catch (err) {
        submitError.value = err.response?.data?.detail
          ? String(err.response.data.detail)
          : t('restocking.submitError')
        console.error('Failed to place restock order:', err)
        submitting.value = false
        return
      }

      // Need has shrunk; recompute slider bounds and refresh recommendations
      try {
        await loadBounds()
      } catch (err) {
        console.error('Failed to refresh restock bounds:', err)
      }
      clearTimeout(debounceTimer)
      await fetchRecommendations(budget.value)
      submitting.value = false
    }

    onMounted(loadInitial)
    onBeforeUnmount(() => clearTimeout(debounceTimer))

    return {
      t,
      BUDGET_STEP,
      currentCurrency,
      loading,
      error,
      refreshing,
      refreshError,
      submitting,
      submitError,
      lastOrder,
      budget,
      maxBudget,
      items,
      fundedItems,
      summary,
      canPlaceOrder,
      budgetDisplay,
      maxBudgetDisplay,
      budgetStepDisplay,
      onBudgetInput,
      placeOrder,
      formatMoney,
      formatMoneyPrecise,
      formatNumber,
      formatDate,
      translateCategory,
      translateProductName,
      isPartial
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1.5rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.budget-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: #2563eb;
  letter-spacing: -0.025em;
}

.budget-input-label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.813rem;
  font-weight: 600;
  color: #64748b;
}

.budget-input {
  width: 180px;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 0.938rem;
  color: #0f172a;
}

.budget-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.budget-slider {
  width: 100%;
  accent-color: #2563eb;
  cursor: pointer;
}

.budget-slider:disabled {
  cursor: not-allowed;
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.25rem;
}

.stat-detail {
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.375rem;
}

.confirmation {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-left: 4px solid #10b981;
  border-radius: 10px;
  padding: 1.25rem;
  margin-bottom: 1.25rem;
}

.confirmation-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.confirmation-title {
  font-size: 1.125rem;
  font-weight: 700;
  color: #065f46;
}

.confirmation-text {
  font-size: 0.875rem;
  color: #047857;
  margin-top: 0.25rem;
}

.confirmation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.confirmation-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.confirmation-value {
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
  margin-top: 0.25rem;
}

.confirmation-link {
  font-size: 0.875rem;
  font-weight: 600;
  color: #2563eb;
  text-decoration: none;
}

.confirmation-link:hover {
  text-decoration: underline;
}

.link-button {
  background: none;
  border: none;
  color: #64748b;
  font-size: 0.875rem;
  cursor: pointer;
}

.link-button:hover {
  color: #0f172a;
  text-decoration: underline;
}

.order-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.order-summary {
  font-size: 0.875rem;
  color: #64748b;
}

.btn-primary {
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.625rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.updating {
  font-size: 0.813rem;
  font-weight: 500;
  color: #64748b;
  margin-left: 0.5rem;
}

.table-container.stale {
  opacity: 0.6;
  transition: opacity 0.15s ease;
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.938rem;
}

.num {
  text-align: right;
  white-space: nowrap;
}

.item-name {
  font-weight: 500;
  color: #0f172a;
}

.item-sku {
  font-size: 0.75rem;
  color: #64748b;
}

.row-unfunded td {
  color: #94a3b8;
}

.row-unfunded .item-name {
  color: #94a3b8;
}

.row-unfunded .badge {
  opacity: 0.6;
}

.row-partial {
  background: #fffbeb;
}

.row-partial:hover {
  background: #fef3c7;
}

.tag {
  display: inline-block;
  margin-left: 0.375rem;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.688rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.tag-partial {
  background: #fed7aa;
  color: #92400e;
}

.tag-unfunded {
  background: #f1f5f9;
  color: #64748b;
}
</style>
