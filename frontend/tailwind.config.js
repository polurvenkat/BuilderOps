/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0E1116",
        "bg-card": "#171B21",
        "bg-card-locked": "#12151A",
        rail: "#262B33",
        "card-border": "#20242C",
        chalk: "#ECEAE3",
        "chalk-dim": "#8B8D93",
        "chalk-dimmer": "#4E525B",
        track1: "#A79AE8",
        track2: "#3FBBA0",
        track3: "#E7975C",
        gold: "#EFC24B",
      },
      fontFamily: {
        display: ["Sora", "ui-rounded", "system-ui", "sans-serif"],
        body: ["Inter", "-apple-system", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SF Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
