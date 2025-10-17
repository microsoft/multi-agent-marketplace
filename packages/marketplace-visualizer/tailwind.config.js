/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fef5fe",
          100: "#fde9fd",
          200: "#fbd4fb",
          300: "#f9b0f9",
          400: "#fb81ff", // Light end of gradient
          500: "#d440d8", // vp-c-brand-3
          600: "#c947b9", // vp-c-brand-2
          700: "#912084", // vp-c-brand-1 (primary)
          800: "#7a1b6e",
          900: "#5d1654",
        },
      },
    },
  },
  plugins: [],
};
