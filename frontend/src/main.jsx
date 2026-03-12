import React from 'react'
import ReactDOM from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
    <Toaster
      position="bottom-right"
      toastOptions={{
        duration: 4000,
        style: { fontSize: '0.875rem' },
        success: { iconTheme: { primary: '#22c55e', secondary: '#fff' } },
        error: { iconTheme: { primary: '#ef4444', secondary: '#fff' }, duration: 6000 },
      }}
    />
  </React.StrictMode>,
)
