/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates_arena/**/*.html",
    "./static/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        arena: {
          dark: '#0a0a0f',
          darker: '#050508',
          gold: '#ffd700',
          bronze: '#cd7f32',
          silver: '#c0c0c0',
          purple: '#8b5cf6',
          blue: '#3b82f6',
          green: '#22c55e',
          red: '#ef4444'
        },
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        },
      },
      fontFamily: {
        display: ['Cinzel', 'serif'],
        body: ['Inter', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'bounce-slow': 'bounce 2s infinite',
      },
    },
  },
  plugins: [],
}
