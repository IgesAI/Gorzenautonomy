/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        glass: {
          50: 'rgba(255, 255, 255, 0.05)',
          100: 'rgba(255, 255, 255, 0.10)',
          200: 'rgba(255, 255, 255, 0.15)',
          300: 'rgba(255, 255, 255, 0.20)',
          border: 'rgba(255, 255, 255, 0.12)',
        },
        gorzen: {
          50: '#fafafa',
          100: '#f5f5f5',
          200: '#e5e5e5',
          300: '#d4d4d4',
          400: '#d4d4d4',
          500: '#ffffff',
          600: '#b0b0b0',
          700: '#8a8a8a',
          800: '#636363',
          900: '#404040',
          950: '#1a1a1a',
        },
        surface: {
          dark: '#050505',
          card: 'rgba(10, 10, 10, 0.85)',
          elevated: 'rgba(18, 18, 18, 0.90)',
        },
      },
      backdropBlur: {
        glass: '20px',
        'glass-heavy': '40px',
      },
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        'glass': '0 4px 24px rgba(0, 0, 0, 0.35), 0 1px 0 rgba(255, 255, 255, 0.03) inset',
        'glass-lg': '0 12px 40px rgba(0, 0, 0, 0.45), 0 1px 0 rgba(255, 255, 255, 0.04) inset',
        'card': '0 2px 12px rgba(0, 0, 0, 0.3)',
        'glow-gorzen': '0 0 20px rgba(255, 255, 255, 0.08)',
      },
    },
  },
  plugins: [],
};
