import type { Config } from 'tailwindcss'
import sharedPreset from '@jobnok/ui/tailwind-preset'

const config: Config = {
  presets: [sharedPreset],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
    '../../packages/ui/src/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: { '2xl': '1400px' },
    },
  },
}

export default config
