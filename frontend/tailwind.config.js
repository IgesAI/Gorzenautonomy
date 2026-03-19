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
          50: '#eef6ff',
          100: '#d9ebff',
          200: '#bbdcff',
          300: '#8cc5ff',
          400: '#56a4ff',
          500: '#2f7fff',
          600: '#1860f5',
          700: '#104ae1',
          800: '#143db6',
          900: '#17388f',
          950: '#122357',
        },
        surface: {
          dark: '#0a0e1a',
          card: 'rgba(15, 20, 40, 0.75)',
          elevated: 'rgba(20, 28, 55, 0.80)',
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
        'glass': '0 4px 24px rgba(0, 0, 0, 0.25), 0 1px 0 rgba(255, 255, 255, 0.04) inset',
        'glass-lg': '0 12px 40px rgba(0, 0, 0, 0.35), 0 1px 0 rgba(255, 255, 255, 0.06) inset',
        'card': '0 2px 12px rgba(0, 0, 0, 0.2)',
        'glow-gorzen': '0 0 20px rgba(47, 127, 255, 0.15)',
      },
      keyframes: {
        'drone-tint-wave': {
          '0%, 100%': {
            background: 'radial-gradient(ellipse 60% 50% at 50% 25%, rgba(47, 127, 255, 0.30) 0%, rgba(16, 74, 225, 0.12) 40%, transparent 70%)',
          },
          '25%': {
            background: 'radial-gradient(ellipse 60% 50% at 25% 55%, rgba(47, 127, 255, 0.30) 0%, rgba(16, 74, 225, 0.12) 40%, transparent 70%)',
          },
          '50%': {
            background: 'radial-gradient(ellipse 60% 50% at 50% 75%, rgba(47, 127, 255, 0.30) 0%, rgba(16, 74, 225, 0.12) 40%, transparent 70%)',
          },
          '75%': {
            background: 'radial-gradient(ellipse 60% 50% at 75% 45%, rgba(47, 127, 255, 0.30) 0%, rgba(16, 74, 225, 0.12) 40%, transparent 70%)',
          },
        },
      },
      animation: {
        'drone-tint': 'drone-tint-wave 8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
