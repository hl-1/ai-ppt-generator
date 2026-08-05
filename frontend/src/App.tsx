import { StatusRow } from '@/components/StatusRow'
import { useHealth } from '@/features/system/api'

const MILESTONES = [
  { label: '内容与渲染基线', note: '统一内容模型、布局与主题、双渲染链路' },
  { label: '输入与大纲闭环', note: '文档解析、大纲生成与确认' },
  { label: '页面生成闭环', note: '并发生成、素材、图表与表格' },
  { label: '编辑闭环', note: '就地编辑、排序、单页 AI 修改' },
  { label: '交付闭环', note: '质量检查、PPTX 导出与回读验证' },
]

export default function App() {
  const health = useHealth()

  const tone = (state?: string) => {
    if (health.isPending || health.isError) return 'unknown' as const
    return state === 'ok' ? ('ok' as const) : ('down' as const)
  }

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-8 py-5">
          <div className="flex items-baseline gap-3">
            <span className="text-lg leading-none font-semibold tracking-tight">AI PPT 生成器</span>
            <span className="font-display text-sm text-ink-muted">Presentation Studio</span>
          </div>
          <span className="text-xs text-ink-muted">v0.1 · 脚手架</span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-8">
        <section className="bg-grid relative border-b border-line py-24">
          <div className="relative max-w-2xl">
            <p className="mb-6 text-xs tracking-[0.2em] text-accent uppercase">
              输入 · 规划 · 生成 · 编辑 · 导出
            </p>
            {/* 中文没有真斜体，浏览器会做合成倾斜，观感很差；
                因此强调改用色彩加下划线偏移，而不是 italic。 */}
            <h1 className="font-display text-[clamp(2.25rem,4.5vw,3.25rem)] leading-[1.25]">
              把一段想法，变成
              <span className="text-accent underline decoration-accent/30 decoration-1 underline-offset-8">
                可以直接编辑
              </span>
              的演示文稿。
            </h1>
            <p className="mt-8 max-w-lg text-[15px] leading-relaxed text-ink-soft">
              统一内容模型驱动 Web 预览与原生 PPTX 导出，同一份内容、同一套布局、同一组主题令牌，
              两端不会各说各话。
            </p>
          </div>
        </section>

        <div className="grid gap-16 py-20 md:grid-cols-[1fr_1.1fr]">
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
            {health.isError && (
              <p className="mt-6 border-l-2 border-negative bg-accent-soft/40 py-3 pl-4 text-sm text-ink-soft">
                无法连接后端。请先执行 <code className="font-medium">make up</code> 启动依赖服务，
                再执行 <code className="font-medium">make dev-api</code>。
              </p>
            )}
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
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-5xl px-8 py-6 text-xs text-ink-muted">
          固定 16:9 画幅 · 导出为原生可编辑 PPTX
        </div>
      </footer>
    </div>
  )
}
