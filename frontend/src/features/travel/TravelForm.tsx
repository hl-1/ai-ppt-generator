import { useMutation } from '@tanstack/react-query'
import { Check, Loader2, Sparkles } from 'lucide-react'
import { request } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/Button'
import { errorMessage } from '@/lib/errors'

export type TravelConditions = components['schemas']['TravelConditions-Input']
type ExtractResult = components['schemas']['TravelExtractResult']

export const EMPTY_TRAVEL: TravelConditions = {
  origin: '', destination: '', departure_date: null, return_date: null,
  adults: 1, children: 0, seniors: 0, child_ages: [], senior_ages: [],
  budget: null, budget_mode: 'total', transport: 'public', lodging_area: '',
  interests: [], pace: 'balanced', draft_days: 3, confirmed: false,
  departure_window: {}, return_window: {},
  must_visit: [], lodging_preferences: '', room_count: null, meal_budget_per_day: 100, contingency: 300,
  video_preferences: { enabled: true, platforms: ['douyin', 'bilibili'], min_likes: 10000, min_favorites: 1000, lookback_days: 180 },
}

export function TravelForm({ value, onChange, text = '', disabled = false }: {
  value: TravelConditions
  onChange: (conditions: TravelConditions) => void
  text?: string
  disabled?: boolean
}) {
  const extract = useMutation({
    mutationFn: () => request<ExtractResult>('/travel/extract', {
      method: 'POST', body: JSON.stringify({ text }),
    }),
    onSuccess: (result) => onChange({ ...EMPTY_TRAVEL, ...result.conditions, video_preferences: value.video_preferences ?? EMPTY_TRAVEL.video_preferences, confirmed: false }),
  })
  const change = (patch: Partial<TravelConditions>) => {
    if (Object.entries(patch).every(([key, next]) => JSON.stringify(value[key as keyof TravelConditions]) === JSON.stringify(next))) return
    onChange({ ...value, ...patch, confirmed: false })
  }
  const field = 'mt-1.5 w-full min-w-0 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink disabled:opacity-50'
  const video = { ...EMPTY_TRAVEL.video_preferences, ...value.video_preferences }
  const changeVideo = (patch: Partial<NonNullable<TravelConditions['video_preferences']>>) => change({ video_preferences: { ...video, ...patch } })
  return (
    <section className="mt-5 border-t border-line pt-5" aria-label="旅行条件">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">旅行条件</h2>
        {text && <Button variant="ghost" size="sm" disabled={disabled || extract.isPending} onClick={() => extract.mutate()}>
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
        {(['departure_date', 'return_date'] as const).map((key) => <label key={key} className="min-w-0 text-sm text-ink-soft">
          {key === 'departure_date' ? '出发日期' : '返程日期'}
          <input aria-label={key === 'departure_date' ? '出发日期' : '返程日期'} type="date" className={field}
            value={value[key] ?? ''} min={key === 'return_date' ? value.departure_date ?? undefined : undefined}
            onChange={(event) => change({ [key]: event.target.value || null })} />
        </label>)}
        {(['departure_window', 'return_window'] as const).map((key) => <div key={key} className="min-w-0">
          <p className="text-sm text-ink-soft">{key === 'departure_window' ? '可接受出发时段' : '可接受返程时段'}</p>
          <div className="grid grid-cols-2 gap-2">
            {(['earliest', 'latest'] as const).map((edge) => <input key={edge} type="time" className={field}
              aria-label={`${key === 'departure_window' ? '出发' : '返程'}${edge === 'earliest' ? '最早' : '最晚'}时间`}
              value={value[key]?.[edge]?.slice(0, 5) ?? ''}
              onChange={(event) => change({ [key]: { ...value[key], [edge]: event.target.value || null } })} />)}
          </div>
        </div>)}
        <div className="grid grid-cols-3 gap-2 sm:col-span-2">
          {(['adults', 'children', 'seniors'] as const).map((key) => <label key={key} className="text-sm text-ink-soft">
            {{ adults: '成人', children: '儿童', seniors: '老人' }[key]}
            <input type="number" min={0} max={key === 'adults' ? 50 : 20} className={field} aria-label={{ adults: '成人数量', children: '儿童数量', seniors: '老人数量' }[key]}
              value={value[key] ?? 0} onChange={(event) => change({ [key]: Number(event.target.value), ...(key === 'children' ? { child_ages: [] } : key === 'seniors' ? { senior_ages: [] } : {}) })} />
          </label>)}
        </div>
        {(value.children ?? 0) > 0 && <label className="text-sm text-ink-soft">儿童年龄（逗号分隔）
          <input className={field} aria-label="儿童年龄" defaultValue={value.child_ages?.join(', ')} key={`children-${value.children}-${extract.submittedAt}`}
            onBlur={(event) => change({ child_ages: event.target.value.split(/[,，\s]+/).filter(Boolean).map(Number) })} />
        </label>}
        {(value.seniors ?? 0) > 0 && <label className="text-sm text-ink-soft">老人年龄（逗号分隔）
          <input className={field} aria-label="老人年龄" defaultValue={value.senior_ages?.join(', ')} key={`seniors-${value.seniors}-${extract.submittedAt}`}
            onBlur={(event) => change({ senior_ages: event.target.value.split(/[,，\s]+/).filter(Boolean).map(Number) })} />
        </label>}
        <label className="text-sm text-ink-soft">预算（元）
          <input type="number" min={1} max={10000000} className={field} aria-label="旅行预算" value={value.budget ?? ''}
            onChange={(event) => change({ budget: event.target.value ? Number(event.target.value) : null })} />
        </label>
        <label className="text-sm text-ink-soft">预算口径
          <select className={field} aria-label="预算口径" value={value.budget_mode} onChange={(event) => change({ budget_mode: event.target.value as TravelConditions['budget_mode'] })}>
            <option value="total">总预算</option><option value="per_person">人均预算</option>
          </select>
        </label>
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
        <label className="text-sm text-ink-soft">住宿区域
          <input className={field} aria-label="住宿区域" maxLength={120} value={value.lodging_area ?? ''} onChange={(event) => change({ lodging_area: event.target.value })} />
        </label>
        <label className="text-sm text-ink-soft">住宿房型与设施偏好
          <input className={field} aria-label="住宿偏好" value={value.lodging_preferences ?? ''} maxLength={300}
            onChange={(event) => change({ lodging_preferences: event.target.value })} />
        </label>
        <label className="text-sm text-ink-soft">房间数
          <input type="number" min={1} max={50} className={field} aria-label="房间数" placeholder="按每间 2 人估算" value={value.room_count ?? ''}
            onChange={(event) => change({ room_count: event.target.value ? Number(event.target.value) : null })} />
        </label>
        <label className="text-sm text-ink-soft">每人每日餐饮预算（元）
          <input type="number" min={1} max={10000} className={field} aria-label="每日餐饮预算" value={value.meal_budget_per_day ?? 100}
            onChange={(event) => change({ meal_budget_per_day: Number(event.target.value) })} />
        </label>
        <label className="text-sm text-ink-soft">团队备用金（元）
          <input type="number" min={0} max={1000000} className={field} aria-label="团队备用金" value={value.contingency ?? 300}
            onChange={(event) => change({ contingency: Number(event.target.value) })} />
        </label>
        <label className="text-sm text-ink-soft sm:col-span-2">必去地点（逗号分隔，最多 8 个）
          <input className={field} aria-label="必去地点" defaultValue={value.must_visit?.join('，') ?? ''} key={`must-visit-${extract.submittedAt}`}
            onBlur={(event) => change({ must_visit: [...new Set(event.target.value.split(/[,，、]/).map((name) => name.trim()).filter(Boolean))] })} />
        </label>
        <label className="text-sm text-ink-soft">日期未定时的草案天数
          <input type="number" min={1} max={14} className={field} aria-label="草案天数" value={value.draft_days} onChange={(event) => change({ draft_days: Number(event.target.value) })} />
        </label>
        <label className="text-sm text-ink-soft sm:col-span-2">感兴趣的景点（逗号分隔）
          <input className={field} aria-label="感兴趣的景点" defaultValue={value.interests?.join(', ')} key={`interests-${extract.submittedAt}`}
            onBlur={(event) => change({ interests: event.target.value.split(/[,，、]+/).map((name) => name.trim()).filter(Boolean) })} />
        </label>
        <div className="border-t border-line pt-4 sm:col-span-2">
          <label className="flex items-center gap-2 text-sm text-ink-soft">
            <input type="checkbox" className="size-4 accent-accent" aria-label="查询视频攻略"
              checked={video.enabled ?? true} onChange={(event) => changeVideo({ enabled: event.target.checked })} />
            视频攻略
          </label>
          {video.enabled && <div className="mt-3 grid min-w-0 gap-3 sm:grid-cols-2">
            <div className="flex flex-wrap gap-4 sm:col-span-2">
              {(['douyin', 'bilibili'] as const).map((platform) => <label key={platform} className="flex items-center gap-2 text-sm text-ink-soft">
                <input type="checkbox" className="size-4 accent-accent" checked={video.platforms?.includes(platform) ?? false}
                  disabled={video.platforms?.length === 1 && video.platforms.includes(platform)}
                  aria-label={platform === 'douyin' ? '查询抖音' : '查询 B 站'}
                  onChange={(event) => {
                    const platforms = event.target.checked ? [...(video.platforms ?? []), platform] : video.platforms?.filter((item) => item !== platform)
                    if (platforms?.length) changeVideo({ platforms })
                  }} />
                {platform === 'douyin' ? '抖音' : 'B 站'}
              </label>)}
            </div>
            <label className="min-w-0 text-sm text-ink-soft">点赞下限（或收藏达标）
              <input type="number" min={1} max={100000000} className={field} aria-label="视频点赞下限" value={video.min_likes}
                onChange={(event) => changeVideo({ min_likes: Number(event.target.value) })} />
            </label>
            <label className="min-w-0 text-sm text-ink-soft">收藏下限（或点赞达标）
              <input type="number" min={1} max={100000000} className={field} aria-label="视频收藏下限" value={video.min_favorites}
                onChange={(event) => changeVideo({ min_favorites: Number(event.target.value) })} />
            </label>
            <label className="min-w-0 text-sm text-ink-soft">发布于最近（天）
              <input type="number" min={1} max={1095} className={field} aria-label="视频发布时间范围" value={video.lookback_days}
                onChange={(event) => changeVideo({ lookback_days: Number(event.target.value) })} />
            </label>
          </div>}
        </div>
        <label className="flex items-start gap-2 text-sm text-ink-soft sm:col-span-2">
          <input type="checkbox" className="mt-0.5 size-4 accent-accent" checked={value.confirmed ?? false}
            aria-label="确认旅行条件" onChange={(event) => onChange({ ...value, confirmed: event.target.checked })} />
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
