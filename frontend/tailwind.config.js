/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Shared with the terminal renderer: near-monochrome on charcoal with a
        // single soft champagne accent. No rainbows.
        ink: "#ecedf0", // primary text
        soft: "#a2a7b0", // secondary text
        muted: "#6a707a", // labels / tertiary
        faint: "#454a53", // dim hints
        line: "#2a2e36", // borders / dividers
        accent: {
          DEFAULT: "#c9b68c", // the single accent — soft champagne
          hi: "#e6d9b0", // light gold (sheen highlight)
          lo: "#a68f63", // deep gold (sheen low)
        },
        rail: "#5a4f38", // dim gold thread
        ok: "#8fb08a", // muted sage (success)
        warn: "#cbae74", // muted amber (warning)
        err: "#c58a8a", // muted rose (error)
        surface: {
          700: "#1c2333",
          800: "#141a28",
          850: "#0f1420",
          900: "#0a0e1a",
          950: "#070a12",
        },
      },
      fontFamily: {
        // The dashboard leans mono like the terminal; Inter carries prose only.
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px -6px rgba(201, 182, 140, 0.30)",
        card: "0 12px 40px -20px rgba(0, 0, 0, 0.7)",
      },
      backgroundImage: {
        // Warm gold foil — a narrow champagne sheen, not a rainbow.
        "gold-foil": "linear-gradient(120deg, #e6d9b0 0%, #c9b68c 50%, #a68f63 100%)",
        "gold-radial": "radial-gradient(circle at 50% 0%, rgba(201,182,140,0.10), transparent 62%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(201,182,140,0.45)" },
          "50%": { boxShadow: "0 0 0 9px rgba(201,182,140,0)" },
        },
        sheen: {
          "0%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
          "100%": { backgroundPosition: "0% 50%" },
        },
        shimmer: {
          "0%": { transform: "translateX(-120%)" },
          "100%": { transform: "translateX(220%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s ease-out both",
        "glow-pulse": "glow-pulse 2s ease-in-out infinite",
        sheen: "sheen 7s ease infinite",
        shimmer: "shimmer 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
}
