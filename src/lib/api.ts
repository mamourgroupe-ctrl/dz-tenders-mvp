import { mockTenders, productLabels } from '../data/mockTenders'
import type {
  DashboardStats,
  MonthlyPoint,
  OrganisationPoint,
  Product,
  ProductPoint,
  SummaryStats,
  Tender,
  TenderFilters,
  TenderPage,
  TimelinePoint,
  WilayaPoint,
} from '../types'

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '')
const API_ROOT = API_URL ? (API_URL.endsWith('/api') ? API_URL : `${API_URL}/api`) : ''
const PAGE_SIZE = 20

/**
 * Mock data is an explicit development mode: it is used only when
 * VITE_API_URL is not set. When an API URL is configured, failures are
 * surfaced to React Query (loading/error states) instead of silently
 * falling back to mock tenders.
 */
export const isUsingMockApi = !API_URL

function buildUrl(path: string, params?: URLSearchParams): string {
  const url = `${API_ROOT}${path}`
  return params && params.toString() ? `${url}?${params.toString()}` : url
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
  ) {
    super(`API request failed: ${status} ${code}`)
    this.name = 'ApiError'
  }
}

async function getJson<T>(path: string, params?: URLSearchParams): Promise<T> {
  const response = await fetch(buildUrl(path, params))
  if (!response.ok) {
    let code = 'http_error'
    try {
      const body = (await response.json()) as { error?: { code?: string } }
      if (body.error?.code) code = body.error.code
    } catch {
      // Non-JSON error body: keep the generic code, never invent details.
    }
    throw new ApiError(response.status, code)
  }
  return response.json() as Promise<T>
}

function filterMockTenders(filters: TenderFilters): Tender[] {
  const search = filters.search?.trim().toLocaleLowerCase('ar')
  return mockTenders.filter((tender) => {
    const matchesSearch = !search || [tender.titleAr, tender.titleFr, tender.organisation, tender.reference, tender.wilaya]
      .some((value) => (value ?? '').toLocaleLowerCase('ar').includes(search))
    const matchesWilaya = !filters.wilaya || tender.wilaya === filters.wilaya
    const matchesProduct = !filters.product || tender.products.includes(filters.product)
    const matchesPriority = !filters.priority || tender.priority === filters.priority
    const matchesFrom = !filters.dateFrom || (tender.deadline ?? '') >= filters.dateFrom
    const matchesTo = !filters.dateTo || (tender.deadline ?? '9999-12-31') <= filters.dateTo
    return matchesSearch && matchesWilaya && matchesProduct && matchesPriority && matchesFrom && matchesTo
  })
}

export async function fetchTenders(filters: TenderFilters = {}): Promise<TenderPage> {
  if (API_URL) {
    const params = new URLSearchParams()
    if (filters.search) params.set('search', filters.search)
    if (filters.wilaya) params.set('wilaya', filters.wilaya)
    if (filters.product) params.set('product', filters.product)
    if (filters.priority) params.set('priority', String(filters.priority))
    if (filters.dateFrom) params.set('date_from', filters.dateFrom)
    if (filters.dateTo) params.set('date_to', filters.dateTo)
    params.set('page', String(filters.page ?? 1))
    params.set('page_size', String(filters.pageSize ?? PAGE_SIZE))
    return getJson<TenderPage>('/tenders', params)
  }

  const matching = filterMockTenders(filters)
  const page = filters.page ?? 1
  const pageSize = filters.pageSize ?? PAGE_SIZE
  const start = (page - 1) * pageSize
  return {
    items: matching.slice(start, start + pageSize),
    total: matching.length,
    page,
    pageSize,
    pages: Math.max(1, Math.ceil(matching.length / pageSize)),
  }
}

function deriveSummary(tenders: Tender[]): SummaryStats {
  const active = tenders.filter((tender) => tender.status !== 'closed').length
  return {
    total: tenders.length,
    active,
    priority1: tenders.filter((tender) => tender.priority === 1).length,
    priority2: tenders.filter((tender) => tender.priority === 2).length,
    priority3: tenders.filter((tender) => tender.priority === 3).length,
    change: 12.4,
  }
}

function deriveTimeline(tenders: Tender[]): TimelinePoint[] {
  const timeline: TimelinePoint[] = []
  const anchor = new Date('2026-10-06T12:00:00')
  for (let offset = 29; offset >= 0; offset -= 1) {
    const date = new Date(anchor)
    date.setDate(anchor.getDate() - offset)
    const iso = date.toISOString().slice(0, 10)
    const count = tenders.filter((tender) => tender.publicationDate === iso).length
    // A small stable baseline gives the dashboard a useful trend even with sparse mock dates.
    const baseline = [2, 3, 1, 4, 2, 5, 3][offset % 7]
    timeline.push({
      date: iso,
      label: date.toLocaleDateString('ar-DZ', { day: 'numeric', month: 'short' }),
      tenders: count + baseline,
    })
  }
  return timeline
}

