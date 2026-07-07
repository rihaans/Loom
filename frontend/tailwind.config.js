/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Loom brand — the cyan→magenta "weave" (shared with the terminal UI).
        loom: {
          cyan: "#00d9ff",
          sky: "#33cdff",
          violet: "#7ab9ff",
          orchid: "#c79bff",
          pink: "#f176f3",
          magenta: "#ff5fd2",
        },
        // Per-agent accents — kept in lockstep with the CLI renderer.
        agent: {
          pm: "#00d9ff",
          architect: "#ff5fd2",
          frontend: "#88c0d0",
          backend: "#a3be8c",
          reviewer: "#d08770",
          qa: "#ebcb8b",
          devops: "#b48ead",
        },
        primary: {
          50: "#f0f9ff",
          100: "#e0f2fe",
          400: "#38bdf8",
          500: "#00d9ff",
          600: "#0284c7",
          700: "#0369a1",
        },
        surface: {
          50: "#f8fafc",
          100: "#f1f5f9",
          700: "#1c2333",
          800: "#141a28",
          850: "#0f1420",
          900: "#0a0e1a",
          950: "#070a12",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px -4px rgba(0, 217, 255, 0.45)",
        "glow-magenta": "0 0 24px -4px rgba(255, 95, 210, 0.45)",
        card: "0 10px 40px -12px rgba(0, 0, 0, 0.6)",
      },
      backgroundImage: {
        "loom-gradient": "linear-gradient(120deg, #00d9ff 0%, #7ab9ff 45%, #ff5fd2 100%)",
        "loom-radial": "radial-gradient(circle at 50% 0%, rgba(0,217,255,0.12), transparent 60%)",
      },
      keyframes: {
        "gradient-x": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(0,217,255,0.5)" },
          "50%": { boxShadow: "0 0 0 10px rgba(0,217,255,0)" },
        },
        shimmer: {
          "0%": { transform: "translateX(-120%)" },
          "100%": { transform: "translateX(220%)" },
        },
        aurora: {
          "0%, 100%": { transform: "translate(0,0) scale(1)" },
          "33%": { transform: "translate(4%, -3%) scale(1.08)" },
          "66%": { transform: "translate(-3%, 4%) scale(0.96)" },
        },
      },
      animation: {
        "gradient-x": "gradient-x 6s ease infinite",
        "fade-up": "fade-up 0.5s ease-out both",
        float: "float 4s ease-in-out infinite",
        "glow-pulse": "glow-pulse 2s ease-in-out infinite",
        shimmer: "shimmer 1.8s ease-in-out infinite",
        aurora: "aurora 18s ease-in-out infinite",
      },
    },
  },
  plugins: [],
}
