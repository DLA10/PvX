/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        t: {
          black:    '#000000',
          panel:    '#080000',
          deep:     '#0d0000',
          border:   '#4a0000',
          maroon:   '#8b0000',
          fire:     '#b22222',
          'or-dim': '#6b2500',
          'or-mid': '#cc4400',
          orange:   '#ff6600',
          bright:   '#ff8c00',
          hot:      '#ff4500',
          amber:    '#ffaa00',
          gold:     '#ffd700',
          dim:      '#3d1500',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      animation: {
        blink:       'blink 1s step-end infinite',
        'blink-slow':'blink 2s step-end infinite',
        'pulse-glow':'pulseGlow 2s ease-in-out infinite',
        scan:        'scan 6s linear infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        pulseGlow: {
          '0%, 100%': { textShadow: '0 0 6px #ff6600, 0 0 12px #ff4500' },
          '50%':      { textShadow: '0 0 12px #ff8c00, 0 0 24px #ff6600, 0 0 36px #ff4500' },
        },
        scan: {
          '0%':   { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
      },
      boxShadow: {
        'glow-or':     '0 0 8px rgba(255,102,0,0.6), 0 0 20px rgba(255,69,0,0.2)',
        'glow-maroon': '0 0 8px rgba(139,0,0,0.7), inset 0 0 8px rgba(139,0,0,0.1)',
        'glow-panel':  '0 0 1px rgba(255,102,0,0.3)',
        'bar-or':      '0 0 10px rgba(255,102,0,0.8), 0 0 20px rgba(255,69,0,0.4)',
      },
    },
  },
  plugins: [],
}
