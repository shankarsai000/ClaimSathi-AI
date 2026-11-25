import { Routes, Route, Navigate } from 'react-router-dom'
import { AppSettingsProvider } from './i18n'
import Layout from './components/Layout'
import LandingPage from './landing/LandingPage'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import NewClaim from './pages/NewClaim'
import ClaimDetail from './pages/ClaimDetail'
import EvidenceVerify from './pages/EvidenceVerify'

export default function App() {
  return (
    <AppSettingsProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<Login />} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/claims/new" element={<NewClaim />} />
          <Route path="/claims/:id" element={<ClaimDetail />} />
          <Route path="/evidence-verify" element={<EvidenceVerify />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppSettingsProvider>
  )
}
