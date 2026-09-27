/** @type {import('tailwindcss').Config} */

/**
 * Midnight Aurora.
 *
 * Every colour here resolves to a CSS variable defined in `src/index.css`,
 * so a single `.light` / `.dark` class on <html> repaints the whole app.
 * Never hard-code a hex in a component — reach for a token below, or one of
 * the `.glass` / `.tone-*` / `.btn-*` component classes.
 */

const channel = (name) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  darkMode: ["class", "html.dark"],
  theme: {
    extend: {
      colors: {
        /* --- canvas ------------------------------------------------------ */
        canvas: {
          0: "var(--bg-0)",
          1: "var(--bg-1)",
          2: "var(--bg-2)",
        },

        /* Semantic tones are NOT declared here on purpose — they live as
           `text-success` / `bg-success-soft` / `border-success-soft` utilities
           in index.css so a Tailwind colour of the same name can't shadow
           them. See the tone block in src/index.css. */

        /* --- aurora ------------------------------------------------------ */
        bloom: {
          1: channel("--bloom-1"),
          2: channel("--bloom-2"),
          3: channel("--bloom-3"),
        },

        /* --- legacy names, remapped so any missed class still themes ----- */
        primary: {
          50: "rgb(var(--accent-from) / 0.10)",
          100: "rgb(var(--accent-from) / 0.18)",
          500: channel("--accent-from"),
          600: channel("--accent-from"),
          700: channel("--accent-from"),
          950: "var(--bg-1)",
        },
        accent: {
          50: "rgb(var(--accent-to) / 0.10)",
          100: "rgb(var(--accent-to) / 0.18)",
          500: channel("--accent-to"),
          600: channel("--accent-to"),
          700: channel("--accent-to"),
        },
        warning: {
          50: "rgb(var(--t-warn) / 0.10)",
          100: "rgb(var(--t-warn) / 0.20)",
          500: channel("--t-warn"),
          700: channel("--t-warn"),
        },
        neutral: {
          50: "var(--glass-sunk)",
          100: "var(--glass-1)",
          200: "var(--line-1)",
          500: "var(--text-3)",
          700: "var(--text-2)",
          900: "var(--text-1)",
          950: "var(--text-1)",
        },
      },

      borderRadius: {
        component: "1rem",
        panel: "1.5rem",
        hero: "2rem",
      },

      boxShadow: {
        soft: "var(--sh-1)",
        lift: "var(--sh-2)",
        deep: "var(--sh-3)",
        glow: "var(--sh-glow)",
      },

      backdropBlur: {
        glass: "22px",
      },

      fontSize: {
        "display-lg": ["clamp(2.25rem, 1.6rem + 2.6vw, 3.5rem)", { lineHeight: "1.05", fontWeight: "700", letterSpacing: "-0.03em" }],
        "display-sm": ["clamp(1.6rem, 1.3rem + 1.2vw, 2.125rem)", { lineHeight: "1.15", fontWeight: "700", letterSpacing: "-0.025em" }],
        metric: ["clamp(1.75rem, 1.45rem + 1vw, 2.25rem)", { lineHeight: "1.1", fontWeight: "700", letterSpacing: "-0.03em" }],
        eyebrow: ["0.6875rem", { lineHeight: "1rem", fontWeight: "700", letterSpacing: "0.14em" }],
      },

      spacing: {
        section: "1.5rem",
        "section-lg": "2rem",
        sidebar: "17rem",
        "sidebar-sm": "5.5rem",
      },

      transitionTimingFunction: {
        spring: "cubic-bezier(0.22, 1, 0.36, 1)",
      },

      keyframes: {
        rise: {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "none" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-in-left": {
          from: { opacity: "0", transform: "translateX(-14px)" },
          to: { opacity: "1", transform: "none" },
        },
      },

      animation: {
        rise: "rise 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 0.4s ease both",
        "slide-in-left": "slide-in-left 0.4s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
};
