import type { ReactNode } from 'react'
import { Button } from '@/components/ui/Button'
import { useAuthStore } from '@/features/auth/store'

export function AppShell({ children }: { children: ReactNode }) {
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-8 py-5">
          <div className="flex items-baseline gap-3">
            <span className="text-lg leading-none font-semibold tracking-tight">AI PPT 生成器</span>
            <span className="font-display text-sm text-ink-muted">Presentation Studio</span>
          </div>
          <div className="flex items-center gap-5">
            <span className="text-sm text-ink-muted">{user?.email}</span>
            <Button variant="ghost" onClick={logout} className="h-8 px-0 text-sm">
              退出登录
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-8">{children}</main>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-5xl px-8 py-6 text-xs text-ink-muted">
          固定 16:9 画幅 · 导出为原生可编辑 PPTX
        </div>
      </footer>
    </div>
  )
}
