# Ported from validatorjs/validator.js (MIT). Data tables.
"""Static lookup tables for the validator port (ISO codes, IBAN, locale alphabets)."""

from __future__ import annotations

ALPHA = {
    'en-US': ('^[A-Z]+$', True),
    'az-AZ': ('^[A-VXYZÇƏĞİıÖŞÜ]+$', True),
    'bg-BG': ('^[А-Я]+$', True),
    'cs-CZ': ('^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]+$', True),
    'da-DK': ('^[A-ZÆØÅ]+$', True),
    'de-DE': ('^[A-ZÄÖÜß]+$', True),
    'el-GR': ('^[Α-ώ]+$', True),
    'es-ES': ('^[A-ZÁÉÍÑÓÚÜ]+$', True),
    'fa-IR': ('^[ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی]+$', True),
    'fi-FI': ('^[A-ZÅÄÖ]+$', True),
    'fr-FR': ('^[A-ZÀÂÆÇÉÈÊËÏÎÔŒÙÛÜŸ]+$', True),
    'it-IT': ('^[A-ZÀÉÈÌÎÓÒÙ]+$', True),
    'ja-JP': ('^[ぁ-んァ-ヶｦ-ﾟ一-龠ー・。、]+$', True),
    'nb-NO': ('^[A-ZÆØÅ]+$', True),
    'nl-NL': ('^[A-ZÁÉËÏÓÖÜÚ]+$', True),
    'nn-NO': ('^[A-ZÆØÅ]+$', True),
    'hu-HU': ('^[A-ZÁÉÍÓÖŐÚÜŰ]+$', True),
    'pl-PL': ('^[A-ZĄĆĘŚŁŃÓŻŹ]+$', True),
    'pt-PT': ('^[A-ZÃÁÀÂÄÇÉÊËÍÏÕÓÔÖÚÜ]+$', True),
    'ru-RU': ('^[А-ЯЁ]+$', True),
    'kk-KZ': ('^[А-ЯЁ\\u04D8\\u04B0\\u0406\\u04A2\\u0492\\u04AE\\u049A\\u04E8\\u04BA]+$', True),
    'sl-SI': ('^[A-ZČĆĐŠŽ]+$', True),
    'sk-SK': ('^[A-ZÁČĎÉÍŇÓŠŤÚÝŽĹŔĽÄÔ]+$', True),
    'sr-RS@latin': ('^[A-ZČĆŽŠĐ]+$', True),
    'sr-RS': ('^[А-ЯЂЈЉЊЋЏ]+$', True),
    'sv-SE': ('^[A-ZÅÄÖ]+$', True),
    'th-TH': ('^[ก-๐\\s]+$', True),
    'tr-TR': ('^[A-ZÇĞİıÖŞÜ]+$', True),
    'uk-UA': ('^[А-ЩЬЮЯЄIЇҐі]+$', True),
    'vi-VN': ('^[A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴĐÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸ]+$', True),
    'ko-KR': ('^[ㄱ-ㅎㅏ-ㅣ가-힣]*$', False),
    'ku-IQ': ('^[ئابپتجچحخدرڕزژسشعغفڤقکگلڵمنوۆھەیێيطؤثآإأكضصةظذ]+$', True),
    'ar': ('^[ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهوىيًٌٍَُِّْٰ]+$', False),
    'he': ('^[א-ת]+$', False),
    'fa': ("^['آاءأؤئبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهةی']+$", True),
    'bn': ("^['ঀঁংঃঅআইঈউঊঋঌএঐওঔকখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহ়ঽািীুূৃৄেৈোৌ্ৎৗড়ঢ়য়ৠৡৢৣৰৱ৲৳৴৵৶৷৸৹৺৻']+$", False),
    'eo': ('^[ABCĈD-GĜHĤIJĴK-PRSŜTUŬVZ]+$', True),
    'hi-IN': ('^[\\u0900-\\u0961]+[\\u0972-\\u097F]*$', True),
    'si-LK': ('^[\\u0D80-\\u0DFF]+$', False),
    'ta-IN': ('^[\\u0B80-\\u0BFF]+$', True),
    'te-IN': ('^[\\u0C00-\\u0C7F]+$', True),
    'kn-IN': ('^[\\u0C80-\\u0CFF]+$', True),
    'ml-IN': ('^[\\u0D00-\\u0D7F]+$', True),
    'gu-IN': ('^[\\u0A80-\\u0AFF]+$', True),
    'pa-IN': ('^[\\u0A00-\\u0A7F]+$', True),
    'or-IN': ('^[\\u0B00-\\u0B7F]+$', True),
}

