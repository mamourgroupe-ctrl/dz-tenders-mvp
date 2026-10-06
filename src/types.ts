export type Product = 'PVC_PIPES' | 'PEHD_PIPES' | 'PE_TANKS'
export type Priority = 1 | 2 | 3
export type TenderStatus = 'active' | 'closing_soon' | 'closed'

export interface Tender {
  id: string
  titleAr: string
  titleFr: string
  organisation: string
  organisationShort: string
  wilaya: string
  deadline: string
  publicationDate: string
  products: Product[]
  score: number
  priority: Priority
  status: TenderStatus
  description: string
  source: string
  sourceUrl: string
  latitude: number
  longitude: number
  reference: string
  estimatedValue: string
}

export interface TenderFilters {
  search?: string
  wilaya?: string
  product?: Product | ''
  priority?: Priority | ''
  dateFrom?: string
  dateTo?: string
  page?: number
  pageSize?: number
}

export interface TenderPage {
  items: Tender[]
  total: number
  page: number
  pageSize: number
  pages: number
}

export interface SummaryStats {
  total: number
  active: number
  priority1: number
  priority2: number
  priority3: number
  change: number
}

export interface TimelinePoint {
  date: string
  label: string
  tenders: number
}

export interface WilayaPoint {
  wilaya: string
  count: number
  percentage: number
}

export interface ProductPoint {
  product: Product
  label: string
  count: number
  color: string
}

export interface MonthlyPoint {
  month: string
  current: number
  previous: number
}

export interface OrganisationPoint {
  organisation: string
  count: number
  percentage: number
}

export interface DashboardStats {
  summary: SummaryStats
  timeline: TimelinePoint[]
  byWilaya: WilayaPoint[]
  byProduct: ProductPoint[]
}
