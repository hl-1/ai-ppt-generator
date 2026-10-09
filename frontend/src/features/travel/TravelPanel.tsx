import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, RefreshCw, Settings2 } from 'lucide-react'
import { useState } from 'react'
import { request } from '@/api/client'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/Button'
import { useUpdateProject } from '@/features/projects/api'
import type { ProjectDetail } from '@/features/projects/types'
import { EMPTY_TRAVEL, TravelForm, type TravelConditions } from '@/features/travel/TravelForm'
import { errorMessage } from '@/lib/errors'

type Research = components['schemas']['TravelResearchPublic']
const priceLabels = { official_rule: '官方规则价格', supplier_quote: '供应商参考报价', estimate: '估算', pending: '待查询' }
const serviceLabels: Record<string, string> = { amap: '地图与路线', qweather: '天气与空气质量', firecrawl: '联网检索', video: '视频攻略' }
const statusLabels = { ready: '已查询', partial: '部分完成', failed: '失败', not_configured: '未配置', pending: '待查询' }
const money = (value: string | number | null | undefined) => value == null ? '待查询' : `¥${Number(value).toFixed(2)}`
const videoStatusLabels: Record<string, string> = {
  candidate: '待筛选', selected: '正在读取', ready: '已读取', rejected: '未入选', unavailable: '读取未完成',
  popularity_unknown: '热度未知', below_popularity_threshold: '热度未达门槛', publication_unknown: '发布时间未知',
  outside_date_range: '超出发布时间范围', video_too_long: '视频时长超限', irrelevant_video: '内容不匹配',
  selection_limit: '已选取其他候选', access_restricted: '访问受限', advice_extraction_failed: '建议整理未完成',
  no_relevant_advice: '未提取到相关建议',
  content_partial: '已读取部分内容',
  duration_unknown: '视频时长未知',
}
const adviceLabels = { lodging: '住宿', restaurant: '餐饮', pitfall: '避坑', checkin: '打卡', route: '游览' }

function travelServiceMessage(code: string | null | undefined) {
  if (code?.includes('timeout')) return '查询超时。'
  if (code === 'not_configured') return '服务尚未配置。'
  if (code === 'http_401' || code === 'http_403' || code === 'provider_rejected') return '服务访问被拒绝，请检查凭证与权限。'
  if (code === 'http_429') return '请求受限或额度不足，请稍后刷新。'
  return '服务查询未全部完成。'
}

export function TravelResultStatus({ projectId, missingImages }: { projectId: string; missingImages: number }) {
  const query = useQuery({
    queryKey: ['travel', projectId], queryFn: () => request<Research | null>(`/projects/${projectId}/travel/research`),
    refetchInterval: (result) => ['queued', 'researching'].includes(result.state.data?.status ?? '') ? 1500 : false,
  })
  const research = query.data
  if (query.isError) return <p role="alert" className="border-b border-line px-5 py-2 text-xs text-warning">旅行资料状态未能读取：{errorMessage(query.error)}</p>
  if (!research) return null
  const pending = research.data.plan?.unresolved_items.length ?? 0
  const running = research.status === 'queued' || research.status === 'researching'
  return <p role="status" className="border-b border-line px-5 py-2 text-xs text-warning">
    旅行资料 v{research.version} · {research.stale ? '资料已失效，请重新查询并生成' : running ? '资料查询中' : research.status === 'failed' ? '资料查询失败' : pending ? `${pending} 项资料待确认` : research.status === 'partial' ? '资料查询部分完成，仍有信息待确认' : '资料查询完成'}
    {missingImages > 0 ? ` · ${missingImages} 张实景照片或地图未取得` : ''}
  </p>
}

