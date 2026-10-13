import { useEffect, useState, type ComponentType, type FormEvent, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  BarChart3,
  Bell,
  ChevronLeft,
  CircleHelp,
  Database,
  FileText,
  Heart,
  LayoutDashboard,
  Menu,
  Moon,
  Search,
  Settings,
  Sun,
  X,
} from 'lucide-react'
import type { LucideProps } from 'lucide-react'
import { productLabels } from '../data/mockTenders'
import type { Product, Priority, Tender } from '../types'

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

export function formatDate(value: string | null): string {
  if (!value) return 'غير محدد'
  return new Date(`${value}T12:00:00`).toLocaleDateString('ar-DZ', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

export function formatDateCompact(value: string | null): string {
  if (!value) return 'غير محدد'
  return new Date(`${value}T12:00:00`).toLocaleDateString('ar-DZ', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function getDaysRemaining(deadline: string | null): number {
  if (!deadline) return 0
  const today = new Date('2026-10-06T12:00:00')
  const end = new Date(`${deadline}T23:59:59`)
  return Math.ceil((end.getTime() - today.getTime()) / 86_400_000)
}

export function productLabel(product: Product): string {
  return productLabels[product]
}

export function PriorityBadge({ priority }: { priority: Priority }): JSX.Element {
  const styles: Record<Priority, string> = {
    1: 'bg-red-50 text-red-600 ring-red-100 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/20',
    2: 'bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20',
    3: 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-slate-700/60 dark:text-slate-300 dark:ring-slate-600',
  }
  return <span className={cn('inline-flex h-7 min-w-7 items-center justify-center rounded-full px-2 text-xs font-bold ring-1', styles[priority])}>{priority}</span>
}

export function StatusBadge({ status }: { status: Tender['status'] }): JSX.Element {
  const copy = {
    active: 'نشطة',
    closing_soon: 'تغلق قريباً',
    closed: 'مغلقة',
  }[status]
  const styles = {
    active: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 dark:text-emerald-300',
    closing_soon: 'text-amber-700 bg-amber-50 dark:bg-amber-500/10 dark:text-amber-300',
    closed: 'text-slate-500 bg-slate-100 dark:bg-slate-700/60 dark:text-slate-300',
  }[status]
  return <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold', styles)}><span className="h-1.5 w-1.5 rounded-full bg-current" />{copy}</span>
}

export function ProductTag({ product, compact = false }: { product: Product; compact?: boolean }): JSX.Element {
  const styles: Record<Product, string> = {
    PVC_PIPES: 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300',
    PEHD_PIPES: 'bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300',
    PE_TANKS: 'bg-orange-50 text-orange-700 dark:bg-orange-500/10 dark:text-orange-300',
  }
  const labels: Record<Product, string> = {
    PVC_PIPES: compact ? 'PVC' : 'أنابيب PVC',
    PEHD_PIPES: compact ? 'PEHD' : 'أنابيب PEHD',
    PE_TANKS: compact ? 'خزانات PE' : 'خزانات PE',
  }
  return <span className={cn('inline-flex items-center rounded-md px-2 py-1 text-[11px] font-semibold', styles[product])}>{labels[product]}</span>
}

export function Score({ value }: { value: number }): JSX.Element {
  const tone = value >= 80 ? 'text-emerald-600' : value >= 60 ? 'text-brand-500' : 'text-slate-500'
  return <span className={cn('font-bold tabular-nums', tone)}>{value}<span className="mr-0.5 text-[10px] font-medium">%</span></span>
}

interface MetricCardProps {
  title: string
  value: string | number
  hint: string
  icon: ComponentType<LucideProps>
  iconClass: string
  trend?: string
  trendDown?: boolean
}

export function MetricCard({ title, value, hint, icon: Icon, iconClass, trend, trendDown }: MetricCardProps): JSX.Element {
  return (
    <div className="group rounded-2xl border border-slate-200/80 bg-white p-5 shadow-soft transition-all hover:-translate-y-0.5 hover:shadow-lg dark:border-slate-700/70 dark:bg-slate-800/80">
      <div className="flex items-start justify-between gap-3">
        <div className={cn('flex h-11 w-11 items-center justify-center rounded-xl', iconClass)}><Icon size={21} strokeWidth={1.8} /></div>
        {trend && <span className={cn('rounded-full px-2 py-1 text-[11px] font-bold', trendDown ? 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300' : 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300')}>{trend}</span>}
      </div>
      <p className="mt-4 text-[13px] font-medium text-slate-500 dark:text-slate-400">{title}</p>
      <div className="mt-1 flex items-baseline gap-2"><p className="text-2xl font-extrabold tracking-tight text-ink dark:text-white">{value}</p><span className="text-xs text-slate-400">{hint}</span></div>
    </div>
  )
}

export function SectionHeading({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }): JSX.Element {
  return <div className="mb-5 flex items-end justify-between gap-4"><div><h2 className="text-[17px] font-bold text-ink dark:text-white">{title}</h2>{subtitle && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}</div>{action}</div>
}

function Logo(): JSX.Element {
  return <div className="flex items-center gap-3"><div className="relative flex h-10 w-10 items-center justify-center overflow-hidden rounded-xl bg-brand-500 shadow-lg shadow-brand-500/20"><div className="absolute -left-2 -top-2 h-7 w-7 rounded-full border-[3px] border-white/20" /><Database className="relative text-white" size={21} strokeWidth={1.8} /></div><div><p className="text-[15px] font-extrabold leading-tight text-ink dark:text-white">منصة المناقصات</p><p className="mt-0.5 text-[9px] font-bold uppercase tracking-[0.22em] text-brand-500">DZ TENDERS</p></div></div>
}

interface SidebarProps { open: boolean; onClose: () => void }

export function Sidebar({ open, onClose }: SidebarProps): JSX.Element {
  const location = useLocation()
  const navItems = [
    { to: '/', label: 'نظرة عامة', icon: LayoutDashboard, end: true },
    { to: '/tenders', label: 'المناقصات', icon: FileText },
    { to: '/statistics', label: 'الإحصائيات', icon: BarChart3 },
  ]
  return <>
    {open && <button aria-label="إغلاق القائمة" onClick={onClose} className="fixed inset-0 z-30 bg-slate-900/30 backdrop-blur-sm lg:hidden" />}
    <aside className={cn('fixed inset-y-0 right-0 z-40 flex w-[264px] flex-col border-l border-slate-200 bg-white px-4 py-5 transition-transform duration-300 dark:border-slate-700 dark:bg-slate-900 lg:translate-x-0', open ? 'translate-x-0' : 'translate-x-full')}>
      <div className="flex items-center justify-between px-2"><Logo /><button onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 lg:hidden dark:hover:bg-slate-800"><X size={18} /></button></div>
      <div className="mt-9 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">القائمة الرئيسية</div>
      <nav className="mt-3 space-y-1">
        {navItems.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} onClick={onClose} className={({ isActive }) => cn('group flex items-center gap-3 rounded-xl px-3 py-3 text-[13px] font-semibold transition-colors', isActive ? 'bg-brand-50 text-brand-500 dark:bg-brand-500/10 dark:text-blue-300' : 'text-slate-500 hover:bg-slate-50 hover:text-ink dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white')}><Icon size={19} strokeWidth={1.8} /><span>{label}</span>{location.pathname === to && <span className="mr-auto h-1.5 w-1.5 rounded-full bg-brand-500" />}</NavLink>)}
      </nav>
      <div className="mt-8 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">مساحة العمل</div>
      <nav className="mt-3 space-y-1">
        <NavLink to="/tenders" onClick={onClose} className="flex items-center gap-3 rounded-xl px-3 py-3 text-[13px] font-semibold text-slate-500 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800"><Heart size={19} strokeWidth={1.8} /><span>المفضلة</span><span className="mr-auto rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800">8</span></NavLink>
        <button className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-[13px] font-semibold text-slate-500 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800"><Settings size={19} strokeWidth={1.8} /><span>الإعدادات</span></button>
      </nav>
      <div className="mt-auto rounded-2xl bg-brand-50 p-4 dark:bg-brand-500/10"><div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-white"><CircleHelp size={17} /></div><p className="text-xs font-bold text-ink dark:text-white">هل تحتاج إلى مساعدة؟</p><p className="mt-1 text-[11px] leading-5 text-slate-500 dark:text-slate-400">فريق الدعم متاح للإجابة عن استفساراتك.</p><button className="mt-3 text-[11px] font-bold text-brand-500">تواصل معنا <ChevronLeft className="mr-1 inline" size={13} /></button></div>
      <p className="mt-4 text-center text-[10px] text-slate-400">الإصدار 1.0.0 · 2026</p>
    </aside>
  </>
}

export function Topbar({ onMenu, darkMode, onToggleDark }: { onMenu: () => void; darkMode: boolean; onToggleDark: () => void }): JSX.Element {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (search.trim()) navigate(`/tenders?search=${encodeURIComponent(search.trim())}`)
  }
  return <header className="sticky top-0 z-20 flex h-[76px] items-center justify-between border-b border-slate-200/80 bg-canvas/90 px-5 backdrop-blur-md dark:border-slate-700/70 dark:bg-slate-950/85 lg:px-9"><div className="flex items-center gap-3"><button onClick={onMenu} className="rounded-xl p-2 text-slate-500 hover:bg-white lg:hidden dark:hover:bg-slate-800"><Menu size={21} /></button><form onSubmit={submitSearch} className="hidden h-10 w-[290px] items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-slate-400 sm:flex dark:border-slate-700 dark:bg-slate-800"><Search size={17} /><input aria-label="بحث" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ابحث عن مناقصة، جهة..." className="w-full bg-transparent text-xs text-ink outline-none placeholder:text-slate-400 dark:text-white" /></form></div><div className="flex items-center gap-2 sm:gap-4"><button onClick={onToggleDark} aria-label="تغيير المظهر" className="rounded-xl p-2.5 text-slate-500 transition-colors hover:bg-white hover:text-brand-500 dark:hover:bg-slate-800">{darkMode ? <Sun size={18} /> : <Moon size={18} />}</button><button aria-label="الإشعارات" className="relative rounded-xl p-2.5 text-slate-500 hover:bg-white dark:hover:bg-slate-800"><Bell size={19} /><span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-red-500 ring-2 ring-canvas" /></button><div className="h-7 w-px bg-slate-200 dark:bg-slate-700" /><div className="flex items-center gap-2"><div className="hidden text-left sm:block"><p className="text-xs font-bold text-ink dark:text-white">أحمد بن عمر</p><p className="mt-0.5 text-[10px] text-slate-400">مدير المشتريات</p></div><div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-cyan-500 text-xs font-bold text-white">أب</div></div></div></header>
}

export function useDarkMode(): [boolean, () => void] {
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('dz-tenders-theme') === 'dark')
  useEffect(() => { document.documentElement.classList.toggle('dark', darkMode); localStorage.setItem('dz-tenders-theme', darkMode ? 'dark' : 'light') }, [darkMode])
  return [darkMode, () => setDarkMode((value) => !value)]
}

export function PageLoader(): JSX.Element {
  return <div className="flex min-h-[50vh] items-center justify-center"><div className="h-9 w-9 animate-spin rounded-full border-2 border-brand-100 border-t-brand-500" /></div>
}

export function EmptyState({ title = 'لا توجد نتائج', description = 'جرّب تغيير خيارات البحث أو الفلترة.' }: { title?: string; description?: string }): JSX.Element {
  return <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white px-5 py-16 text-center dark:border-slate-700 dark:bg-slate-800/50"><div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 dark:bg-slate-700"><Search size={21} /></div><p className="mt-4 font-bold text-ink dark:text-white">{title}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{description}</p></div>
}