ALPHANUMERIC = {
    'en-US': ('^[0-9A-Z]+$', True),
    'az-AZ': ('^[0-9A-VXYZÇƏĞİıÖŞÜ]+$', True),
    'bg-BG': ('^[0-9А-Я]+$', True),
    'cs-CZ': ('^[0-9A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]+$', True),
    'da-DK': ('^[0-9A-ZÆØÅ]+$', True),
    'de-DE': ('^[0-9A-ZÄÖÜß]+$', True),
    'el-GR': ('^[0-9Α-ω]+$', True),
    'es-ES': ('^[0-9A-ZÁÉÍÑÓÚÜ]+$', True),
    'fi-FI': ('^[0-9A-ZÅÄÖ]+$', True),
    'fr-FR': ('^[0-9A-ZÀÂÆÇÉÈÊËÏÎÔŒÙÛÜŸ]+$', True),
    'it-IT': ('^[0-9A-ZÀÉÈÌÎÓÒÙ]+$', True),
    'ja-JP': ('^[0-9０-９ぁ-んァ-ヶｦ-ﾟ一-龠ー・。、]+$', True),
    'hu-HU': ('^[0-9A-ZÁÉÍÓÖŐÚÜŰ]+$', True),
    'nb-NO': ('^[0-9A-ZÆØÅ]+$', True),
    'nl-NL': ('^[0-9A-ZÁÉËÏÓÖÜÚ]+$', True),
    'nn-NO': ('^[0-9A-ZÆØÅ]+$', True),
    'pl-PL': ('^[0-9A-ZĄĆĘŚŁŃÓŻŹ]+$', True),
    'pt-PT': ('^[0-9A-ZÃÁÀÂÄÇÉÊËÍÏÕÓÔÖÚÜ]+$', True),
    'ru-RU': ('^[0-9А-ЯЁ]+$', True),
    'kk-KZ': ('^[0-9А-ЯЁ\\u04D8\\u04B0\\u0406\\u04A2\\u0492\\u04AE\\u049A\\u04E8\\u04BA]+$', True),
    'sl-SI': ('^[0-9A-ZČĆĐŠŽ]+$', True),
    'sk-SK': ('^[0-9A-ZÁČĎÉÍŇÓŠŤÚÝŽĹŔĽÄÔ]+$', True),
    'sr-RS@latin': ('^[0-9A-ZČĆŽŠĐ]+$', True),
    'sr-RS': ('^[0-9А-ЯЂЈЉЊЋЏ]+$', True),
    'sv-SE': ('^[0-9A-ZÅÄÖ]+$', True),
    'th-TH': ('^[ก-๙\\s]+$', True),
    'tr-TR': ('^[0-9A-ZÇĞİıÖŞÜ]+$', True),
    'uk-UA': ('^[0-9А-ЩЬЮЯЄIЇҐі]+$', True),
    'ko-KR': ('^[0-9ㄱ-ㅎㅏ-ㅣ가-힣]*$', False),
    'ku-IQ': ('^[٠١٢٣٤٥٦٧٨٩0-9ئابپتجچحخدرڕزژسشعغفڤقکگلڵمنوۆھەیێيطؤثآإأكضصةظذ]+$', True),
    'vi-VN': ('^[0-9A-ZÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴĐÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸ]+$', True),
    'ar': ('^[٠١٢٣٤٥٦٧٨٩0-9ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهوىيًٌٍَُِّْٰ]+$', False),
    'he': ('^[0-9א-ת]+$', False),
    'fa': ("^['0-9آاءأؤئبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهةی۱۲۳۴۵۶۷۸۹۰']+$", True),
    'bn': ("^['ঀঁংঃঅআইঈউঊঋঌএঐওঔকখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহ়ঽািীুূৃৄেৈোৌ্ৎৗড়ঢ়য়ৠৡৢৣ০১২৩৪৫৬৭৮৯ৰৱ৲৳৴৵৶৷৸৹৺৻']+$", False),
    'eo': ('^[0-9ABCĈD-GĜHĤIJĴK-PRSŜTUŬVZ]+$', True),
    'hi-IN': ('^[\\u0900-\\u0963]+[\\u0966-\\u097F]*$', True),
    'si-LK': ('^[0-9\\u0D80-\\u0DFF]+$', False),
    'ta-IN': ('^[0-9\\u0B80-\\u0BFF.]+$', True),
    'te-IN': ('^[0-9\\u0C00-\\u0C7F.]+$', True),
    'kn-IN': ('^[0-9\\u0C80-\\u0CFF.]+$', True),
    'ml-IN': ('^[0-9\\u0D00-\\u0D7F.]+$', True),
    'gu-IN': ('^[0-9\\u0A80-\\u0AFF.]+$', True),
    'pa-IN': ('^[0-9\\u0A00-\\u0A7F.]+$', True),
    'or-IN': ('^[0-9\\u0B00-\\u0B7F.]+$', True),
}

