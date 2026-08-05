import { PAGE_COUNT_RANGE, TONE_LABEL } from '@/features/projects/types'
import { themeList } from '@/render/design'

export const TONE_OPTIONS = Object.entries(TONE_LABEL).map(([value, label]) => ({ value, label }))

export const THEME_OPTIONS = themeList.map((theme) => ({ value: theme.id, label: theme.name }))

export const PAGE_COUNT_OPTIONS = Array.from(
  { length: PAGE_COUNT_RANGE.max - PAGE_COUNT_RANGE.min + 1 },
  (_, index) => {
    const count = PAGE_COUNT_RANGE.min + index
    return { value: count, label: `${count} 页` }
  },
)
