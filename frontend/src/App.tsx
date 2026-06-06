import { Route, Routes } from 'react-router-dom'
import { Navbar } from './components/Navbar'
import AboutPage from './pages/AboutPage'
import DashboardPage from './pages/DashboardPage'
import MaintenancePage from './pages/MaintenancePage'
import MapPage from './pages/MapPage'

// Backend is paused for cost reasons; set VITE_MAINTENANCE_MODE to 'true' in
// Vercel to serve the standalone maintenance page, or unset it to restore the app.
const MAINTENANCE_MODE = import.meta.env.VITE_MAINTENANCE_MODE === 'true'

export default function App() {
  if (MAINTENANCE_MODE) {
    return <MaintenancePage />
  }

  return (
    <div className="layout">
      <Navbar />
      <Routes>
        <Route path="/" element={<MapPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/about" element={<AboutPage />} />
      </Routes>
    </div>
  )
}