DECIMAL = {
    'en-US': '.',
    'ar': '٫',
}


for _loc in ('AU', 'GB', 'HK', 'IN', 'NZ', 'ZA', 'ZM'):
    ALPHA[f'en-{_loc}'] = ALPHA['en-US']
    ALPHANUMERIC[f'en-{_loc}'] = ALPHANUMERIC['en-US']
    DECIMAL[f'en-{_loc}'] = DECIMAL['en-US']
for _loc in ('AE', 'BH', 'DZ', 'EG', 'IQ', 'JO', 'KW', 'LB', 'LY', 'MA', 'QM', 'QA', 'SA', 'SD', 'SY', 'TN', 'YE'):
    ALPHA[f'ar-{_loc}'] = ALPHA['ar']
    ALPHANUMERIC[f'ar-{_loc}'] = ALPHANUMERIC['ar']
    DECIMAL[f'ar-{_loc}'] = DECIMAL['ar']
for _loc in ('IR', 'AF'):
    ALPHANUMERIC[f'fa-{_loc}'] = ALPHANUMERIC['fa']
    DECIMAL[f'fa-{_loc}'] = DECIMAL['ar']
for _loc in ('BD', 'IN'):
    ALPHA[f'bn-{_loc}'] = ALPHA['bn']
    ALPHANUMERIC[f'bn-{_loc}'] = ALPHANUMERIC['bn']
    DECIMAL[f'bn-{_loc}'] = DECIMAL['en-US']
for _loc in ('ar-EG', 'ar-LB', 'ar-LY'):
    DECIMAL[_loc] = DECIMAL['en-US']
for _loc in ('bg-BG', 'cs-CZ', 'da-DK', 'de-DE', 'el-GR', 'en-ZM', 'eo', 'es-ES', 'fr-CA', 'fr-FR',
             'gu-IN', 'hi-IN', 'hu-HU', 'id-ID', 'it-IT', 'kk-KZ', 'kn-IN', 'ku-IQ', 'ml-IN', 'nb-NO',
             'nl-NL', 'nn-NO', 'or-IN', 'pa-IN', 'pl-PL', 'pt-PT', 'ru-RU', 'si-LK', 'sl-SI', 'sr-RS',
             'sr-RS@latin', 'sv-SE', 'ta-IN', 'te-IN', 'tr-TR', 'uk-UA', 'vi-VN'):
    DECIMAL[_loc] = ','
ALPHA['fr-CA'] = ALPHA['fr-FR']; ALPHANUMERIC['fr-CA'] = ALPHANUMERIC['fr-FR']
ALPHA['pt-BR'] = ALPHA['pt-PT']; ALPHANUMERIC['pt-BR'] = ALPHANUMERIC['pt-PT']; DECIMAL['pt-BR'] = DECIMAL['pt-PT']
ALPHA['pl-Pl'] = ALPHA['pl-PL']; ALPHANUMERIC['pl-Pl'] = ALPHANUMERIC['pl-PL']; DECIMAL['pl-Pl'] = DECIMAL['pl-PL']
ALPHA['fa-AF'] = ALPHA['fa']

