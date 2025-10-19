import React from 'react'
import ReactDOM from 'react-dom/client'
import { Provider } from 'react-redux'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { store } from './store/store'
import App from './App'
import { AppProviders } from './components/common/AppProviders'
import './index.css' // Minimal global styles - most styling in antdTheme.ts and GlobalStyles.ts
import i18n from './i18n/config'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000, // 10 minutes
      refetchOnWindowFocus: false,
    },
    mutations: {
      // Disable React Query's default error toasts
      // We handle errors in our mutations
      onError: () => {
        // Do nothing - let individual mutations handle their errors
      },
    },
  },
})

const renderApplication = () => {
  const StrictModeWrapper = import.meta.env.DEV ? React.StrictMode : React.Fragment;
  
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <StrictModeWrapper>
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>
          <AppProviders>
            <App />
          </AppProviders>
        </QueryClientProvider>
      </Provider>
    </StrictModeWrapper>
  )
}

// Wait for i18n to initialize before rendering
i18n.on('initialized', renderApplication)

// If i18n is already initialized, render immediately
if (i18n.isInitialized) {
  renderApplication()
}