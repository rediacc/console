import React from 'react'
import ReactDOM from 'react-dom/client'
import { Provider } from 'react-redux'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { store } from './store/store'
import App from './App'
import { AppProviders } from './components/common/AppProviders'
import './index.css'
import i18n from './i18n/config'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000, // 10 minutes
      refetchOnWindowFocus: false,
    },
  },
})

// Wait for i18n to initialize before rendering
i18n.on('initialized', () => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>
          <AppProviders>
            <App />
            <Toaster
                position="top-center"
                toastOptions={{
                  duration: 4000,
                  style: {
                    background: '#1f2937',
                    color: '#fff',
                  },
                  success: {
                    iconTheme: {
                      primary: '#333333',
                      secondary: '#fff',
                    },
                  },
                  error: {
                    iconTheme: {
                      primary: '#666666',
                      secondary: '#fff',
                    },
                  },
                }}
              />
          </AppProviders>
        </QueryClientProvider>
      </Provider>
    </React.StrictMode>
  )
})

// If i18n is already initialized, render immediately
if (i18n.isInitialized) {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>
          <AppProviders>
            <App />
            <Toaster
                position="top-center"
                toastOptions={{
                  duration: 4000,
                  style: {
                    background: '#1f2937',
                    color: '#fff',
                  },
                  success: {
                    iconTheme: {
                      primary: '#333333',
                      secondary: '#fff',
                    },
                  },
                  error: {
                    iconTheme: {
                      primary: '#666666',
                      secondary: '#fff',
                    },
                  },
                }}
              />
          </AppProviders>
        </QueryClientProvider>
      </Provider>
    </React.StrictMode>
  )
}