IBAN_REGEX = {
    'AD': '^(AD[0-9]{2})\\d{8}[A-Z0-9]{12}$',
    'AE': '^(AE[0-9]{2})\\d{3}\\d{16}$',
    'AL': '^(AL[0-9]{2})\\d{8}[A-Z0-9]{16}$',
    'AT': '^(AT[0-9]{2})\\d{16}$',
    'AZ': '^(AZ[0-9]{2})[A-Z0-9]{4}\\d{20}$',
    'BA': '^(BA[0-9]{2})\\d{16}$',
    'BE': '^(BE[0-9]{2})\\d{12}$',
    'BG': '^(BG[0-9]{2})[A-Z]{4}\\d{6}[A-Z0-9]{8}$',
    'BH': '^(BH[0-9]{2})[A-Z]{4}[A-Z0-9]{14}$',
    'BR': '^(BR[0-9]{2})\\d{23}[A-Z]{1}[A-Z0-9]{1}$',
    'BY': '^(BY[0-9]{2})[A-Z0-9]{4}\\d{20}$',
    'CH': '^(CH[0-9]{2})\\d{5}[A-Z0-9]{12}$',
    'CR': '^(CR[0-9]{2})\\d{18}$',
    'CY': '^(CY[0-9]{2})\\d{8}[A-Z0-9]{16}$',
    'CZ': '^(CZ[0-9]{2})\\d{20}$',
    'DE': '^(DE[0-9]{2})\\d{18}$',
    'DK': '^(DK[0-9]{2})\\d{14}$',
    'DO': '^(DO[0-9]{2})[A-Z]{4}\\d{20}$',
    'DZ': '^(DZ\\d{24})$',
    'EE': '^(EE[0-9]{2})\\d{16}$',
    'EG': '^(EG[0-9]{2})\\d{25}$',
    'ES': '^(ES[0-9]{2})\\d{20}$',
    'FI': '^(FI[0-9]{2})\\d{14}$',
    'FO': '^(FO[0-9]{2})\\d{14}$',
    'FR': '^(FR[0-9]{2})\\d{10}[A-Z0-9]{11}\\d{2}$',
    'GB': '^(GB[0-9]{2})[A-Z]{4}\\d{14}$',
    'GE': '^(GE[0-9]{2})[A-Z0-9]{2}\\d{16}$',
    'GI': '^(GI[0-9]{2})[A-Z]{4}[A-Z0-9]{15}$',
    'GL': '^(GL[0-9]{2})\\d{14}$',
    'GR': '^(GR[0-9]{2})\\d{7}[A-Z0-9]{16}$',
    'GT': '^(GT[0-9]{2})[A-Z0-9]{4}[A-Z0-9]{20}$',
    'HR': '^(HR[0-9]{2})\\d{17}$',
    'HU': '^(HU[0-9]{2})\\d{24}$',
    'IE': '^(IE[0-9]{2})[A-Z]{4}\\d{14}$',
    'IL': '^(IL[0-9]{2})\\d{19}$',
    'IQ': '^(IQ[0-9]{2})[A-Z]{4}\\d{15}$',
    'IR': '^(IR[0-9]{2})\\d{22}$',
    'IS': '^(IS[0-9]{2})\\d{22}$',
    'IT': '^(IT[0-9]{2})[A-Z]{1}\\d{10}[A-Z0-9]{12}$',
    'JO': '^(JO[0-9]{2})[A-Z]{4}\\d{22}$',
    'KW': '^(KW[0-9]{2})[A-Z]{4}[A-Z0-9]{22}$',
    'KZ': '^(KZ[0-9]{2})\\d{3}[A-Z0-9]{13}$',
    'LB': '^(LB[0-9]{2})\\d{4}[A-Z0-9]{20}$',
    'LC': '^(LC[0-9]{2})[A-Z]{4}[A-Z0-9]{24}$',
    'LI': '^(LI[0-9]{2})\\d{5}[A-Z0-9]{12}$',
    'LT': '^(LT[0-9]{2})\\d{16}$',
    'LU': '^(LU[0-9]{2})\\d{3}[A-Z0-9]{13}$',
    'LV': '^(LV[0-9]{2})[A-Z]{4}[A-Z0-9]{13}$',
    'MA': '^(MA[0-9]{26})$',
    'MC': '^(MC[0-9]{2})\\d{10}[A-Z0-9]{11}\\d{2}$',
    'MD': '^(MD[0-9]{2})[A-Z0-9]{20}$',
    'ME': '^(ME[0-9]{2})\\d{18}$',
    'MK': '^(MK[0-9]{2})\\d{3}[A-Z0-9]{10}\\d{2}$',
    'MR': '^(MR[0-9]{2})\\d{23}$',
    'MT': '^(MT[0-9]{2})[A-Z]{4}\\d{5}[A-Z0-9]{18}$',
    'MU': '^(MU[0-9]{2})[A-Z]{4}\\d{19}[A-Z]{3}$',
    'MZ': '^(MZ[0-9]{2})\\d{21}$',
    'NL': '^(NL[0-9]{2})[A-Z]{4}\\d{10}$',
    'NO': '^(NO[0-9]{2})\\d{11}$',
    'PK': '^(PK[0-9]{2})[A-Z0-9]{4}\\d{16}$',
    'PL': '^(PL[0-9]{2})\\d{24}$',
    'PS': '^(PS[0-9]{2})[A-Z]{4}[A-Z0-9]{21}$',
    'PT': '^(PT[0-9]{2})\\d{21}$',
    'QA': '^(QA[0-9]{2})[A-Z]{4}[A-Z0-9]{21}$',
    'RO': '^(RO[0-9]{2})[A-Z]{4}[A-Z0-9]{16}$',
    'RS': '^(RS[0-9]{2})\\d{18}$',
    'SA': '^(SA[0-9]{2})\\d{2}[A-Z0-9]{18}$',
    'SC': '^(SC[0-9]{2})[A-Z]{4}\\d{20}[A-Z]{3}$',
    'SE': '^(SE[0-9]{2})\\d{20}$',
    'SI': '^(SI[0-9]{2})\\d{15}$',
    'SK': '^(SK[0-9]{2})\\d{20}$',
    'SM': '^(SM[0-9]{2})[A-Z]{1}\\d{10}[A-Z0-9]{12}$',
    'SV': '^(SV[0-9]{2})[A-Z0-9]{4}\\d{20}$',
    'TL': '^(TL[0-9]{2})\\d{19}$',
    'TN': '^(TN[0-9]{2})\\d{20}$',
    'TR': '^(TR[0-9]{2})\\d{5}[A-Z0-9]{17}$',
    'UA': '^(UA[0-9]{2})\\d{6}[A-Z0-9]{19}$',
    'VA': '^(VA[0-9]{2})\\d{18}$',
    'VG': '^(VG[0-9]{2})[A-Z]{4}\\d{16}$',
    'XK': '^(XK[0-9]{2})\\d{16}$',
}

