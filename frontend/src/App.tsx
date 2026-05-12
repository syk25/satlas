import { Route, Routes } from 'react-router-dom'
import { Navbar } from './components/Navbar'
import DashboardPage from './pages/DashboardPage'
import MapPage from './pages/MapPage'

export default function App() {
  return (
    <div className="layout">
      <Navbar />
      <Routes>
        <Route path="/" element={<MapPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </div>
  )
}
