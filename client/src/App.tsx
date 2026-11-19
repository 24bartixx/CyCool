import { Route, Routes } from 'react-router'
import Layout from './components/Layout.tsx'
import NotFoundPage from './pages/NotFoundPage.tsx'
import PlannerPage from './pages/PlannerPage.tsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<PlannerPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
