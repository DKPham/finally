import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#080b10",
          900: "#0d1117",
          850: "#11161e",
          800: "#161b24",
          700: "#1f2632",
          600: "#2a3240",
          500: "#3a4456",
        },
        mute: { 400: "#8b95a7", 500: "#6b7588", 600: "#4f586a" },
        accent: { DEFAULT: "#ecad0a", dim: "#a37806" },
        primary: { DEFAULT: "#209dd7", dim: "#16719b" },
        secondary: { DEFAULT: "#753991", bright: "#8e48b0" },
        up: { DEFAULT: "#22c55e", dim: "#15803d" },
        down: { DEFAULT: "#ef4444", dim: "#b91c1c" },
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "JetBrains Mono",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      fontSize: { "2xs": ["0.65rem", { lineHeight: "0.9rem" }] },
    },
  },
  plugins: [],
};

export default config;
