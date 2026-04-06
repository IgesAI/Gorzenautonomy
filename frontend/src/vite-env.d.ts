/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Set to a Cesium Ion access token to enable Cesium World Terrain on the mission globe. */
  readonly VITE_CESIUM_ION_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