export function TravelPanel({ project, locked = false }: { project: ProjectDetail; locked?: boolean }) {
  const client = useQueryClient()
  const key = ['travel', project.id]
  const query = useQuery({
    queryKey: key,
    queryFn: () => request<Research | null>(`/projects/${project.id}/travel/research`),
    refetchInterval: (result) => ['queued', 'researching'].includes(result.state.data?.status ?? '') ? 1500 : false,
  })
  const refresh = useMutation({
    mutationFn: () => request(`/projects/${project.id}/travel/refresh`, { method: 'POST' }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: key }) },
  })
  const booking = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'pending' | 'completed' | 'failed' }) => request<Research>(`/projects/${project.id}/travel/bookings/${id}`, {
      method: 'PATCH', body: JSON.stringify({ user_status: status }),
    }),
    onSuccess: (data) => client.setQueryData(key, data),
  })
  const update = useUpdateProject(project.id)
  const [editing, setEditing] = useState(false)
  const [conditions, setConditions] = useState<TravelConditions>({ ...EMPTY_TRAVEL, ...project.travel_conditions })
  const research = query.data
  const plan = research?.data.plan
  const running = research?.status === 'queued' || research?.status === 'researching'
  const error = refresh.error ?? update.error ?? booking.error ?? query.error
  return (
    <section className="mb-6 border-y border-line py-5" aria-label="旅行资料">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-base font-semibold">旅行资料{research ? ` · v${research.version}` : ''}</h2>
        {!locked && <Button size="sm" variant="ghost" disabled={running || update.isPending} onClick={() => { setConditions({ ...EMPTY_TRAVEL, ...project.travel_conditions }); setEditing(!editing) }}>
          <Settings2 className="size-4" />调整条件
        </Button>}
        {!locked && <Button size="sm" variant="ghost" disabled={running || refresh.isPending || editing} onClick={() => refresh.mutate()}>
          <RefreshCw className={`size-4 ${running || refresh.isPending ? 'animate-spin' : ''}`} />刷新资料
        </Button>}
      </div>
      {editing && <>
        <TravelForm value={conditions} onChange={setConditions} disabled={update.isPending} />
        <Button className="mt-3" size="sm" disabled={!conditions.confirmed || !conditions.destination?.trim() || update.isPending} onClick={() => update.mutate({ travel_conditions: conditions }, {
          onSuccess: () => { setEditing(false); void client.invalidateQueries({ queryKey: key }) },
        })}><Check className="size-4" />保存条件</Button>
      </>}
      {running && <div className="mt-4" aria-live="polite">
        <p className="flex items-center gap-2 text-sm text-ink-muted"><Loader2 className="size-4 animate-spin" />{research.stage}</p>
        <progress className="mt-2 h-2 w-full accent-accent" value={research.progress} max={100} />
      </div>}
      {research?.stale && <p role="status" className="mt-3 text-sm text-warning">资料已失效，请刷新资料并重新生成大纲。</p>}
      {research?.status === 'failed' && <p role="alert" className="mt-3 text-sm text-negative">查询未完成：{research.stage}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-negative">{errorMessage(error)}</p>}
      {research?.status === 'partial' && <p role="status" className="mt-3 text-sm text-warning">旅行查询部分完成，已有资料可查看，仍有信息待核实。</p>}
      {research?.data.services && <div className="mt-3 grid gap-3 text-xs sm:grid-cols-3">
        {research.data.services.map((service) => <div key={service.service} className="min-w-0 border-l-2 border-line pl-3">
          <p className={service.status === 'ready' ? 'text-positive' : 'text-warning'}>{serviceLabels[service.service] ?? service.service} · {statusLabels[service.status]}</p>
          {service.status !== 'ready' && <p className="mt-1 break-words text-ink-muted">{service.message ?? travelServiceMessage(service.error_code)} {service.action ?? '请检查服务配置后刷新旅行资料。'}</p>}
        </div>)}
      </div>}
      {!!research?.data.issues?.length && <div role="status" className="mt-4 space-y-2 border-l-2 border-warning pl-3">
        {research.data.issues.map((issue, index) => <div key={`${issue.code}-${index}`}><p className="text-xs text-warning">{issue.stage}：{issue.message}</p><p className="mt-1 text-xs text-ink-muted">{issue.action}</p></div>)}
      </div>}
      {research && !research.stale && !!research.data.videos?.length && <details className="mt-4 text-sm" open>
        <summary className="cursor-pointer font-medium">视频攻略 · {research.data.videos.filter((video) => video.selected).length} 条入选</summary>
        <ul className="mt-3 divide-y divide-line">
          {research.data.videos.map((video) => <li key={video.id} className="min-w-0 py-3">
            <a href={video.url} target="_blank" rel="noreferrer" className="break-words text-accent hover:underline">{video.title || video.url}</a>
            <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-muted">
              <span>{video.platform === 'douyin' ? '抖音' : 'B 站'}{video.author ? ` · ${video.author}` : ''}</span>
              <span>点赞 {video.likes == null ? '未知' : `${video.counts_approximate ? '约 ' : ''}${video.likes.toLocaleString()}`}</span>
              <span>收藏 {video.favorites == null ? '未知' : `${video.counts_approximate ? '约 ' : ''}${video.favorites.toLocaleString()}`}</span>
              <span>发布 {video.published_at ? new Date(video.published_at).toLocaleDateString('zh-CN') : '未知'}</span>
              <span>时长 {video.duration_seconds == null ? '未知' : `${Math.floor(video.duration_seconds / 60)}:${String(Math.floor(video.duration_seconds % 60)).padStart(2, '0')}`}</span>
              <span>{videoStatusLabels[video.error_code ?? video.status ?? 'candidate'] ?? '读取未完成'}</span>
            </p>
            {video.content_kind && <p className="mt-1 text-xs text-ink-muted">{{ subtitles: '平台字幕', transcription: '语音转写', platform_summary: '平台 AI 章节摘要' }[video.content_kind]}{video.content_truncated ? ' · 部分内容' : ''} · 体验参考</p>}
            {research.data.video_advice?.filter((item) => item.video_id === video.id).map((item) => <p key={item.id} className="mt-2 break-words text-xs text-ink-soft">
              {adviceLabels[item.kind]} · {item.place}：{item.suggestion}
              <span className="ml-2 text-ink-muted">{Math.floor(item.timestamp_seconds / 60)}:{String(Math.floor(item.timestamp_seconds % 60)).padStart(2, '0')}{item.end_timestamp_seconds != null ? `–${Math.floor(item.end_timestamp_seconds / 60)}:${String(Math.floor(item.end_timestamp_seconds % 60)).padStart(2, '0')}` : '（结束时间未取得）'}</span>
            </p>)}
          </li>)}
        </ul>
      </details>}
      {plan && !research?.stale && <div className="mt-4 space-y-4 text-sm">
        <p className="text-ink-muted">{plan.draft ? '建议草案' : '规划资料'} · {plan.conditions.destination} · {plan.conditions.departure_date ?? '日期待确认'} 至 {plan.conditions.return_date ?? '日期待确认'}</p>
        <p role="status" className="text-xs text-ink-muted">{new Set(plan.days.flatMap((day) => day.stops.map((stop) => stop.place_id))).size} 个计划景点，最低 {new Set(plan.days.flatMap((day) => day.stops.map((stop) => stop.place_id))).size + 5} 页；景点规则、完整日期及费用明细会继续拆页。</p>
        {!!research?.data.route_map?.url && <figure>
          <img src={research.data.route_map.url} alt="旅行路线总地图" className="max-h-80 w-full object-contain" />
          <figcaption className="mt-1 text-xs text-ink-muted">{research.data.route_map.note}</figcaption>
        </figure>}
        <details open>
          <summary className="cursor-pointer font-medium">逐日路线与天气</summary>
          <div className="mt-3 space-y-4">
            {plan.days.map((day) => <div key={day.day} className="border-l-2 border-line pl-3">
              <h3 className="font-medium">第 {day.day} 天 {day.date ?? '建议日期'}</h3>
              <p className="mt-1 text-xs text-ink-muted">{day.weather?.status === 'ready'
                ? `${day.weather.condition} · ${day.weather.temp_min}–${day.weather.temp_max} °C · 降水 ${day.weather.precipitation || '待查询'} · 风 ${day.weather.wind || '待查询'}`
                : day.weather?.note ?? '天气待更新'}</p>
              <p className="mt-1 text-xs text-ink-muted">空气质量预报：{day.air_quality?.status === 'ready'
                ? `${day.air_quality.standard} · AQI ${day.air_quality.aqi_display || day.air_quality.aqi} · ${day.air_quality.category}`
                : day.air_quality?.note ?? '暂未发布 / 未取得'}</p>
              {day.air_quality?.valid_from && <p className="mt-1 text-xs text-ink-muted">有效 {new Date(day.air_quality.valid_from).toLocaleString('zh-CN')} 至 {day.air_quality.valid_until ? new Date(day.air_quality.valid_until).toLocaleString('zh-CN') : '待确认'}</p>}
              <ol className="mt-2 space-y-2">
                {day.stops?.map((stop) => <li key={stop.place_id}>
                  <p>{stop.start.slice(0, 5)}–{stop.end.slice(0, 5)} {stop.name} <span className="text-xs text-ink-muted">建议游览时段</span></p>
                  {stop.internal_route?.map((line) => <p key={line} className="mt-1 text-xs text-ink-muted">导览：{line}</p>)}
                  {stop.checkin_spots?.map((line) => <p key={line} className="mt-1 text-xs text-ink-muted">打卡：{line}</p>)}
                  {stop.warnings?.map((line) => <p key={line} className="mt-1 text-xs text-warning">{line}</p>)}
                </li>)}
              </ol>
              {day.routes?.map((route, index) => <p key={index} className="mt-1 text-xs text-ink-muted">交通：{route.distance_m == null ? '距离待查询' : `${(route.distance_m / 1000).toFixed(1)} km`} · {route.duration_minutes ?? '待查询'} 分钟 · {money(route.cost)}</p>)}
              {day.breaks?.map((line) => <p key={line} className="mt-1 text-xs text-ink-muted">{line}</p>)}
              {day.warnings?.map((line) => <p key={line} className="mt-1 text-xs text-warning">{line}</p>)}
              {day.alternatives?.map((line) => <p key={line} className="mt-1 text-xs text-ink-muted">替代安排：{line}</p>)}
            </div>)}
          </div>
          {research?.data.current_air_quality && <p className="mt-3 text-xs text-ink-muted">当前实况 {research.data.current_air_quality.date}：{research.data.current_air_quality.standard} · AQI {research.data.current_air_quality.aqi_display || research.data.current_air_quality.aqi} · {research.data.current_air_quality.category}。当前实况不是未来出行预报。</p>}
          {plan.preparation?.map((line) => <p key={line} className="mt-2 text-xs text-ink-soft">准备：{line}</p>)}
        </details>
        <details><summary className="cursor-pointer font-medium">出发返程与住宿</summary>
          {[...(plan.transport ?? []), ...(plan.lodging ?? [])].map((line) => <p key={line} className="mt-2 break-words text-ink-soft">{line}</p>)}
        </details>
        <details open><summary className="cursor-pointer font-medium">预算与缺价项目</summary>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[420px] text-left text-xs">
              <thead><tr className="border-b border-line text-ink-muted"><th className="py-2">项目</th><th>口径</th><th>单价 × 数量 × 天数</th><th className="text-right">小计</th></tr></thead>
              <tbody>{plan.cost_items.map((item) => <tr key={item.id} className="border-b border-line/50 align-top">
                <td className="py-2 pr-2">{item.label}<p className="mt-1 max-w-64 break-words text-ink-muted">{item.conditions}</p></td>
                <td className="py-2 pr-2 whitespace-nowrap">{priceLabels[item.kind ?? 'pending']}</td>
                <td className="py-2">{money(item.unit_price)} / {item.unit} × {item.quantity ?? 1} × {item.days ?? 1}</td>
                <td className="py-2 text-right whitespace-nowrap">{money(item.subtotal)}</td>
              </tr>)}</tbody>
            </table>
          </div>
          <p className="mt-3">已知小计 {money(plan.known_subtotal)} · 估算小计 {money(plan.estimated_subtotal)} · 预算 {money(plan.budget_limit)}</p>
          <p className="mt-2">备用金 {money(plan.contingency_subtotal)} · {plan.total_complete ? '规划合计' : '部分合计（不含缺价）'} {money(plan.total)} · 人均 {money(plan.per_person)} · 预算余额 {money(plan.budget_difference)}</p>
          {plan.budget_exceeded && <p className="mt-1 text-negative">已知费用与估算之和已超过预算。</p>}
          {plan.warnings?.map((line) => <p key={line} className="mt-1 text-xs text-warning">{line}</p>)}
        </details>
        <details open><summary className="cursor-pointer font-medium">预约待办</summary>
          {plan.booking_tasks.map((task) => <div key={task.id} className="mt-3 flex items-start gap-3">
            <div className="min-w-0 flex-1"><p>{task.title} · {task.rule_status === 'verified' ? '规则已核实' : '规则待核实'}</p>
              <p className="mt-1 break-words text-xs text-ink-muted">{task.rule}</p>
              {task.url && <a className="mt-1 inline-block text-xs text-accent underline" href={task.url} target="_blank" rel="noreferrer">查看来源</a>}
            </div>
            <select aria-label={`${task.title}状态`} className="shrink-0 rounded-lg border border-line bg-surface p-1.5 text-xs" value={task.user_status ?? 'pending'}
              disabled={booking.isPending} onChange={(event) => booking.mutate({ id: task.id, status: event.target.value as 'pending' | 'completed' | 'failed' })}>
              <option value="pending">待预约</option><option value="completed">已预约</option><option value="failed">预约失败</option>
            </select>
          </div>)}
        </details>
        <details><summary className="cursor-pointer font-medium">资料来源与待核实项目</summary>
          <ul className="mt-2 space-y-1 text-xs text-warning">{plan.unresolved_items.map((line) => <li key={line}>{line}</li>)}</ul>
          {research?.data.sources?.map((source) => <p key={source.id} className="mt-2 break-words text-xs text-ink-muted">
            {source.id} · <a className="text-accent underline" href={source.url} target="_blank" rel="noreferrer">{source.title}</a> · {source.trust === 'official' ? '官方来源' : source.trust === 'provider' ? '服务商数据' : '来源待核实'} · {new Date(source.retrieved_at).toLocaleString('zh-CN')}
          </p>)}
          {research?.data.facts?.map((fact) => <p key={fact.id} className="mt-2 break-words text-xs text-ink-soft">{fact.id} · {fact.source_id} · {fact.status === 'verified' ? '日期已核实' : fact.status === 'outdated' ? '旧资料' : '参考/待核实'}：{fact.quote}</p>)}
        </details>
      </div>}
    </section>
  )
}
