import { useState } from 'react'
import './landing.css'
import Navbar from './components/Navbar'
import HeroSection from './components/HeroSection'
import TrustBar from './components/TrustBar'
import InteractivePlayground from './components/InteractivePlayground'
import WorkflowAndBento from './components/WorkflowAndBento'
import ComplianceFaqFooter from './components/ComplianceFaqFooter'

export default function LandingPage() {
  const [pilotModalOpen, setPilotModalOpen] = useState(false)

  return (
    <div className="landing-root min-h-screen bg-white text-slate-900">
      <Navbar onOpenPilotModal={() => setPilotModalOpen(true)} />
      <main>
        <HeroSection onOpenPilotModal={() => setPilotModalOpen(true)} />
        <TrustBar />
        <InteractivePlayground />
        <WorkflowAndBento />
        <ComplianceFaqFooter
          pilotModalOpen={pilotModalOpen}
          onOpenPilotModal={() => setPilotModalOpen(true)}
          onClosePilotModal={() => setPilotModalOpen(false)}
        />
      </main>
    </div>
  )
}
