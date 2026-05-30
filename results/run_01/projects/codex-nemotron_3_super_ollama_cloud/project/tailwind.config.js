/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./chat/**/*.html",
    "./chat/**/*.js",
  ],
  theme: {
    extend: {},
  },
  safelist: [
    { pattern: /bg-(blue|gray|red)-(500|200|900)/ },
    { pattern: /text-(white|gray-(900))/ },
    { pattern: /px-3 py-2 rounded-xl max-w-\[80%\]/ },
    { pattern: /self-(end|start)/ },
    { pattern: /message-(user|assistant|error)/ },
    { pattern: /flex-1/ },
    { pattern: /px-4/ },
    { pattern: /py-2/ },
    { pattern: /border/ },
    { pattern: /focus:/ },
    { pattern: /hover:/ },
  ],
  plugins: [],
}
