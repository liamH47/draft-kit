import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import './App.css'
import { CheatSheet } from './routes/CheatSheet'
import { DraftBoard } from './routes/DraftBoard'
import { Login } from './routes/Login'
import { SetupWizard } from './routes/SetupWizard'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<SetupWizard />} />
          <Route path="/login" element={<Login />} />
          <Route path="/draft/:sessionId" element={<DraftBoard />} />
          <Route path="/cheatsheet/:leagueId" element={<CheatSheet />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
