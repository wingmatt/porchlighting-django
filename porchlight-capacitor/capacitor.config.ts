import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.porchlighting.app',
  appName: 'Porchlighting',
  webDir: 'dist',
  server: {
    // Opt in only for local Android HTTP API testing; production must use HTTPS.
    cleartext: process.env.CAPACITOR_CLEAR_TEXT === 'true',
  },
};

export default config;