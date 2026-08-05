import type { ReactNode } from 'react'
import { NavLink } from 'react-router'
import { Button } from '@/components/ui/Button'
import { useAuthStore } from '@/features/auth/store'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: '工作台' },
  { to: '/projects', label: 'PPT' },
  { to: '/preview', label: '渲染基线' },
]

export function AppShell({ children }: { children: ReactNode }) {
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-8 py-5">
          <div className="flex items-baseline gap-8">
            <span className="text-lg leading-none font-semibold tracking-tight">AI PPT 生成器</span>
            <nav className="flex items-baseline gap-6">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'text-sm transition-colors',
                      isActive ? 'text-ink' : 'text-ink-muted hover:text-accent',
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-5">
            <span className="text-sm text-ink-muted">{user?.email}</span>
            <Button variant="ghost" onClick={logout} className="h-8 px-0 text-sm">
              退出登录
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-8">{children}</main>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-6xl px-8 py-6 text-xs text-ink-muted">
          固定 16:9 画幅 · 导出为原生可编辑 PPTX
        </div>
      </footer>
    </div>
  )
}
