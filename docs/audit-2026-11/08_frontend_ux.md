# Audit Report 08: Frontend & UX

**Date:** 2026-11-08  
**Repository:** dz-tenders-mvp  
**Auditor:** Claude Opus 5.5

---

## Executive Summary

The frontend is a **React 18 + TypeScript + Vite** single-page application (`src/`) serving as an **admin/dashboard** for the platform. It uses **TanStack Query** for server state, **React Router v6** for routing, **Tailwind CSS** for styling, **Recharts** for analytics, and **Leaflet** for maps. Code quality is good with strict TypeScript, but **bundle size (861 kB JS)** exceeds recommendations and **code-splitting is absent**. UX is functional with RTL Arabic support, but accessibility and responsive design need verification.

---

## Architecture

```
src/
├── main.tsx                 # Entry: QueryClientProvider, BrowserRouter, App
├── App.tsx                  # Routes: /tenders, /dashboard, /login, /
├── lib/
│   ├── api.ts               # Dual-mode client (mock/real), TanStack hooks
│   └── types.ts             # TypeScript interfaces mirroring API
├── pages/
│   ├── TendersPage.tsx      # Main table: filters, pagination, favorites, drawer
│   ├── DashboardPage.tsx    # Metrics cards, 3 charts, recent tenders table
│   ├── LoginPage.tsx        # Phone/password + CSRF
│   └── NotFound.tsx         # 404
├── components/
│   ├── layout/
│   │   ├── Header.tsx       # Logo, navigation, user menu
│   │   ├── Sidebar.tsx      # Collapsible nav (desktop/mobile)
│   │   └── Footer.tsx
│   ├── tenders/
│   │   ├── TendersTable.tsx # TanStack Table v8 (sort, filter, select)
│   │   ├── TenderFilters.tsx# Multi-select: type, wilaya, sector, date
│   │   ├── TenderDrawer.tsx # Side panel: detail + map (Leaflet)
│   │   └── TenderRow.tsx    # Row with favorite star, expand
│   ├── dashboard/
│   │   ├── MetricCard.tsx   # KPI tile with trend
│   │   ├── LineChart.tsx    # Recharts: tenders over time
│   │   ├── PieChart.tsx     # Recharts: by type/sector/wilaya
│   │   └── BarChart.tsx     # Recharts: top wilayas/sectors
│   ├── ui/
│   │   ├── Button.tsx       # Variants: primary, secondary, ghost, danger
│   │   ├── Input.tsx        # With label, error, RTL support
│   │   ├── Select.tsx       # Multi-select with search
│   │   ├── Pagination.tsx   # Page numbers + ellipsis
│   │   ├── Badge.tsx        # Status, priority, type badges
│   │   ├── Modal.tsx        # Portal-based, focus trap
│   │   └── Tooltip.tsx      # Hover/focus trigger
│   └── map/
│       └── MapContainer.tsx # Leaflet wrapper with custom markers
├── hooks/
│   ├── useTenders.ts        # useQuery + useInfiniteQuery wrappers
│   ├── useDashboardStats.ts # useQuery for stats
│   └── useAuth.ts           # Login/logout mutations
└── styles/
    ├── globals.css          # Tailwind imports + custom RTL utilities
    └── tailwind.css         # Tailwind config (arabic font, rtl)
```

---

## Key Features

### Tenders Page (`TendersPage.tsx`)

| Feature | Implementation |
|---------|----------------|
| **Data Fetching** | `useTenders(params)` → TanStack Query (cache 30s, dedupe) |
| **Table** | TanStack Table v8: column sorting, row selection, pagination |
| **Filters** | Controlled inputs → update query params → refetch |
| **Pagination** | Server-side (page/page_size); `Pagination` component |
| **Favorites** | Local state + `useMutation` to backend (not yet wired) |
| **Detail Drawer** | Slide-over panel (`TenderDrawer`) with map + full fields |
| **Map** | Leaflet + OSM tiles; marker at wilaya centroid (approx) |
| **RTL** | `dir="rtl"` on `<html>`; Tailwind `rtl:` variants |

