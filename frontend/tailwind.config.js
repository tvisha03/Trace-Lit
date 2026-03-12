/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ['DM Serif Display', 'Georgia', 'serif'],
        mono:  ['DM Mono', 'monospace'],
        sans:  ['DM Sans', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Backgrounds
        'tl-bg':  '#080808',
        'tl-s1':  '#0f0f0f',
        'tl-s2':  '#141414',
        'tl-s3':  '#1a1a1a',
        'tl-s4':  '#212121',
        'tl-s5':  '#2a2a2a',
        // Borders
        'tl-b1':  '#222222',
        'tl-b2':  '#2e2e2e',
        'tl-b3':  '#3a3a3a',
        // Text
        'tl-t1':  '#ececec',
        'tl-t2':  '#aaaaaa',
        'tl-t3':  '#666666',
        'tl-t4':  '#444444',
        // Accent
        'tl-gold': '#c9a96e',
        // Confidence
        'tl-hi':   '#34d399',
        'tl-med':  '#fbbf24',
        'tl-low':  '#f87171',
        'tl-info': '#60a5fa',
      },
    },
  },
  plugins: [],
}
