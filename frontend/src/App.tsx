import { Routes, Route, Navigate } from 'react-router-dom'
import { AppSettingsProvider } from './i18n'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import NewClaim from './pages/NewClaim'
import ClaimDetail from './pages/ClaimDetail'

export default function App() {
  return (
    <AppSettingsProvider>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/login" element={<Login />} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/claims/new" element={<NewClaim />} />
          <Route path="/claims/:id" element={<ClaimDetail />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppSettingsProvider>
  )
}