### Dashboard Page (`DashboardPage.tsx`)

| Widget | Library | Data Source |
|--------|---------|-------------|
| **Metric Cards** (4) | Custom `MetricCard` | `fetchDashboardStats()` |
| **Line Chart** (Tenders/Month) | Recharts `LineChart` | `fetchStatistics({period: "monthly"})` |
| **Pie Chart** (By Type) | Recharts `PieChart` | `fetchStatistics({groupBy: "type"})` |
| **Bar Chart** (Top Wilayas) | Recharts `BarChart` | `fetchStatistics({groupBy: "wilaya"})` |
| **Recent Tenders** | `TendersTable` (subset) | `fetchTenders({page_size: 5})` |

### Authentication (`LoginPage.tsx`)

- Phone input (Algerian format, auto-normalize to E.164)
- Password (show/hide toggle)
- CSRF token from cookie (`dz_csrf`) → header `X-CSRF-Token`
- `useMutation` for login; on success → redirect to intended page
- Rate limit UI: shows retry-after on 429

---

## Technical Stack

| Category | Technology | Version |
|----------|------------|---------|
| **Framework** | React | 18.3.1 |
| **Language** | TypeScript | 5.6.3 (strict) |
| **Build** | Vite | 5.4.11 |
| **Routing** | React Router DOM | 6.28.0 |
| **Data Fetching** | TanStack Query | 5.56.2 |
| **Table** | TanStack Table | 8.x (via `@tanstack/react-table`) |
| **Charts** | Recharts | 2.13.3 |
| **Maps** | Leaflet + React-Leaflet | 1.9.4 + 4.2.1 |
| **Icons** | Lucide React | 0.468.0 |
| **Styling** | Tailwind CSS | 3.4.15 |
| **HTTP** | Fetch API (native) | — |
| **Mocking** | MSW-style inline | `api.ts` |

---

## Build Analysis

```bash
$ npm run build
# dist/
#   index.html                 0.48 kB  (gzip: 0.34 kB)
#   assets/index-Ce9cKb_p.css  46.63 kB (gzip: 12.44 kB)
#   assets/index-BaYjmRPo.js   861.50 kB (gzip: 244.89 kB)  ⚠️ >500 kB
```

### Bundle Composition (Estimated)

| Package | Est. Size | Reason |
|---------|-----------|--------|
| `recharts` | ~200 kB | 3 chart types + dependencies (`d3-scale`, `d3-shape`) |
| `leaflet` + `react-leaflet` | ~150 kB | Map in `TenderDrawer` |
| `@tanstack/react-query` + `react-table` | ~80 kB | Core data/hooks |
| `lucide-react` | ~80 kB | Tree-shaken but many icons used |
| `react-router-dom` | ~40 kB | Routing |
| **Application code** | ~200 kB | Pages, components, hooks |
| **Runtime** (React, scheduler) | ~110 kB | React 18 production |

### Code-Splitting Opportunities

| Chunk | Components | Est. Savings |
|-------|------------|--------------|
| `dashboard` | `DashboardPage`, `LineChart`, `PieChart`, `BarChart`, `MetricCard` | ~200 kB (Recharts) |
| `map` | `TenderDrawer`, `MapContainer`, Leaflet | ~150 kB |
| `tenders` | `TendersPage`, `TendersTable`, `TenderFilters` | — (core) |
| `auth` | `LoginPage` | ~20 kB |

---

## RTL & Arabic Support

### Implementation
- **HTML**: `<html lang="ar" dir="rtl">` (set in `index.html` + verified in tests)
- **Tailwind**: `rtl:` variant enabled (`tailwind.config.js` → `plugins: [require('tailwindcss-rtl')]` or native v3.4+)
- **Font**: `Cairo` or `Tajawal` (Google Fonts) — loaded in `globals.css`
- **Components**: All use logical properties (`margin-inline-start`, `padding-inline-end`)

### Test Verification
```python
# tests/test_phase1_routes.py:test_home_page_renders_rtl_arabic
assert '<html lang="ar" dir="rtl">' in response.text
```

