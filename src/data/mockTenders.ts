import type { Product, Tender } from '../types'

const coordinates: Record<string, [number, number]> = {
  الجزائر: [36.7538, 3.0588],
  قسنطينة: [36.365, 6.6147],
  وهران: [35.6971, -0.6308],
  ورقلة: [31.9539, 5.3221],
  بسكرة: [34.8504, 5.7281],
  غرداية: [32.4909, 3.6735],
  أدرار: [27.8743, -0.2939],
  سطيف: [36.1898, 5.4108],
}

interface Seed {
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
  priority: 1 | 2 | 3
  status: 'active' | 'closing_soon' | 'closed'
  reference: string
  estimatedValue: string
}

const seeds: Seed[] = [
  {
    id: 'DZ-2026-001', titleAr: 'اقتناء أنابيب PVC لمشاريع تجديد شبكة توزيع المياه', titleFr: 'Acquisition de conduites PVC pour le renouvellement du réseau d’eau potable', organisation: 'الجزائرية للمياه', organisationShort: 'ADE', wilaya: 'الجزائر', deadline: '2026-10-22', publicationDate: '2026-09-28', products: ['PVC_PIPES'], score: 96, priority: 1, status: 'active', reference: 'ADE/DMR/042/2026', estimatedValue: '28.5 مليون دج',
  },
  {
    id: 'DZ-2026-002', titleAr: 'توريد وتركيب خزانات من البولي إيثيلين بسعة كبيرة', titleFr: 'Fourniture et installation de réservoirs en polyéthylène grand volume', organisation: 'الديوان الوطني للتطهير', organisationShort: 'ONA', wilaya: 'وهران', deadline: '2026-10-13', publicationDate: '2026-09-24', products: ['PE_TANKS'], score: 91, priority: 1, status: 'closing_soon', reference: 'ONA/DG/MP/118/26', estimatedValue: '44 مليون دج',
  },
  {
    id: 'DZ-2026-003', titleAr: 'إنجاز شبكة نقل الغاز الطبيعي للمنطقة الصناعية', titleFr: 'Réalisation du réseau de transport de gaz naturel de la zone industrielle', organisation: 'سونلغاز - مديرية التوزيع', organisationShort: 'Sonelgaz', wilaya: 'قسنطينة', deadline: '2026-11-05', publicationDate: '2026-10-01', products: ['PEHD_PIPES'], score: 88, priority: 2, status: 'active', reference: 'SDC/CONST/2026-77', estimatedValue: '86.2 مليون دج',
  },
  {
    id: 'DZ-2026-004', titleAr: 'اقتناء أنابيب PEHD ومستلزمات الربط لشبكة المياه', titleFr: 'Acquisition de tubes PEHD et accessoires de raccordement du réseau hydraulique', organisation: 'الجزائرية للمياه - وحدة بسكرة', organisationShort: 'ADE', wilaya: 'بسكرة', deadline: '2026-10-18', publicationDate: '2026-09-29', products: ['PEHD_PIPES', 'PVC_PIPES'], score: 86, priority: 2, status: 'active', reference: 'ADE/BISK/ACH/93/26', estimatedValue: '19.8 مليون دج',
  },
  {
    id: 'DZ-2026-005', titleAr: 'تجهيز محطات الضخ بخزانات مياه صناعية', titleFr: 'Équipement des stations de pompage en réservoirs d’eau industriels', organisation: 'سوناطراك - مديرية الجنوب', organisationShort: 'Sonatrach', wilaya: 'ورقلة', deadline: '2026-10-11', publicationDate: '2026-09-20', products: ['PE_TANKS'], score: 83, priority: 2, status: 'closing_soon', reference: 'SH/DPP/OUAR/56/2026', estimatedValue: '31.4 مليون دج',
  },
  {
    id: 'DZ-2026-006', titleAr: 'أشغال إعادة تأهيل شبكة الصرف الصحي الرئيسية', titleFr: 'Travaux de réhabilitation du réseau principal d’assainissement', organisation: 'الديوان الوطني للتطهير - فرع سطيف', organisationShort: 'ONA', wilaya: 'سطيف', deadline: '2026-10-30', publicationDate: '2026-09-30', products: ['PVC_PIPES', 'PEHD_PIPES'], score: 79, priority: 2, status: 'active', reference: 'ONA/SETIF/DR/2026/41', estimatedValue: '52.7 مليون دج',
  },
  {
    id: 'DZ-2026-007', titleAr: 'توفير أنابيب الضغط العالي لمشروع الربط الريفي', titleFr: 'Fourniture de conduites haute pression pour le raccordement rural', organisation: 'الجزائرية للمياه - وحدة غرداية', organisationShort: 'ADE', wilaya: 'غرداية', deadline: '2026-10-16', publicationDate: '2026-09-27', products: ['PEHD_PIPES'], score: 76, priority: 2, status: 'active', reference: 'ADE/GHAR/2026/117', estimatedValue: '14.1 مليون دج',
  },
  {
    id: 'DZ-2026-008', titleAr: 'اقتناء خزانات لتخزين المياه الصالحة للشرب', titleFr: 'Acquisition de citernes de stockage d’eau potable', organisation: 'الجزائرية للمياه - وحدة أدرار', organisationShort: 'ADE', wilaya: 'أدرار', deadline: '2026-10-27', publicationDate: '2026-10-02', products: ['PE_TANKS'], score: 74, priority: 3, status: 'active', reference: 'ADE/ADR/EXP/2026/08', estimatedValue: '9.6 مليون دج',
  },
  {
    id: 'DZ-2026-009', titleAr: 'توسعة شبكة توزيع المياه الصالحة للشرب', titleFr: 'Extension du réseau de distribution d’eau potable', organisation: 'الجزائرية للمياه - وحدة وهران', organisationShort: 'ADE', wilaya: 'وهران', deadline: '2026-11-12', publicationDate: '2026-10-03', products: ['PVC_PIPES'], score: 72, priority: 3, status: 'active', reference: 'ADE/ORAN/DRH/62/26', estimatedValue: '37.9 مليون دج',
  },
  {
    id: 'DZ-2026-010', titleAr: 'أشغال مد شبكة الغاز لفائدة التجمعات السكنية', titleFr: 'Travaux d’extension du réseau de gaz au profit des agglomérations', organisation: 'سونلغاز - مديرية التوزيع', organisationShort: 'Sonelgaz', wilaya: 'أدرار', deadline: '2026-10-09', publicationDate: '2026-09-18', products: ['PEHD_PIPES'], score: 70, priority: 3, status: 'closing_soon', reference: 'SG/ADR/RESEAU/33/26', estimatedValue: '23.6 مليون دج',
  },
  {
    id: 'DZ-2026-011', titleAr: 'تجديد قنوات الصرف الصحي للمجمعات الحضرية', titleFr: 'Renouvellement des conduites d’assainissement des pôles urbains', organisation: 'الديوان الوطني للتطهير', organisationShort: 'ONA', wilaya: 'الجزائر', deadline: '2026-10-25', publicationDate: '2026-09-30', products: ['PVC_PIPES'], score: 69, priority: 3, status: 'active', reference: 'ONA/CENTRE/2026/209', estimatedValue: '46.3 مليون دج',
  },
  {
    id: 'DZ-2026-012', titleAr: 'توريد أنابيب بلاستيكية لمشاريع السقي الفلاحي', titleFr: 'Fourniture de canalisations plastiques pour l’irrigation agricole', organisation: 'سوناطراك - مديرية المشتريات', organisationShort: 'Sonatrach', wilaya: 'بسكرة', deadline: '2026-10-20', publicationDate: '2026-09-25', products: ['PEHD_PIPES', 'PVC_PIPES'], score: 67, priority: 3, status: 'active', reference: 'SH/ACH/AGRI/2026/92', estimatedValue: '17.5 مليون دج',
  },
  {
    id: 'DZ-2026-013', titleAr: 'اقتناء خزانات بلاستيكية أفقية وعمودية', titleFr: 'Acquisition de réservoirs plastiques horizontaux et verticaux', organisation: 'الجزائرية للمياه', organisationShort: 'ADE', wilaya: 'قسنطينة', deadline: '2026-11-03', publicationDate: '2026-10-01', products: ['PE_TANKS'], score: 65, priority: 3, status: 'active', reference: 'ADE/CONS/DS/2026/71', estimatedValue: '11.2 مليون دج',
  },
  {
    id: 'DZ-2026-014', titleAr: 'إنجاز شبكة المياه الصالحة للشرب لقرى الهضاب', titleFr: 'Réalisation du réseau d’eau potable des villages des Hauts-Plateaux', organisation: 'الجزائرية للمياه - وحدة سطيف', organisationShort: 'ADE', wilaya: 'سطيف', deadline: '2026-10-14', publicationDate: '2026-09-19', products: ['PEHD_PIPES'], score: 63, priority: 3, status: 'closing_soon', reference: 'ADE/SETIF/AEP/2026/38', estimatedValue: '21.8 مليون دج',
  },
  {
    id: 'DZ-2026-015', titleAr: 'أشغال حماية وتحويل قنوات نقل الغاز', titleFr: 'Travaux de protection et de déviation des conduites de transport de gaz', organisation: 'سونلغاز - مديرية التوزيع', organisationShort: 'Sonelgaz', wilaya: 'الجزائر', deadline: '2026-11-18', publicationDate: '2026-10-04', products: ['PEHD_PIPES'], score: 61, priority: 3, status: 'active', reference: 'SDC/ALG/PROT/2026/104', estimatedValue: '63.1 مليون دج',
  },
  {
    id: 'DZ-2026-016', titleAr: 'إنجاز أحواض وخزانات لتجميع مياه الأمطار', titleFr: 'Réalisation de bassins et réservoirs de collecte des eaux pluviales', organisation: 'الديوان الوطني للتطهير', organisationShort: 'ONA', wilaya: 'غرداية', deadline: '2026-10-29', publicationDate: '2026-09-23', products: ['PE_TANKS'], score: 60, priority: 3, status: 'active', reference: 'ONA/GHAR/EAU/22/26', estimatedValue: '8.9 مليون دج',
  },
  {
    id: 'DZ-2026-017', titleAr: 'اقتناء ملحقات وأنابيب PVC لشبكة التوزيع', titleFr: 'Acquisition d’accessoires et tubes PVC pour le réseau de distribution', organisation: 'الجزائرية للمياه - وحدة وهران', organisationShort: 'ADE', wilaya: 'وهران', deadline: '2026-10-08', publicationDate: '2026-09-16', products: ['PVC_PIPES'], score: 58, priority: 3, status: 'closing_soon', reference: 'ADE/ORAN/LOG/2026/44', estimatedValue: '12.7 مليون دج',
  },
  {
    id: 'DZ-2026-018', titleAr: 'توريد أنابيب PEHD لمشروع نقل المياه الجوفية', titleFr: 'Fourniture de conduites PEHD pour le transfert des eaux souterraines', organisation: 'الجزائرية للمياه - وحدة ورقلة', organisationShort: 'ADE', wilaya: 'ورقلة', deadline: '2026-10-23', publicationDate: '2026-09-22', products: ['PEHD_PIPES'], score: 56, priority: 3, status: 'active', reference: 'ADE/OUAR/TRANS/2026/18', estimatedValue: '26.5 مليون دج',
  },
  {
    id: 'DZ-2026-019', titleAr: 'اقتناء خزانات مياه لفائدة المنشآت الصناعية', titleFr: 'Acquisition de réservoirs d’eau au profit des installations industrielles', organisation: 'سوناطراك - مديرية الجنوب', organisationShort: 'Sonatrach', wilaya: 'ورقلة', deadline: '2026-10-31', publicationDate: '2026-09-26', products: ['PE_TANKS'], score: 54, priority: 3, status: 'active', reference: 'SH/DPS/OUAR/2026/84', estimatedValue: '35.6 مليون دج',
  },
  {
    id: 'DZ-2026-020', titleAr: 'إعادة تأهيل قنوات الصرف بحي المدينة الجديدة', titleFr: 'Réhabilitation des conduites d’assainissement de la nouvelle ville', organisation: 'الديوان الوطني للتطهير - فرع قسنطينة', organisationShort: 'ONA', wilaya: 'قسنطينة', deadline: '2026-10-17', publicationDate: '2026-09-21', products: ['PVC_PIPES'], score: 52, priority: 3, status: 'active', reference: 'ONA/CONS/URB/2026/57', estimatedValue: '18.2 مليون دج',
  },
  {
    id: 'DZ-2026-021', titleAr: 'إنجاز شبكة تزويد بالمياه للمنطقة الجنوبية', titleFr: 'Réalisation du réseau d’alimentation en eau de la zone sud', organisation: 'الجزائرية للمياه - وحدة أدرار', organisationShort: 'ADE', wilaya: 'أدرار', deadline: '2026-10-06', publicationDate: '2026-09-05', products: ['PEHD_PIPES'], score: 49, priority: 3, status: 'closed', reference: 'ADE/ADR/AEP/2026/02', estimatedValue: '16.9 مليون دج',
  },
  {
    id: 'DZ-2026-022', titleAr: 'توريد تجهيزات تخزين ونقل المياه', titleFr: 'Fourniture d’équipements de stockage et de transport d’eau', organisation: 'الجزائرية للمياه', organisationShort: 'ADE', wilaya: 'بسكرة', deadline: '2026-09-29', publicationDate: '2026-08-30', products: ['PE_TANKS'], score: 47, priority: 3, status: 'closed', reference: 'ADE/BISK/STO/2026/11', estimatedValue: '7.4 مليون دج',
  },
  {
    id: 'DZ-2026-023', titleAr: 'أشغال وضع أنابيب الغاز بأحياء التوسعة العمرانية', titleFr: 'Pose de conduites de gaz dans les quartiers d’extension urbaine', organisation: 'سونلغاز - مديرية التوزيع', organisationShort: 'Sonelgaz', wilaya: 'وهران', deadline: '2026-10-19', publicationDate: '2026-09-15', products: ['PEHD_PIPES'], score: 45, priority: 3, status: 'active', reference: 'SDC/ORAN/EXT/2026/49', estimatedValue: '29.3 مليون دج',
  },
  {
    id: 'DZ-2026-024', titleAr: 'صيانة واستبدال خزانات المياه بالمحطات', titleFr: 'Maintenance et remplacement des réservoirs d’eau des stations', organisation: 'الديوان الوطني للتطهير', organisationShort: 'ONA', wilaya: 'أدرار', deadline: '2026-11-08', publicationDate: '2026-10-02', products: ['PE_TANKS'], score: 43, priority: 3, status: 'active', reference: 'ONA/ADR/MAINT/2026/16', estimatedValue: '6.8 مليون دج',
  },
  {
    id: 'DZ-2026-025', titleAr: 'توسعة شبكة المياه للقطب الحضري الجديد', titleFr: 'Extension du réseau d’eau du nouveau pôle urbain', organisation: 'الجزائرية للمياه - وحدة غرداية', organisationShort: 'ADE', wilaya: 'غرداية', deadline: '2026-09-25', publicationDate: '2026-08-28', products: ['PVC_PIPES', 'PEHD_PIPES'], score: 41, priority: 3, status: 'closed', reference: 'ADE/GHAR/URB/2026/27', estimatedValue: '13.6 مليون دج',
  },
  {
    id: 'DZ-2026-026', titleAr: 'اقتناء أنابيب ومعدات لشبكة الري', titleFr: 'Acquisition de tubes et équipements pour le réseau d’irrigation', organisation: 'سوناطراك - مديرية المشتريات', organisationShort: 'Sonatrach', wilaya: 'بسكرة', deadline: '2026-11-15', publicationDate: '2026-10-01', products: ['PVC_PIPES'], score: 39, priority: 3, status: 'active', reference: 'SH/ACH/IRR/2026/63', estimatedValue: '10.5 مليون دج',
  },
  {
    id: 'DZ-2026-027', titleAr: 'إعادة تأهيل قناة المياه الرئيسية لمدينة سطيف', titleFr: 'Réhabilitation de la conduite principale d’eau de la ville de Sétif', organisation: 'الجزائرية للمياه - وحدة سطيف', organisationShort: 'ADE', wilaya: 'سطيف', deadline: '2026-09-18', publicationDate: '2026-08-22', products: ['PEHD_PIPES'], score: 37, priority: 3, status: 'closed', reference: 'ADE/SETIF/MAIN/2026/18', estimatedValue: '24.7 مليون دج',
  },
  {
    id: 'DZ-2026-028', titleAr: 'توريد أنابيب الصرف الصحي لمشروع سكني', titleFr: 'Fourniture de conduites d’assainissement pour un projet résidentiel', organisation: 'الديوان الوطني للتطهير - فرع سطيف', organisationShort: 'ONA', wilaya: 'سطيف', deadline: '2026-10-28', publicationDate: '2026-09-29', products: ['PVC_PIPES'], score: 35, priority: 3, status: 'active', reference: 'ONA/SETIF/HAB/2026/89', estimatedValue: '15.1 مليون دج',
  },
  {
    id: 'DZ-2026-029', titleAr: 'إنجاز وتجهيز خزانات مياه للمناطق النائية', titleFr: 'Réalisation et équipement de réservoirs d’eau pour les zones enclavées', organisation: 'الجزائرية للمياه - وحدة ورقلة', organisationShort: 'ADE', wilaya: 'ورقلة', deadline: '2026-10-12', publicationDate: '2026-09-17', products: ['PE_TANKS'], score: 33, priority: 3, status: 'closing_soon', reference: 'ADE/OUAR/RUR/2026/44', estimatedValue: '12.9 مليون دج',
  },
  {
    id: 'DZ-2026-030', titleAr: 'أشغال صيانة شبكة التوزيع واستبدال القنوات', titleFr: 'Travaux de maintenance du réseau de distribution et remplacement des conduites', organisation: 'الجزائرية للمياه - وحدة الجزائر', organisationShort: 'ADE', wilaya: 'الجزائر', deadline: '2026-09-12', publicationDate: '2026-08-18', products: ['PVC_PIPES', 'PEHD_PIPES'], score: 31, priority: 3, status: 'closed', reference: 'ADE/ALG/MAINT/2026/72', estimatedValue: '20.4 مليون دج',
  },
]

