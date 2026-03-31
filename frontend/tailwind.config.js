/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#e9faf3',
          100: '#c9f0de',
          200: '#94ddbe',
          300: '#67cda3',
          400: '#45be8c',
          500: '#2f9b75',
          600: '#227a5b',
          700: '#1b5f47',
          800: '#144736',
          900: '#0e3326'
        },
        slatewarm: {
          50: '#eef2f6',
          100: '#d7dee7',
          200: '#aeb9c9',
          300: '#8797af',
          400: '#62738d',
          500: '#465468',
          600: '#344051',
          700: '#242d3b',
          800: '#151b24',
          900: '#0b0e12'
        }
      },
      borderRadius: {
        xl2: '18px'
      },
      boxShadow: {
        soft: '0 8px 24px rgba(0,0,0,0.22)'
      }
    }
  },
  plugins: []
}

