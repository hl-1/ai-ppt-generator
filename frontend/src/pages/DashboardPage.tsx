import { Link } from 'react-router'
import { StatusRow } from '@/components/StatusRow'
import { useAuthStore } from '@/features/auth/store'
import { useHealth } from '@/features/system/api'

const MILESTONES = [
  { label: '内容与渲染基线', note: '统一内容模型、布局与主题、双渲染链路' },
  { label: '输入与大纲闭环', note: '文档解析、大纲生成与确认' },
  { label: '页面生成闭环', note: '并发生成、素材、图表与表格' },
  { label: '编辑闭环', note: '就地编辑、排序、单页 AI 修改' },
  { label: '交付闭环', note: '质量检查、PPTX 导出与回读验证' },
]

export default function DashboardPage() {
  const health = useHealth()
  const user = useAuthStore((state) => state.user)

  const tone = (state?: string) => {
    if (health.isPending || health.isError) return 'unknown' as const
    return state === 'ok' ? ('ok' as const) : ('down' as const)
  }

  return (
    <>
      <section className="border-b border-line py-16">
        <p className="mb-4 text-xs tracking-[0.2em] text-accent uppercase">工作台</p>
        <h1 className="font-display text-[clamp(2rem,4vw,2.75rem)] leading-[1.3]">
          欢迎回来，{user?.email.split('@')[0]}。
        </h1>
        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-ink-soft">
          现在可以创建 PPT 并录入材料了。大纲生成会在下一个里程碑接入。
        </p>
        <Link
          to="/projects"
          className="mt-8 inline-block border-b border-accent pb-1 text-sm text-accent"
        >
          进入 PPT 列表
        </Link>
      </section>

      <div className="grid gap-16 py-16 md:grid-cols-[1fr_1.1fr]">
        <section>
          <h2 className="mb-1 text-sm font-semibold tracking-wide">系统状态</h2>
          <p className="mb-6 text-sm text-ink-muted">每 10 秒自动探活一次。</p>
          <div className="border-t border-line">
            <StatusRow
              name="API 服务"
              hint="FastAPI"
              tone={health.isError ? 'down' : health.isPending ? 'unknown' : 'ok'}
            />
            <StatusRow name="PostgreSQL" hint="内容与任务状态" tone={tone(health.data?.database)} />
            <StatusRow name="Redis" hint="队列与进度广播" tone={tone(health.data?.redis)} />
          </div>
        </section>

        <section>
          <h2 className="mb-1 text-sm font-semibold tracking-wide">实施里程碑</h2>
          <p className="mb-6 text-sm text-ink-muted">按顺序推进，前一阶段未验证不扩展外围功能。</p>
          <ol className="border-t border-line">
            {MILESTONES.map((milestone, index) => (
              <li
                key={milestone.label}
                className="flex items-baseline gap-4 border-b border-line py-4 last:border-b-0"
              >
                <span className="w-8 shrink-0 font-display text-lg text-line-strong tabular-nums">
                  M{index}
                </span>
                <span className="w-36 shrink-0 text-sm font-medium">{milestone.label}</span>
                <span className="flex-1 text-sm text-ink-muted">{milestone.note}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </>
  )
}