export const mockTenders: Tender[] = seeds.map((tender) => {
  const [latitude, longitude] = coordinates[tender.wilaya]
  return {
    ...tender,
    description: `يهدف هذا المشروع إلى دعم وتطوير البنية التحتية للمياه والطاقة في ولاية ${tender.wilaya}، وفقاً للمعايير التقنية المعتمدة. تشمل الصفقة التوريد والنقل والتسليم في الموقع مع الالتزام بآجال الإنجاز المحددة.`,
    source: tender.organisationShort === 'ADE' ? 'الجزائرية للمياه' : tender.organisationShort === 'ONA' ? 'الديوان الوطني للتطهير' : tender.organisationShort,
    sourceUrl: `https://www.marches-publics.gov.dz/tender/${tender.id}`,
    latitude,
    longitude,
  }
})

export const productLabels: Record<Product, string> = {
  PVC_PIPES: 'أنابيب PVC',
  PEHD_PIPES: 'أنابيب PEHD',
  PE_TANKS: 'خزانات PE',
}

export const productShortLabels: Record<Product, string> = {
  PVC_PIPES: 'PVC',
  PEHD_PIPES: 'PEHD',
  PE_TANKS: 'خزانات',
}

export const wilayas = Object.keys(coordinates)
export const organisations = ['ADE', 'ONA', 'Sonelgaz', 'Sonatrach']
