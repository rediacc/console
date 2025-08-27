/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_HTTP_PORT: string
  readonly VITE_SYSTEM_DOMAIN: string
  readonly VITE_APP_VERSION: string
  readonly VITE_BUILD_TYPE: 'DEBUG' | 'RELEASE'
  readonly VITE_SANDBOX_API_URL: string
  readonly MODE: string
  readonly DEV: boolean
  readonly PROD: boolean
  readonly SSR: boolean
  readonly BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}