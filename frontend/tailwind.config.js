/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#171a1c',
        sand: '#f6f3ee',
        paper: '#fffdfa',
        line: '#e5ded3',
        jade: {
          50: '#eef7f4',
          100: '#d6ece5',
          300: '#8fc9ba',
          500: '#2f8f79',
          600: '#22745f',
          700: '#1b5a4b',
          900: '#0f332b',
        },
        clay: {
          100: '#fbe8dd',
          500: '#c56a3d',
          600: '#a8552e',
        },
      },
      fontFamily: {
        sans: [
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
        number: ['"DM Mono"', '"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(23,26,28,0.04), 0 8px 24px -12px rgba(23,26,28,0.18)',
      },
      keyframes: {
        rise: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        rise: 'rise 180ms ease-out',
      },
    },
  },
  plugins: [],
}
