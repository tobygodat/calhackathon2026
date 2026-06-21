/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Design tokens — Research Dashboard handoff
      colors: {
        navy: "#1a2836", // nav bar bg + body text
        "navy-mid": "#2c3e4d", // nav active state
        steel: "#93a6b2", // nav link rest
        ice: "#B7C9D9", // search pill rest text
        "pale-ice": "#EAF1EE", // hover text on dark bg
        "page-bg": "#ECF3EF", // main content bg
        coral: "#c84858", // contradiction accent
        amber: "#c07828", // knowledge gap accent
        teal: "#287858", // reinforcement accent
        violet: "#7848b8", // open question accent
      },
      fontFamily: {
        serif: ["Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
