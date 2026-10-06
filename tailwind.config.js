/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          500: '#1a5490',
          600: '#164777',
          700: '#12395f',
        },
        ink: '#172b4d',
        canvas: '#f8fafc',
      },
      fontFamily: {
        sans: ['Cairo', 'Tajawal', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 8px 30px rgba(23, 43, 77, 0.06)',
      },
    },
  },
  plugins: [],
}