function deriveByWilaya(tenders: Tender[]): WilayaPoint[] {
  const counts = new Map<string, number>()
  tenders.forEach((tender) => counts.set(tender.wilaya, (counts.get(tender.wilaya) ?? 0) + 1))
  return [...counts.entries()]
    .map(([wilaya, count]) => ({ wilaya, count, percentage: Math.round((count / tenders.length) * 100) }))
    .sort((a, b) => b.count - a.count)
}

function deriveByProduct(tenders: Tender[]): ProductPoint[] {
  const products: Product[] = ['PVC_PIPES', 'PEHD_PIPES', 'PE_TANKS']
  const colors: Record<Product, string> = { PVC_PIPES: '#1a5490', PEHD_PIPES: '#2ca58d', PE_TANKS: '#f6a623' }
  return products.map((product) => ({
    product,
    label: productLabels[product],
    count: tenders.filter((tender) => tender.products.includes(product)).length,
    color: colors[product],
  }))
}

function buildMockDashboardStats(): DashboardStats {
  return {
    summary: deriveSummary(mockTenders),
    timeline: deriveTimeline(mockTenders),
    byWilaya: deriveByWilaya(mockTenders),
    byProduct: deriveByProduct(mockTenders),
  }
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  if (API_URL) {
    const [summary, byWilaya, byProduct, timeline] = await Promise.all([
      getJson<SummaryStats>('/stats/summary'),
      getJson<WilayaPoint[]>('/stats/by-wilaya'),
      getJson<ProductPoint[]>('/stats/by-product'),
      getJson<TimelinePoint[]>('/stats/timeline'),
    ])
    return { summary, byWilaya, byProduct, timeline }
  }
  return buildMockDashboardStats()
}

export async function fetchTender(id: string): Promise<Tender | undefined> {
  if (API_URL) {
    try {
      return await getJson<Tender>(`/tenders/${encodeURIComponent(id)}`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return undefined
      throw error
    }
  }
  return mockTenders.find((tender) => tender.id === id)
}

export interface StatisticsData {
  monthly: MonthlyPoint[]
  organisations: OrganisationPoint[]
  /** Outcome metrics are not stored in SQLite; null outside mock mode. */
  successRate: number | null
  won: number | null
  submitted: number | null
}

export async function fetchStatistics(): Promise<StatisticsData> {
  if (API_URL) {
    // Real mode: derive only what the read-only API actually stores.
    // Monthly points come from the 30-day timeline; win/submission
    // outcomes are not tracked anywhere, so they stay null (the page
    // hides those widgets) instead of showing invented numbers.
    const [page, timeline] = await Promise.all([
      getJson<TenderPage>('/tenders', new URLSearchParams({ page: '1', page_size: '100' })),
      getJson<TimelinePoint[]>('/stats/timeline'),
    ])
    const orgCounts = new Map<string, number>()
    page.items.forEach((tender) =>
      orgCounts.set(tender.organisationShort, (orgCounts.get(tender.organisationShort) ?? 0) + 1),
    )
    const total = page.total || page.items.length
    const monthCounts = new Map<string, number>()
    timeline.forEach((point) => {
      const month = point.date.slice(0, 7)
      monthCounts.set(month, (monthCounts.get(month) ?? 0) + point.tenders)
    })
    return {
      monthly: [...monthCounts.entries()].map(([month, current]) => ({
        month,
        current,
        previous: 0,
      })),
      organisations: [...orgCounts.entries()]
        .map(([organisation, count]) => ({
          organisation,
          count,
          percentage: total ? Math.round((count / total) * 100) : 0,
        }))
        .sort((a, b) => b.count - a.count),
      successRate: null,
      won: null,
      submitted: null,
    }
  }
  const counts = new Map<string, number>()
  mockTenders.forEach((tender) => counts.set(tender.organisationShort, (counts.get(tender.organisationShort) ?? 0) + 1))
  const total = mockTenders.length
  return {
    monthly: [
      { month: 'ماي', current: 18, previous: 12 },
      { month: 'جوان', current: 24, previous: 20 },
      { month: 'جويلية', current: 21, previous: 25 },
      { month: 'أوت', current: 29, previous: 23 },
      { month: 'سبتمبر', current: total, previous: 26 },
      { month: 'أكتوبر', current: 22, previous: 19 },
    ],
    organisations: [...counts.entries()]
      .map(([organisation, count]) => ({ organisation, count, percentage: Math.round((count / total) * 100) }))
      .sort((a, b) => b.count - a.count),
    successRate: 68,
    won: 17,
    submitted: 25,
  }
}

export { PAGE_SIZE }