ISO_31661_ALPHA2 = frozenset(['AD', 'AE', 'AF', 'AG', 'AI', 'AL', 'AM', 'AO', 'AQ', 'AR', 'AS', 'AT', 'AU', 'AW', 'AX', 'AZ', 'BA', 'BB', 'BD', 'BE', 'BF', 'BG', 'BH', 'BI', 'BJ', 'BL', 'BM', 'BN', 'BO', 'BQ', 'BR', 'BS', 'BT', 'BV', 'BW', 'BY', 'BZ', 'CA', 'CC', 'CD', 'CF', 'CG', 'CH', 'CI', 'CK', 'CL', 'CM', 'CN', 'CO', 'CR', 'CU', 'CV', 'CW', 'CX', 'CY', 'CZ', 'DE', 'DJ', 'DK', 'DM', 'DO', 'DZ', 'EC', 'EE', 'EG', 'EH', 'ER', 'ES', 'ET', 'FI', 'FJ', 'FK', 'FM', 'FO', 'FR', 'GA', 'GB', 'GD', 'GE', 'GF', 'GG', 'GH', 'GI', 'GL', 'GM', 'GN', 'GP', 'GQ', 'GR', 'GS', 'GT', 'GU', 'GW', 'GY', 'HK', 'HM', 'HN', 'HR', 'HT', 'HU', 'ID', 'IE', 'IL', 'IM', 'IN', 'IO', 'IQ', 'IR', 'IS', 'IT', 'JE', 'JM', 'JO', 'JP', 'KE', 'KG', 'KH', 'KI', 'KM', 'KN', 'KP', 'KR', 'KW', 'KY', 'KZ', 'LA', 'LB', 'LC', 'LI', 'LK', 'LR', 'LS', 'LT', 'LU', 'LV', 'LY', 'MA', 'MC', 'MD', 'ME', 'MF', 'MG', 'MH', 'MK', 'ML', 'MM', 'MN', 'MO', 'MP', 'MQ', 'MR', 'MS', 'MT', 'MU', 'MV', 'MW', 'MX', 'MY', 'MZ', 'NA', 'NC', 'NE', 'NF', 'NG', 'NI', 'NL', 'NO', 'NP', 'NR', 'NU', 'NZ', 'OM', 'PA', 'PE', 'PF', 'PG', 'PH', 'PK', 'PL', 'PM', 'PN', 'PR', 'PS', 'PT', 'PW', 'PY', 'QA', 'RE', 'RO', 'RS', 'RU', 'RW', 'SA', 'SB', 'SC', 'SD', 'SE', 'SG', 'SH', 'SI', 'SJ', 'SK', 'SL', 'SM', 'SN', 'SO', 'SR', 'SS', 'ST', 'SV', 'SX', 'SY', 'SZ', 'TC', 'TD', 'TF', 'TG', 'TH', 'TJ', 'TK', 'TL', 'TM', 'TN', 'TO', 'TR', 'TT', 'TV', 'TW', 'TZ', 'UA', 'UG', 'UM', 'US', 'UY', 'UZ', 'VA', 'VC', 'VE', 'VG', 'VI', 'VN', 'VU', 'WF', 'WS', 'YE', 'YT', 'ZA', 'ZM', 'ZW'])

