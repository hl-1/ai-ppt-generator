import { useMutation } from '@tanstack/react-query'
import { Check, ChevronDown, Loader2, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { request } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/Button'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

export type TravelConditions = components['schemas']['TravelConditions-Input']
type ExtractResult = components['schemas']['TravelExtractResult']

export const EMPTY_TRAVEL: TravelConditions = {
  origin: '', destination: '', departure_date: null, return_date: null,
  adults: 1, children: 0, seniors: 0, child_ages: [], senior_ages: [],
  budget: null, budget_mode: 'total', transport: 'public', lodging_area: '',
  interests: [], pace: 'balanced', draft_days: 3, confirmed: false,
  departure_window: {}, return_window: {},
  must_visit: [], lodging_preferences: '', room_count: null, meal_budget_per_day: 100, contingency: 300,
  video_preferences: { enabled: true, platforms: ['douyin', 'bilibili'], min_likes: 1000, min_favorites: 1000, lookback_days: 180 },
}

function totalBudget(conditions: TravelConditions) {
  const people = (conditions.adults ?? 1) + (conditions.children ?? 0) + (conditions.seniors ?? 0)
  return conditions.budget == null ? null : Number(conditions.budget) * (conditions.budget_mode === 'per_person' ? people : 1)
}

export function TravelForm({ value, onChange, text = '', disabled = false, showCostSettings = false }: {
  value: TravelConditions
  onChange: (conditions: TravelConditions) => void
  text?: string
  disabled?: boolean
  showCostSettings?: boolean
}) {
  const [dateMode, setDateMode] = useState<'dates' | 'days'>(value.departure_date || value.return_date ? 'dates' : 'days')
  const [showChildren, setShowChildren] = useState((value.children ?? 0) > 0)
  const [showSeniors, setShowSeniors] = useState((value.seniors ?? 0) > 0)
  const extract = useMutation({
    mutationFn: () => request<ExtractResult>('/travel/extract', {
      method: 'POST', body: JSON.stringify({ text }),
    }),
    onSuccess: (result) => {
      const conditions = { ...EMPTY_TRAVEL, ...result.conditions }
      setDateMode(conditions.departure_date || conditions.return_date ? 'dates' : 'days')
      setShowChildren((conditions.children ?? 0) > 0)
      setShowSeniors((conditions.seniors ?? 0) > 0)
      onChange({ ...conditions, budget: totalBudget(conditions), budget_mode: 'total', video_preferences: value.video_preferences ?? EMPTY_TRAVEL.video_preferences, confirmed: false })
    },
  })
  const change = (patch: Partial<TravelConditions>) => {
    if (Object.entries(patch).every(([key, next]) => JSON.stringify(value[key as keyof TravelConditions]) === JSON.stringify(next))) return
    // Normalize legacy per-person budgets before changing the party size.
    onChange({ ...value, budget: totalBudget(value), budget_mode: 'total', ...patch, confirmed: false })
  }
  const adults = value.adults ?? 1
  const extractedAt = extract.isSuccess ? extract.submittedAt : 0
  const children = value.children ?? 0
  const seniors = value.seniors ?? 0
  const people = adults + children + seniors
  const places = [...new Set([...(value.must_visit ?? []), ...(value.interests ?? [])])]
  const optionalPlaces = places.filter((name) => !value.must_visit?.includes(name))
  const placesInvalid = optionalPlaces.length > 12 || (value.must_visit?.length ?? 0) > 8
  const budgetInvalid = (totalBudget(value) ?? 0) > 10000000
  const datesIncomplete = dateMode === 'dates' && (!value.departure_date || !value.return_date)
  const field = 'mt-1.5 w-full min-w-0 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink disabled:opacity-50'
  const video = { ...EMPTY_TRAVEL.video_preferences, ...value.video_preferences }
  const lodgingPreference = [value.lodging_area ? `区域：${value.lodging_area}` : '', value.lodging_preferences].filter(Boolean).join('；')
  const changeCompanions = (key: 'children' | 'seniors', count: number) => {
    const next = Math.min(20, Math.max(0, Math.trunc(count)))
    const other = key === 'children' ? seniors : children
    change({
      [key]: next,
      adults: Math.min(50, Math.max(1 - next - other, people - next - other, 0)),
      ...(key === 'children' ? { child_ages: value.child_ages?.slice(0, next) ?? [] } : { senior_ages: value.senior_ages?.slice(0, next) ?? [] }),
    })
  }
  return (
    <section className="mt-5 border-t border-line pt-5" aria-label="旅行条件">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">旅行条件</h2>
        {text && <Button type="button" variant="ghost" size="sm" disabled={disabled || extract.isPending} onClick={() => extract.mutate()}>
          {extract.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          提取条件
        </Button>}
      </div>
      <fieldset disabled={disabled || extract.isPending} className="grid min-w-0 gap-4 sm:grid-cols-2">
        {(['origin', 'destination'] as const).map((key) => <label key={key} className="min-w-0 text-sm text-ink-soft">
          {key === 'origin' ? '出发城市' : '目的地'}
          <input aria-label={key === 'origin' ? '出发城市' : '目的地'} className={field} value={value[key] ?? ''} maxLength={80}
            onChange={(event) => change({ [key]: event.target.value })} />
        </label>)}
        <div className="min-w-0 sm:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-ink-soft">出行时间</p>
            <div role="group" aria-label="出行时间方式" className="inline-flex h-8 rounded-lg border border-line bg-surface-soft p-0.5">
              {(['dates', 'days'] as const).map((mode) => <button key={mode} type="button" aria-pressed={dateMode === mode}
                className={cn('min-w-20 rounded-md px-3 text-xs transition-colors', dateMode === mode ? 'bg-surface font-medium text-ink shadow-sm' : 'text-ink-muted')}
                onClick={() => {
                  setDateMode(mode)
                  change(mode === 'days' ? { departure_date: null, return_date: null, confirmed: false } : { confirmed: false })
                }}>
                {mode === 'dates' ? '日期已定' : '日期未定'}
              </button>)}
            </div>
          </div>
          {dateMode === 'dates' ? <div className="mt-2 grid min-w-0 gap-3 sm:grid-cols-2">
            {(['departure_date', 'return_date'] as const).map((key) => <label key={key} className="min-w-0 text-sm text-ink-soft">
              {key === 'departure_date' ? '出发日期' : '返程日期'}
              <input aria-label={key === 'departure_date' ? '出发日期' : '返程日期'} type="date" className={field}
                value={value[key] ?? ''} min={key === 'return_date' ? value.departure_date ?? undefined : undefined}
                onChange={(event) => change({ [key]: event.target.value || null })} />
            </label>)}
          </div> : <label className="mt-2 block text-sm text-ink-soft">旅行天数
            <input type="number" min={1} max={14} className={field} aria-label="草案天数" value={value.draft_days}
              onChange={(event) => change({ draft_days: Number(event.target.value) })} />
          </label>}
        </div>
        <div className="min-w-0">
          <label className="text-sm text-ink-soft">出行人数
            <input type="number" min={Math.max(1, children + seniors)} max={50 + children + seniors} className={field} aria-label="出行人数" value={people}
              onChange={(event) => {
                if (Number.isFinite(event.target.valueAsNumber)) change({ adults: Math.min(50, Math.max(1 - children - seniors, Math.trunc(event.target.valueAsNumber) - children - seniors, 0)) })
              }} />
          </label>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-xs text-ink-soft">
            {(['children', 'seniors'] as const).map((key) => <label key={key} className="flex items-center gap-1.5">
              <input type="checkbox" className="size-3.5 accent-accent" aria-label={key === 'children' ? '有儿童同行' : '有老人同行'}
                checked={key === 'children' ? showChildren || children > 0 : showSeniors || seniors > 0}
                onChange={(event) => {
                  if (key === 'children') setShowChildren(event.target.checked)
                  else setShowSeniors(event.target.checked)
                  if (!event.target.checked) changeCompanions(key, 0)
                }} />
              {key === 'children' ? '有儿童' : '有老人'}
            </label>)}
          </div>
        </div>
        <label className="min-w-0 text-sm text-ink-soft">全程总预算（元，选填）
          <input type="number" min={1} max={10000000} className={field} aria-label="旅行预算" value={totalBudget(value) ?? ''}
            aria-invalid={budgetInvalid || undefined} onChange={(event) => change({ budget: event.target.value ? Number(event.target.value) : null })} />
          {budgetInvalid && <span role="alert" className="mt-2 block text-xs text-negative">全程总预算最多 1000 万元。</span>}
        </label>
        {(showChildren || children > 0 || showSeniors || seniors > 0) && <div className="grid min-w-0 gap-3 border-l-2 border-line pl-3 sm:col-span-2 sm:grid-cols-2">
          <p className="text-xs text-ink-muted sm:col-span-2">成人 {adults} 人 · 共 {people} 人</p>
          {(['children', 'seniors'] as const).map((key) => ((key === 'children' ? showChildren || children > 0 : showSeniors || seniors > 0) && <div key={key} className="grid min-w-0 gap-3">
            <label className="text-sm text-ink-soft">{key === 'children' ? '儿童人数' : '老人人数'}
              <input type="number" min={0} max={20} className={field} aria-label={key === 'children' ? '儿童数量' : '老人数量'} value={key === 'children' ? children : seniors}
                onChange={(event) => { if (Number.isFinite(event.target.valueAsNumber)) changeCompanions(key, event.target.valueAsNumber) }} />
            </label>
            {(key === 'children' ? children : seniors) > 0 && <label className="text-sm text-ink-soft">{key === 'children' ? '儿童年龄（选填）' : '老人年龄（选填）'}
              <input className={field} aria-label={key === 'children' ? '儿童年龄' : '老人年龄'} placeholder={key === 'children' ? '如：6，10' : '如：65，70'}
                defaultValue={(key === 'children' ? value.child_ages : value.senior_ages)?.join('，')}
                key={`${key}-${key === 'children' ? children : seniors}-${extractedAt}`}
                onBlur={(event) => change({ [key === 'children' ? 'child_ages' : 'senior_ages']: event.target.value.split(/[,，\s]+/).filter(Boolean).map(Number) })} />
            </label>}
          </div>))}
        </div>}
        <div className="min-w-0 sm:col-span-2">
          <label className="text-sm text-ink-soft">想去的地方（选填）
            <input className={field} aria-label="想去的地方" placeholder="如：故宫，天坛，颐和园" maxLength={2000}
              aria-invalid={placesInvalid || undefined} defaultValue={places.join('，')} key={`places-${extractedAt}`}
              onBlur={(event) => {
                const names = [...new Set(event.target.value.split(/[,，、]/).map((name) => name.trim()).filter(Boolean))]
                const mustVisit = (value.must_visit ?? []).filter((name) => names.includes(name))
                change({ must_visit: mustVisit, interests: names.filter((name) => !mustVisit.includes(name)) })
              }} />
          </label>
          {places.length > 0 && <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
            {places.map((name) => <label key={name} className="flex min-w-0 items-start gap-1.5 text-xs text-ink-soft">
              <input type="checkbox" className="mt-0.5 size-3.5 shrink-0 accent-accent" aria-label={`必去：${name}`} checked={value.must_visit?.includes(name) ?? false}
                disabled={!value.must_visit?.includes(name) && (value.must_visit?.length ?? 0) >= 8}
                onChange={(event) => {
                  const mustVisit = event.target.checked ? [...(value.must_visit ?? []), name] : (value.must_visit ?? []).filter((item) => item !== name)
                  change({ must_visit: mustVisit, interests: places.filter((item) => !mustVisit.includes(item)) })
                }} />
              <span className="break-all">必去：{name}</span>
            </label>)}
          </div>}
          {placesInvalid && <p role="alert" className="mt-2 text-xs text-negative">最多选择 8 个必去地点和 12 个其他地点。</p>}
        </div>
        <details className="group min-w-0 border-t border-line pt-3 sm:col-span-2">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm text-ink-soft [&::-webkit-details-marker]:hidden">
            更多偏好<ChevronDown className="size-4 shrink-0 transition-transform group-open:rotate-180" />
          </summary>
          <div className="mt-4 grid min-w-0 gap-4 sm:grid-cols-2">
            <label className="text-sm text-ink-soft">交通方式
              <select className={field} aria-label="交通方式" value={value.transport} onChange={(event) => change({ transport: event.target.value as TravelConditions['transport'] })}>
                <option value="public">公共交通</option><option value="driving">自驾</option><option value="walking">步行</option>
                <option value="train">火车 / 市内公共交通</option><option value="flight">飞机 / 市内公共交通</option>
              </select>
            </label>
            <label className="text-sm text-ink-soft">游览强度
              <select className={field} aria-label="游览强度" value={value.pace} onChange={(event) => change({ pace: event.target.value as TravelConditions['pace'] })}>
                <option value="relaxed">轻松</option><option value="balanced">适中</option><option value="intensive">紧凑</option>
              </select>
            </label>
            {(['departure_window', 'return_window'] as const).map((key) => <div key={key} className="min-w-0">
              <p className="text-sm text-ink-soft">{key === 'departure_window' ? '可接受出发时段（选填）' : '可接受返程时段（选填）'}</p>
              <div className="grid grid-cols-2 gap-2">
                {(['earliest', 'latest'] as const).map((edge) => <input key={edge} type="time" className={field}
                  aria-label={`${key === 'departure_window' ? '出发' : '返程'}${edge === 'earliest' ? '最早' : '最晚'}时间`}
                  value={value[key]?.[edge]?.slice(0, 5) ?? ''}
                  onChange={(event) => change({ [key]: { ...value[key], [edge]: event.target.value || null } })} />)}
              </div>
            </div>)}
            <label className="text-sm text-ink-soft sm:col-span-2">住宿偏好（选填）
              <input className={field} aria-label="住宿偏好" value={lodgingPreference} maxLength={300}
                onChange={(event) => change({ lodging_area: '', lodging_preferences: event.target.value })} />
            </label>
            <label className="text-sm text-ink-soft">房间数（选填）
              <input type="number" min={1} max={50} className={field} aria-label="房间数" placeholder="按每间 2 人估算" value={value.room_count ?? ''}
                onChange={(event) => change({ room_count: event.target.value ? Number(event.target.value) : null })} />
            </label>
            <label className="flex items-center gap-2 text-sm text-ink-soft">
              <input type="checkbox" className="size-4 accent-accent" aria-label="查询视频攻略" checked={video.enabled ?? true}
                onChange={(event) => change({ video_preferences: { ...video, enabled: event.target.checked } })} />
              视频攻略
            </label>
          </div>
        </details>
        {showCostSettings && <details className="group min-w-0 border-t border-line pt-3 sm:col-span-2">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm text-ink-soft [&::-webkit-details-marker]:hidden">
            预算估算<ChevronDown className="size-4 shrink-0 transition-transform group-open:rotate-180" />
          </summary>
          <div className="mt-4 grid min-w-0 gap-4 sm:grid-cols-2">
            <label className="text-sm text-ink-soft">每人每日餐饮预算（元）
              <input type="number" min={1} max={10000} className={field} aria-label="每日餐饮预算" value={value.meal_budget_per_day ?? 100}
                onChange={(event) => change({ meal_budget_per_day: Number(event.target.value) })} />
            </label>
            <label className="text-sm text-ink-soft">团队备用金（元）
              <input type="number" min={0} max={1000000} className={field} aria-label="团队备用金" value={value.contingency ?? 300}
                onChange={(event) => change({ contingency: Number(event.target.value) })} />
            </label>
          </div>
        </details>}
        <label className="flex items-start gap-2 text-sm text-ink-soft sm:col-span-2">
          <input type="checkbox" className="mt-0.5 size-4 accent-accent" checked={value.confirmed ?? false} disabled={placesInvalid || budgetInvalid || datesIncomplete}
            aria-label="确认旅行条件" onChange={(event) => onChange({ ...value, budget: totalBudget(value), budget_mode: 'total', confirmed: event.target.checked })} />
          <span className="flex flex-wrap items-center gap-1">确认旅行条件{!value.departure_date || !value.return_date ? '，日期未定，生成建议草案' : ''}
            {value.confirmed && <Check className="size-4 text-accent" />}
          </span>
        </label>
      </fieldset>
      {extract.isError && <p role="alert" className="mt-3 text-sm text-negative">{errorMessage(extract.error)}</p>}
      {!value.departure_date && extract.data?.warnings.map((warning) => <p key={warning} className="mt-2 text-sm text-warning">{warning}</p>)}
    </section>
  )
}
