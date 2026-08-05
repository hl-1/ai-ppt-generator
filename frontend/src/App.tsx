import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AppShell } from '@/components/AppShell'
import { useAuthStore } from '@/features/auth/store'
import AuthPage from '@/pages/AuthPage'
import DashboardPage from '@/pages/DashboardPage'
import { RequireAuth } from '@/routes/RequireAuth'

export default function App() {
  const restore = useAuthStore((state) => state.restore)

  useEffect(() => {
    void restore()
  }, [restore])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <AppShell>
                <DashboardPage />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
