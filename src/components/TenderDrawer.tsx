import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpLeft, CalendarDays, ExternalLink, Heart, MapPin, X } from 'lucide-react'
import { CircleMarker, MapContainer, TileLayer } from 'react-leaflet'
import type { Tender } from '../types'
import { fetchTender } from '../lib/api'
import { formatDate, getDaysRemaining, PriorityBadge, ProductTag, Score, StatusBadge, cn } from './shared'

interface TenderDrawerProps {
  tender: Tender | null
  onClose: () => void
  isFavorite: boolean
  onToggleFavorite: (id: string) => void
}

export function TenderDrawer({ tender, onClose, isFavorite, onToggleFavorite }: TenderDrawerProps): JSX.Element | null {
  useEffect(() => {
    if (!tender) return undefined
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKeyDown)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKeyDown); document.body.style.overflow = '' }
  }, [tender, onClose])

  const detailQuery = useQuery({
    queryKey: ['tender', tender?.id],
    queryFn: () => fetchTender(tender?.id ?? ''),
    enabled: Boolean(tender),
    initialData: tender ?? undefined,
  })
  if (!tender) return null
  const detail = detailQuery.data ?? tender
  const days = getDaysRemaining(detail.deadline)
  const isClosed = detail.status === 'closed'
  return <>
    <div className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-[2px]" onClick={onClose} />
    <aside className="fixed inset-y-0 left-0 z-50 flex w-full max-w-[570px] flex-col overflow-hidden bg-white shadow-2xl dark:bg-slate-900" role="dialog" aria-modal="true" aria-label="تفاصيل المناقصة">
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700"><div className="flex items-center gap-2 text-xs font-semibold text-slate-500"><button onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"><X size={19} /></button><span>تفاصيل المناقصة</span></div><button onClick={() => onToggleFavorite(detail.id)} className={cn('flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-bold transition-colors', isFavorite ? 'border-red-100 bg-red-50 text-red-600 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300' : 'border-slate-200 text-slate-500 hover:border-brand-100 hover:text-brand-500 dark:border-slate-700')}><Heart size={15} fill={isFavorite ? 'currentColor' : 'none'} />{isFavorite ? 'محفوظة' : 'حفظ للمفضلة'}</button></div>
      <div className="flex-1 overflow-y-auto">
        <div className="border-b border-slate-100 bg-gradient-to-br from-brand-50 via-white to-white px-6 py-6 dark:border-slate-800 dark:from-brand-500/10 dark:via-slate-900 dark:to-slate-900"><div className="flex items-center justify-between gap-3"><span className="text-[11px] font-bold text-brand-500">{detail.reference}</span><StatusBadge status={detail.status} /></div><h2 className="mt-4 text-xl font-extrabold leading-[1.7] text-ink dark:text-white">{detail.titleAr}</h2><p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">{detail.titleFr}</p><div className="mt-5 flex flex-wrap items-center gap-2"><PriorityBadge priority={detail.priority} /><span className="text-xs text-slate-400">أولوية {detail.priority}</span><span className="mx-1 h-4 w-px bg-slate-200 dark:bg-slate-700" /><span className="text-xs text-slate-500 dark:text-slate-400">درجة المطابقة</span><Score value={detail.score} /></div></div>
        <div className="space-y-6 px-6 py-6"><div className="grid grid-cols-2 gap-3"><InfoItem label="الجهة المنظمة" value={detail.organisation} /><InfoItem label="الولاية" value={detail.wilaya} icon={<MapPin size={14} />} /></div><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/60"><div className="flex items-center justify-between"><div className="flex items-center gap-2 text-slate-500 dark:text-slate-400"><CalendarDays size={17} /><span className="text-xs font-semibold">آخر أجل لإيداع العروض</span></div>{isClosed ? <span className="text-xs font-bold text-slate-400">انتهى الأجل</span> : <span className={cn('text-xs font-bold', days <= 7 ? 'text-red-500' : 'text-emerald-600')}>{days} أيام متبقية</span>}</div><p className="mt-3 text-lg font-extrabold text-ink dark:text-white">{formatDate(detail.deadline)}</p><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"><div className={cn('h-full rounded-full', isClosed ? 'w-full bg-slate-300' : days <= 7 ? 'w-[82%] bg-red-400' : 'w-[55%] bg-brand-500')} /></div></div><div><p className="mb-3 text-sm font-bold text-ink dark:text-white">المنتجات المطابقة</p><div className="flex flex-wrap gap-2">{detail.products.map((product) => <ProductTag key={product} product={product} />)}</div></div><div><p className="mb-2 text-sm font-bold text-ink dark:text-white">نبذة عن المشروع</p><p className="text-[13px] leading-7 text-slate-500 dark:text-slate-400">{detail.description}</p></div><div><p className="mb-3 text-sm font-bold text-ink dark:text-white">موقع المشروع</p><div className="h-[190px] overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700"><MapContainer key={detail.id} center={[detail.latitude, detail.longitude]} zoom={9} scrollWheelZoom={false} zoomControl={false} className="h-full w-full"><TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" /><CircleMarker center={[detail.latitude, detail.longitude]} radius={10} pathOptions={{ color: '#1a5490', fillColor: '#1a5490', fillOpacity: 0.85, weight: 3 }} /></MapContainer></div><div className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-400"><MapPin size={12} />{detail.wilaya}، الجزائر</div></div><div className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3 dark:bg-slate-800/60"><div><p className="text-[11px] text-slate-400">تاريخ النشر</p><p className="mt-1 text-xs font-bold text-slate-600 dark:text-slate-300">{formatDate(detail.publicationDate)}</p></div><div className="text-left"><p className="text-[11px] text-slate-400">القيمة التقديرية</p><p className="mt-1 text-xs font-bold text-slate-600 dark:text-slate-300">{detail.estimatedValue}</p></div></div></div>
      </div>
      <div className="border-t border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"><a href={detail.sourceUrl} target="_blank" rel="noreferrer" className="flex h-11 items-center justify-center gap-2 rounded-xl bg-brand-500 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition-colors hover:bg-brand-600">عرض الإعلان الأصلي <ArrowUpLeft size={17} /><ExternalLink size={14} /></a></div>
    </aside>
  </>
}

function InfoItem({ label, value, icon }: { label: string; value: string; icon?: JSX.Element }): JSX.Element {
  return <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700"><p className="text-[11px] text-slate-400">{label}</p><p className="mt-2 flex items-center gap-1.5 text-xs font-bold text-ink dark:text-slate-200">{icon}<span>{value}</span></p></div>
}
