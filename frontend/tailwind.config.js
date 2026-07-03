/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f3e8ff', 100: '#e4d0ff', 200: '#ccaaff', 300: '#aa7af5',
          400: '#7c3ee8', 500: '#6520e4', 600: '#5302e0', 700: '#4200b5',
          800: '#320090', 900: '#230068', 950: '#130040',
        },
        accent: {
          50: '#f0fffb', 100: '#ccfff0', 200: '#99ffe0', 300: '#55ffd0',
          400: '#00ffbf', 500: '#00d9a3', 600: '#00b386', 700: '#008c68',
          800: '#006650', 900: '#004438',
        },
        surface: {
          50: '#120826', 100: '#1e0f40', 200: '#2d1b5c', 300: '#4a3078',
          400: '#715aa0', 500: '#9880c0', 600: '#bfb3d8', 700: '#ddd7ee',
          800: '#eeeaf8', 900: '#f7f4fd', 950: '#fdf9ff',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 4px 0 rgba(83,2,224,0.06), 0 4px 16px 0 rgba(83,2,224,0.04)',
        'card-hover': '0 4px 24px 0 rgba(83,2,224,0.12), 0 1px 4px 0 rgba(83,2,224,0.06)',
        brand: '0 4px 14px 0 rgba(83,2,224,0.35)',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'spin-slow': 'spin 2s linear infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: 0 }, to: { opacity: 1 } },
      },
    },
  },
  plugins: [],
}
