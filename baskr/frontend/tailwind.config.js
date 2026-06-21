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
        teal: "#287858", // reinforcement accent + Lab Context accent green
        violet: "#7848b8", // open question accent
        // Lab Context page tokens (settings handoff)
        "sidebar-bg": "#E0EDE7", // left section nav
        "sidebar-hover": "#D2E2DA", // nav item hover
        "field-bg": "#F3F8F5", // textareas, dropzone
        "slate-text": "#3c4c44", // nav item rest
        "muted-text": "#5a6b62", // helper / subtitle text
        "faint-text": "#8a9aa6", // file size, placeholder
        divider: "#D4E1DB", // section dividers
        "field-border": "#CFE0D8", // textarea / sidebar borders
        "dropzone-border": "#9fb6ab", // upload dropzone (dashed)
      },
      fontFamily: {
        serif: ["Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
