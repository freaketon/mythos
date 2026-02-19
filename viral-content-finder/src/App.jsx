import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Onboarding from './pages/Onboarding'
import OutlierFeed from './pages/OutlierFeed'
import ContentBriefs from './pages/ContentBriefs'
import DailyDigest from './pages/DailyDigest'

function App() {
  const [isOnboarded, setIsOnboarded] = useState(false)
  const [userConfig, setUserConfig] = useState(null)

  if (!isOnboarded) {
    return (
      <Onboarding
        onComplete={(config) => {
          setUserConfig(config)
          setIsOnboarded(true)
        }}
      />
    )
  }

  return (
    <Layout userConfig={userConfig}>
      <Routes>
        <Route path="/" element={<OutlierFeed userConfig={userConfig} />} />
        <Route path="/briefs" element={<ContentBriefs userConfig={userConfig} />} />
        <Route path="/digest" element={<DailyDigest userConfig={userConfig} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}

export default App
