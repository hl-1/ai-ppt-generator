import { type FormEvent, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { errorMessage } from '@/lib/errors'
import { Button } from '@/components/ui/Button'
import { TextField } from '@/components/ui/TextField'
import { login, register } from '@/features/auth/api'
import { useAuthStore } from '@/features/auth/store'

type Mode = 'login' | 'register'

const COPY: Record<Mode, { title: string; submit: string; switchHint: string; switchTo: string }> =
  {
    login: {
      title: '登录',
      submit: '登录',
      switchHint: '还没有账号？',
      switchTo: '注册一个',
    },
    register: {
      title: '注册',
      submit: '创建账号',
      switchHint: '已经有账号了？',
      switchTo: '去登录',
    },
  }

export default function AuthPage() {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const user = useAuthStore((state) => state.user)
  const applySession = useAuthStore((state) => state.applySession)
  const navigate = useNavigate()
  const location = useLocation()

  if (user) {
    return <Navigate to="/" replace />
  }

  const copy = COPY[mode]

  const switchMode = () => {
    setMode(mode === 'login' ? 'register' : 'login')
    setError(null)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const session = await (mode === 'login' ? login : register)({ email, password })
      applySession(session)
      const from = (location.state as { from?: string } | null)?.from ?? '/'
      navigate(from, { replace: true })
    } catch (cause) {
      setError(errorMessage(cause instanceof Error ? cause : null, '网络异常，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="bg-grid relative hidden flex-col justify-between border-r border-line p-14 lg:flex">
        <div className="flex items-baseline gap-3">
          <span className="text-lg leading-none font-semibold tracking-tight">AI PPT 生成器</span>
          <span className="font-display text-sm text-ink-muted">Presentation Studio</span>
        </div>

        <div className="max-w-md">
          <p className="mb-6 text-xs tracking-[0.2em] text-accent uppercase">
            输入 · 规划 · 生成 · 编辑 · 导出
          </p>
          <h1 className="font-display text-[2.75rem] leading-[1.3]">
            把一段想法，变成
            <span className="text-accent underline decoration-accent/30 decoration-1 underline-offset-8">
              可以直接编辑
            </span>
            的 PPT。
          </h1>
        </div>

        <p className="text-xs text-ink-muted">固定 16:9 画幅 · 导出为原生可编辑 PPTX</p>
      </section>

      <section className="flex items-center justify-center px-8 py-16">
        <div className="w-full max-w-sm">
          <h2 className="font-display text-3xl">{copy.title}</h2>
          <p className="mt-2 mb-10 text-sm text-ink-muted">
            项目、素材与成品按账号隔离，不会跨账号可见。
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-7" noValidate>
            <TextField
              label="邮箱"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
            <TextField
              label="密码"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="至少 8 位"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={8}
              hint={mode === 'register' ? '至少 8 位字符。' : undefined}
              required
            />

            {error && (
              <p role="alert" className="border-l-2 border-negative py-2 pl-3 text-sm text-negative">
                {error}
              </p>
            )}

            <Button type="submit" disabled={submitting} className="mt-1 w-full">
              {submitting ? '处理中…' : copy.submit}
            </Button>
          </form>

          <p className="mt-8 text-sm text-ink-muted">
            {copy.switchHint}
            <button
              type="button"
              onClick={switchMode}
              className="ml-1 text-ink underline decoration-line-strong underline-offset-4 transition-colors hover:text-accent hover:decoration-accent"
            >
              {copy.switchTo}
            </button>
          </p>
        </div>
      </section>
    </div>
  )
}