ISO_31661_ALPHA3 = frozenset(['ABW', 'AFG', 'AGO', 'AIA', 'ALA', 'ALB', 'AND', 'ARE', 'ARG', 'ARM', 'ASM', 'ATA', 'ATF', 'ATG', 'AUS', 'AUT', 'AZE', 'BDI', 'BEL', 'BEN', 'BES', 'BFA', 'BGD', 'BGR', 'BHR', 'BHS', 'BIH', 'BLM', 'BLR', 'BLZ', 'BMU', 'BOL', 'BRA', 'BRB', 'BRN', 'BTN', 'BVT', 'BWA', 'CAF', 'CAN', 'CCK', 'CHE', 'CHL', 'CHN', 'CIV', 'CMR', 'COD', 'COG', 'COK', 'COL', 'COM', 'CPV', 'CRI', 'CUB', 'CUW', 'CXR', 'CYM', 'CYP', 'CZE', 'DEU', 'DJI', 'DMA', 'DNK', 'DOM', 'DZA', 'ECU', 'EGY', 'ERI', 'ESH', 'ESP', 'EST', 'ETH', 'FIN', 'FJI', 'FLK', 'FRA', 'FRO', 'FSM', 'GAB', 'GBR', 'GEO', 'GGY', 'GHA', 'GIB', 'GIN', 'GLP', 'GMB', 'GNB', 'GNQ', 'GRC', 'GRD', 'GRL', 'GTM', 'GUF', 'GUM', 'GUY', 'HKG', 'HMD', 'HND', 'HRV', 'HTI', 'HUN', 'IDN', 'IMN', 'IND', 'IOT', 'IRL', 'IRN', 'IRQ', 'ISL', 'ISR', 'ITA', 'JAM', 'JEY', 'JOR', 'JPN', 'KAZ', 'KEN', 'KGZ', 'KHM', 'KIR', 'KNA', 'KOR', 'KWT', 'LAO', 'LBN', 'LBR', 'LBY', 'LCA', 'LIE', 'LKA', 'LSO', 'LTU', 'LUX', 'LVA', 'MAC', 'MAF', 'MAR', 'MCO', 'MDA', 'MDG', 'MDV', 'MEX', 'MHL', 'MKD', 'MLI', 'MLT', 'MMR', 'MNE', 'MNG', 'MNP', 'MOZ', 'MRT', 'MSR', 'MTQ', 'MUS', 'MWI', 'MYS', 'MYT', 'NAM', 'NCL', 'NER', 'NFK', 'NGA', 'NIC', 'NIU', 'NLD', 'NOR', 'NPL', 'NRU', 'NZL', 'OMN', 'PAK', 'PAN', 'PCN', 'PER', 'PHL', 'PLW', 'PNG', 'POL', 'PRI', 'PRK', 'PRT', 'PRY', 'PSE', 'PYF', 'QAT', 'REU', 'ROU', 'RUS', 'RWA', 'SAU', 'SDN', 'SEN', 'SGP', 'SGS', 'SHN', 'SJM', 'SLB', 'SLE', 'SLV', 'SMR', 'SOM', 'SPM', 'SRB', 'SSD', 'STP', 'SUR', 'SVK', 'SVN', 'SWE', 'SWZ', 'SXM', 'SYC', 'SYR', 'TCA', 'TCD', 'TGO', 'THA', 'TJK', 'TKL', 'TKM', 'TLS', 'TON', 'TTO', 'TUN', 'TUR', 'TUV', 'TWN', 'TZA', 'UGA', 'UKR', 'UMI', 'URY', 'USA', 'UZB', 'VAT', 'VCT', 'VEN', 'VGB', 'VIR', 'VNM', 'VUT', 'WLF', 'WSM', 'YEM', 'ZAF', 'ZMB', 'ZWE'])

ISO_31661_NUMERIC = frozenset(['004', '008', '010', '012', '016', '020', '024', '028', '031', '032', '036', '040', '044', '048', '050', '051', '052', '056', '060', '064', '068', '070', '072', '074', '076', '084', '086', '090', '092', '096', '100', '104', '108', '112', '116', '120', '124', '132', '136', '140', '144', '148', '152', '156', '158', '162', '166', '170', '174', '175', '178', '180', '184', '188', '191', '192', '196', '203', '204', '208', '212', '214', '218', '222', '226', '231', '232', '233', '234', '238', '239', '242', '246', '248', '250', '254', '258', '260', '262', '266', '268', '270', '275', '276', '288', '292', '296', '300', '304', '308', '312', '316', '320', '324', '328', '332', '334', '336', '340', '344', '348', '352', '356', '360', '364', '368', '372', '376', '380', '384', '388', '392', '398', '400', '404', '408', '410', '414', '417', '418', '422', '426', '428', '430', '434', '438', '440', '442', '446', '450', '454', '458', '462', '466', '470', '474', '478', '480', '484', '492', '496', '498', '499', '500', '504', '508', '512', '516', '520', '524', '528', '531', '533', '534', '535', '540', '548', '554', '558', '562', '566', '570', '574', '578', '580', '581', '583', '584', '585', '586', '591', '598', '600', '604', '608', '612', '616', '620', '624', '626', '630', '634', '638', '642', '643', '646', '652', '654', '659', '660', '662', '663', '666', '670', '674', '678', '682', '686', '688', '690', '694', '702', '703', '704', '705', '706', '710', '716', '724', '728', '729', '732', '740', '744', '748', '752', '756', '760', '762', '764', '768', '772', '776', '780', '784', '788', '792', '795', '796', '798', '800', '804', '807', '818', '826', '831', '832', '833', '834', '840', '850', '854', '858', '860', '862', '876', '882', '887', '894'])