### Known Gaps
- **Leaflet map**: LTR by default; popup RTL needs custom CSS
- **Recharts**: Tooltip/legend may render LTR; needs `direction: rtl` container
- **Date picker**: Not used (date inputs are native `<input type="date">` — browser handles RTL)
- **Number formatting**: Arabic-Indic digits (٠-٩) not implemented; uses Latin

---

## Accessibility (a11y)

| Criterion | Status | Notes |
|-----------|--------|-------|
| **Semantic HTML** | ✅ Good | `<table>`, `<button>`, `<nav>`, `<main>`, headings hierarchy |
| **Keyboard Navigation** | ⚠️ Partial | Table rows focusable? Drawer focus trap? Modal focus trap? |
| **ARIA Labels** | ⚠️ Partial | Icon-only buttons need `aria-label`; filter selects need `aria-describedby` |
| **Color Contrast** | ❓ Unknown | Tailwind defaults (WCAG AA?) — not verified |
| **Focus Indicators** | ⚠️ Partial | `focus-visible:ring` in Tailwind; check custom components |
| **Screen Reader** | ❓ Unknown | No `live-region` for loading/error states |
| **RTL a11y** | ❓ Unknown | `dir="rtl"` helps; but `aria-orientation` on sliders? |

**No automated a11y testing** (axe-core, jest-axe) in CI.

---

## Responsive Design

| Breakpoint | Tailwind | Status |
|------------|----------|--------|
| **Mobile** (<640px) | Default (mobile-first) | ✅ Stacked layout, collapsible sidebar |
| **Tablet** (640-1024px) | `md:` | ⚠️ Sidebar behavior? Table horizontal scroll? |
| **Desktop** (>1024px) | `lg:`/`xl:` | ✅ Full layout |

**Table on Mobile**: TanStack Table v8 — uses `overflow-x-auto` wrapper; columns don't collapse.

---

## State Management

| State Type | Solution | Scope |
|------------|----------|-------|
| **Server State** | TanStack Query | Global (cache, dedupe, background refetch) |
| **Client State** | React `useState`/`useReducer` | Component-local (filters, drawer open, selection) |
| **Auth State** | `useAuth` hook + context | Session user, login/logout mutations |
| **URL State** | React Router `useSearchParams` | Filters, pagination (shareable URLs) |

**No global client store** (Zustand, Redux) — appropriate for this scale.

---

## Mock Mode (`src/lib/api.ts`)

```typescript
const MOCK_TENDERS: TenderResponse[] = [
  // 20+ realistic Arabic tender objects
];

export async function mockTenders(params: TenderQueryParams): Promise<TenderListResponse> {
  // Client-side filtering, sorting, pagination
  // Simulates API behavior exactly
}
```

**Purpose**: Offline development, Storybook, E2E tests without backend.

**Risk**: Drift from real API schema. **No contract test** — see API-06 in Report 07.

---

## Audit Findings

| ID | Severity | Finding | Evidence | Recommendation |
|----|----------|---------|----------|----------------|
| FE-01 | HIGH | **Bundle size 861 kB** — no code splitting | `npm run build` warning | Dynamic `import()` for Dashboard, Map; `React.lazy` + `Suspense` |
| FE-02 | MEDIUM | **No accessibility testing** | CI lacks axe-core | Add `jest-axe` to unit tests; `cypress-axe` for E2E |
| FE-03 | MEDIUM | **Leaflet map not RTL-aware** | Popups, controls LTR | Custom CSS: `.leaflet-popup-content { direction: rtl }` |
| FE-04 | MEDIUM | **Recharts tooltips/legends LTR** | RTL container not enforced | Wrap charts in `<div dir="rtl">` or CSS `direction: rtl` |
| FE-05 | LOW | **Arabic-Indic digits not used** | Numbers display as 123 not ١٢٣ | `Intl.NumberFormat('ar-DZ').format()` utility |
| FE-06 | LOW | **No virtualization for large tables** | `TendersTable` renders all rows | `react-window` or TanStack Virtual for >100 rows |
| FE-07 | LOW | **Date inputs use browser locale** | `<input type="date">` — inconsistent | Custom date picker (e.g., `react-day-picker` with Arabic) |
| FE-08 | INFO | **No Storybook/Component docs** | Components undocumented | Add Storybook for UI library consistency |
| FE-09 | INFO | **No E2E tests** | Only unit/integration | Add Cypress/Playwright for critical flows (login, search, detail) |
| FE-10 | LOW | **Favicon/App manifest missing** | `index.html` no `<link rel="manifest">` | Add PWA manifest, icons, theme color |

