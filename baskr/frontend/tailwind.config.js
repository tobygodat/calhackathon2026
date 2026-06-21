/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Design tokens — Research Tool handoff (dark monochrome palette)
      colors: {
        bg: "#16181b", // page + nav background
        surface: "#1c1e22", // inputs, dropzone, file chips
        "surface-hover": "#212429", // field focus / dropzone drag bg
        divider: "#2c2f33", // nav bottom border, section dividers
        "field-border": "#34383d", // inputs, chips
        "muted-border": "#3a3e44", // dropzone dashed, cancel button
        "step-ring": "#5a5e64", // step number circle border
        "faint-text": "#7a7e85", // file size
        "muted-text": "#9498a0", // nav rest, helper / subtitle text
        "secondary-text": "#b0b3b8", // descriptions, search pill rest
        "primary-text": "#f2f2f2", // headings, active nav, body
        // Accent colours (dashboard cards only)
        coral: "#e0556a", // contradiction published
        amber: "#d8902f", // knowledge gap filled
        teal: "#2f9a6f", // previous finding reinforced
        violet: "#946ad6", // answer to open question
      },
      fontFamily: {
        sans: ["'Hanken Grotesk'", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