ISO_4217 = frozenset(['AED', 'AFN', 'ALL', 'AMD', 'ANG', 'AOA', 'ARS', 'AUD', 'AWG', 'AZN', 'BAM', 'BBD', 'BDT', 'BGN', 'BHD', 'BIF', 'BMD', 'BND', 'BOB', 'BOV', 'BRL', 'BSD', 'BTN', 'BWP', 'BYN', 'BZD', 'CAD', 'CDF', 'CHE', 'CHF', 'CHW', 'CLF', 'CLP', 'CNY', 'COP', 'COU', 'CRC', 'CUP', 'CVE', 'CZK', 'DJF', 'DKK', 'DOP', 'DZD', 'EGP', 'ERN', 'ETB', 'EUR', 'FJD', 'FKP', 'GBP', 'GEL', 'GHS', 'GIP', 'GMD', 'GNF', 'GTQ', 'GYD', 'HKD', 'HNL', 'HTG', 'HUF', 'IDR', 'ILS', 'INR', 'IQD', 'IRR', 'ISK', 'JMD', 'JOD', 'JPY', 'KES', 'KGS', 'KHR', 'KMF', 'KPW', 'KRW', 'KWD', 'KYD', 'KZT', 'LAK', 'LBP', 'LKR', 'LRD', 'LSL', 'LYD', 'MAD', 'MDL', 'MGA', 'MKD', 'MMK', 'MNT', 'MOP', 'MRU', 'MUR', 'MVR', 'MWK', 'MXN', 'MXV', 'MYR', 'MZN', 'NAD', 'NGN', 'NIO', 'NOK', 'NPR', 'NZD', 'OMR', 'PAB', 'PEN', 'PGK', 'PHP', 'PKR', 'PLN', 'PYG', 'QAR', 'RON', 'RSD', 'RUB', 'RWF', 'SAR', 'SBD', 'SCR', 'SDG', 'SEK', 'SGD', 'SHP', 'SLE', 'SLL', 'SOS', 'SRD', 'SSP', 'STN', 'SVC', 'SYP', 'SZL', 'THB', 'TJS', 'TMT', 'TND', 'TOP', 'TRY', 'TTD', 'TWD', 'TZS', 'UAH', 'UGX', 'USD', 'USN', 'UYI', 'UYU', 'UYW', 'UZS', 'VED', 'VES', 'VND', 'VUV', 'WST', 'XAF', 'XAG', 'XAU', 'XBA', 'XBB', 'XBC', 'XBD', 'XCD', 'XDR', 'XOF', 'XPD', 'XPF', 'XPT', 'XSU', 'XTS', 'XUA', 'XXX', 'YER', 'ZAR', 'ZMW', 'ZWL'])

