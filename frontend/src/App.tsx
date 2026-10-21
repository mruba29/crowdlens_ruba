import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppProvider } from './store'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import CrowdVideos from './pages/CrowdVideos'
import VideoDetail from './pages/VideoDetail'
import LiveAnalysis from './pages/LiveAnalysis'
import CrowdAnalytics from './pages/CrowdAnalytics'
import Alerts from './pages/Alerts'
import Incidents from './pages/Incidents'
import PredictiveRisk from './pages/PredictiveRisk'
import Settings from './pages/Settings'
import Events from './pages/Events'
import EventDetail from './pages/EventDetail'
import EventTimeline from './pages/EventTimeline'
import EventMultiCam from './pages/EventMultiCam'

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/events" element={<Events />} />
            <Route path="/events/:id" element={<EventDetail />} />
            <Route path="/events/:id/timeline" element={<EventTimeline />} />
            <Route path="/events/:id/multicam" element={<EventMultiCam />} />
            <Route path="/videos" element={<CrowdVideos />} />
            <Route path="/videos/:id" element={<VideoDetail />} />
            <Route path="/live" element={<LiveAnalysis />} />
            <Route path="/analytics" element={<CrowdAnalytics />} />
            <Route path="/predictive-risk" element={<PredictiveRisk />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </AppProvider>
    </BrowserRouter>
  )
}
