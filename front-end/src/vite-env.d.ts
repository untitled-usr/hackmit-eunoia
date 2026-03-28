/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MID_AUTH_ORIGIN?: string
  readonly VITE_VIRTMATE_APP_URL?: string
  readonly VITE_VIRTMATE_API_MODE?: string
  readonly VITE_VIRTMATE_API_PREFIX?: string
  readonly VITE_VIRTMATE_API_ORIGIN?: string
  readonly VITE_VIRTMATE_ASSET_ORIGIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