ISO_6391 = frozenset(['aa', 'ab', 'ae', 'af', 'ak', 'am', 'an', 'ar', 'as', 'av', 'ay', 'az', 'ba', 'be', 'bg', 'bh', 'bi', 'bm', 'bn', 'bo', 'br', 'bs', 'ca', 'ce', 'ch', 'co', 'cr', 'cs', 'cu', 'cv', 'cy', 'da', 'de', 'dv', 'dz', 'ee', 'el', 'en', 'eo', 'es', 'et', 'eu', 'fa', 'ff', 'fi', 'fj', 'fo', 'fr', 'fy', 'ga', 'gd', 'gl', 'gn', 'gu', 'gv', 'ha', 'he', 'hi', 'ho', 'hr', 'ht', 'hu', 'hy', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'io', 'is', 'it', 'iu', 'ja', 'jv', 'ka', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'kr', 'ks', 'ku', 'kv', 'kw', 'ky', 'la', 'lb', 'lg', 'li', 'ln', 'lo', 'lt', 'lu', 'lv', 'mg', 'mh', 'mi', 'mk', 'ml', 'mn', 'mr', 'ms', 'mt', 'my', 'na', 'nb', 'nd', 'ne', 'ng', 'nl', 'nn', 'no', 'nr', 'nv', 'ny', 'oc', 'oj', 'om', 'or', 'os', 'pa', 'pi', 'pl', 'ps', 'pt', 'qu', 'rm', 'rn', 'ro', 'ru', 'rw', 'sa', 'sc', 'sd', 'se', 'sg', 'si', 'sk', 'sl', 'sm', 'sn', 'so', 'sq', 'sr', 'ss', 'st', 'su', 'sv', 'sw', 'ta', 'te', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tr', 'ts', 'tt', 'tw', 'ty', 'ug', 'uk', 'ur', 'uz', 've', 'vi', 'vo', 'wa', 'wo', 'xh', 'yi', 'yo', 'za', 'zh', 'zu'])

ISO_15924 = frozenset(['Adlm', 'Afak', 'Aghb', 'Ahom', 'Arab', 'Aran', 'Armi', 'Armn', 'Avst', 'Bali', 'Bamu', 'Bass', 'Batk', 'Beng', 'Bhks', 'Blis', 'Bopo', 'Brah', 'Brai', 'Bugi', 'Buhd', 'Cakm', 'Cans', 'Cari', 'Cham', 'Cher', 'Chis', 'Chrs', 'Cirt', 'Copt', 'Cpmn', 'Cprt', 'Cyrl', 'Cyrs', 'Deva', 'Diak', 'Dogr', 'Dsrt', 'Dupl', 'Egyd', 'Egyh', 'Egyp', 'Elba', 'Elym', 'Ethi', 'Gara', 'Geok', 'Geor', 'Glag', 'Gong', 'Gonm', 'Goth', 'Gran', 'Grek', 'Gujr', 'Gukh', 'Guru', 'Hanb', 'Hang', 'Hani', 'Hano', 'Hans', 'Hant', 'Hatr', 'Hebr', 'Hira', 'Hluw', 'Hmng', 'Hmnp', 'Hrkt', 'Hung', 'Inds', 'Ital', 'Jamo', 'Java', 'Jpan', 'Jurc', 'Kali', 'Kana', 'Kawi', 'Khar', 'Khmr', 'Khoj', 'Kitl', 'Kits', 'Knda', 'Kore', 'Kpel', 'Krai', 'Kthi', 'Lana', 'Laoo', 'Latf', 'Latg', 'Latn', 'Leke', 'Lepc', 'Limb', 'Lina', 'Linb', 'Lisu', 'Loma', 'Lyci', 'Lydi', 'Mahj', 'Maka', 'Mand', 'Mani', 'Marc', 'Maya', 'Medf', 'Mend', 'Merc', 'Mero', 'Mlym', 'Modi', 'Mong', 'Moon', 'Mroo', 'Mtei', 'Mult', 'Mymr', 'Nagm', 'Nand', 'Narb', 'Nbat', 'Newa', 'Nkdb', 'Nkgb', 'Nkoo', 'Nshu', 'Ogam', 'Olck', 'Onao', 'Orkh', 'Orya', 'Osge', 'Osma', 'Ougr', 'Palm', 'Pauc', 'Pcun', 'Pelm', 'Perm', 'Phag', 'Phli', 'Phlp', 'Phlv', 'Phnx', 'Piqd', 'Plrd', 'Prti', 'Psin', 'Qaaa', 'Qaab', 'Qaac', 'Qaad', 'Qaae', 'Qaaf', 'Qaag', 'Qaah', 'Qaai', 'Qaaj', 'Qaak', 'Qaal', 'Qaam', 'Qaan', 'Qaao', 'Qaap', 'Qaaq', 'Qaar', 'Qaas', 'Qaat', 'Qaau', 'Qaav', 'Qaaw', 'Qaax', 'Qaay', 'Qaaz', 'Qaba', 'Qabb', 'Qabc', 'Qabd', 'Qabe', 'Qabf', 'Qabg', 'Qabh', 'Qabi', 'Qabj', 'Qabk', 'Qabl', 'Qabm', 'Qabn', 'Qabo', 'Qabp', 'Qabq', 'Qabr', 'Qabs', 'Qabt', 'Qabu', 'Qabv', 'Qabw', 'Qabx', 'Ranj', 'Rjng', 'Rohg', 'Roro', 'Runr', 'Samr', 'Sara', 'Sarb', 'Saur', 'Sgnw', 'Shaw', 'Shrd', 'Shui', 'Sidd', 'Sidt', 'Sind', 'Sinh', 'Sogd', 'Sogo', 'Sora', 'Soyo', 'Sund', 'Sunu', 'Sylo', 'Syrc', 'Syre', 'Syrj', 'Syrn', 'Tagb', 'Takr', 'Tale', 'Talu', 'Taml', 'Tang', 'Tavt', 'Tayo', 'Telu', 'Teng', 'Tfng', 'Tglg', 'Thaa', 'Thai', 'Tibt', 'Tirh', 'Tnsa', 'Todr', 'Tols', 'Toto', 'Tutg', 'Ugar', 'Vaii', 'Visp', 'Vith', 'Wara', 'Wcho', 'Wole', 'Xpeo', 'Xsux', 'Yezi', 'Yiii', 'Zanb', 'Zinh', 'Zmth', 'Zsye', 'Zsym', 'Zxxx', 'Zyyy', 'Zzzz'])