---

## Performance Metrics (Estimated)

| Metric | Current | Target |
|--------|---------|--------|
| **Initial JS (gz)** | 245 kB | <150 kB (with code splitting) |
| **LCP (3G)** | ~3.5s | <2.5s |
| **TTI (3G)** | ~4s | <3s |
| **CLS** | Unknown | <0.1 |
| **FID** | Unknown | <100ms |

**No Real User Monitoring (RUM)** — add `web-vitals` library.

---

## Recommendations

### Immediate (Week 1)
1. **Code-split Dashboard** — `const DashboardPage = lazy(() => import('./pages/DashboardPage'))`
2. **Code-split Map** — `const TenderDrawer = lazy(() => import('./components/tenders/TenderDrawer'))`
3. **Add RTL fixes** for Leaflet + Recharts (CSS only)
4. **Enable gzip/brotli** on static hosting (Vite `build` → `dist/` served by nginx/CDN)

### Short Term (Weeks 2-3)
5. **Add Arabic number formatting utility** — `formatNumberAr(n: number): string`
6. **Add `jest-axe` to component tests** — CI gate on a11y regressions
7. **Virtualize `TendersTable`** — `useVirtualizer` from `@tanstack/react-virtual`
8. **Add PWA manifest** — `vite-plugin-pwa` for offline-capable dashboard

### Medium Term (Month 1-2)
9. **E2E tests with Playwright** — Login → Search → Detail → Favorite flow
10. **Storybook** — Document `Button`, `Input`, `Select`, `Table`, `Drawer`, `Modal`
11. **RUM** — `web-vitals` → send to analytics endpoint
12. **Design system** — Extract `components/ui/` to shared package if multi-app

---

## Component Quality Scorecard

| Component | Type Safety | Test Coverage | A11y | RTL | Bundle Impact |
|-----------|-------------|---------------|------|-----|---------------|
| `TendersPage` | ✅ | ❌ | ⚠️ | ✅ | High (core) |
| `DashboardPage` | ✅ | ❌ | ⚠️ | ⚠️ | High (charts) |
| `TendersTable` | ✅ | ❌ | ⚠️ | ✅ | Medium |
| `TenderDrawer` | ✅ | ❌ | ❌ | ❌ | High (map) |
| `MetricCard` | ✅ | ❌ | ✅ | ✅ | Low |
| `LineChart`/`PieChart`/`BarChart` | ✅ | ❌ | ❌ | ❌ | High (recharts) |
| `LoginPage` | ✅ | ✅ (auth tests) | ⚠️ | ✅ | Low |
| `ui/*` | ✅ | ❌ | ⚠️ | ✅ | Low |

---

## Frontend Scorecard

| Dimension | Score (1-10) | Notes |
|-----------|-------------|-------|
| **Type Safety** | 10 | Strict TS, zero `any`, shared contracts |
| **Architecture** | 8 | Clean hooks, TanStack Query, Router v6 |
| **Performance** | 5 | 861 kB bundle, no code splitting, no virtualization |
| **Accessibility** | 5 | Semantic HTML good; no testing, gaps in ARIA/focus |
| **RTL/Arabic** | 7 | HTML dir, Tailwind RTL, font; map/charts need fixes |
| **Responsive** | 7 | Mobile-first; table overflow, sidebar OK |
| **Developer Experience** | 8 | Mock mode, hot reload, TypeScript, ESLint |
| **Testing** | 5 | Unit only (auth); no component, E2E, a11y, visual |
| **Documentation** | 4 | No Storybook, no component README |
| **Overall** | **6.6** | Functional dashboard; needs perf/a11y investment |