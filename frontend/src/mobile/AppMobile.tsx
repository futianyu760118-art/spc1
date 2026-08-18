import { BrowserRouter, Routes, Route } from 'react-router-dom'

export default function AppMobile() {
  return (
    <BrowserRouter basename="/m">
      <Routes>
        <Route path="/" element={<div style={{ padding: 24 }}>mobile ok</div>} />
      </Routes>
    </BrowserRouter>
  )
}
