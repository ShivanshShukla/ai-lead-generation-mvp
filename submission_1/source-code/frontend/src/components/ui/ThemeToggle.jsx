import { motion } from "framer-motion";
import { useTheme } from "../../theme/useTheme";

function ThemeToggle({ className = "" }) {
  const { isDark, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Light mode" : "Dark mode"}
      className={[
        "glass glass-hover relative flex h-10 w-[4.25rem] shrink-0 items-center rounded-full p-1",
        className,
      ].join(" ")}
    >
      <motion.span
        layout
        transition={{ type: "spring", stiffness: 500, damping: 32 }}
        className={[
          "bg-accent flex h-8 w-8 items-center justify-center rounded-full",
          isDark ? "ml-0" : "ml-auto",
        ].join(" ")}
        style={{ color: "var(--text-on-accent)" }}
      >
        <motion.svg
          key={isDark ? "moon" : "sun"}
          initial={{ rotate: -90, opacity: 0, scale: 0.6 }}
          animate={{ rotate: 0, opacity: 1, scale: 1 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          viewBox="0 0 24 24"
          className="h-[18px] w-[18px]"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {isDark ? (
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
          ) : (
            <>
              <circle cx="12" cy="12" r="4.2" />
              <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" />
            </>
          )}
        </motion.svg>
      </motion.span>
    </button>
  );
}

export default ThemeToggle;
