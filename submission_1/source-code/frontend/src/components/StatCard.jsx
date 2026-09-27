import { useEffect, useRef, useState } from "react";
import { motion, useInView } from "framer-motion";

/**
 * StatCard — API unchanged (title, value, eyebrow, tone, helper).
 * tone: primary | accent | success | warning | danger | neutral
 */

const toneVar = {
  primary: "var(--accent-from)",
  accent: "var(--accent-to)",
  success: "var(--t-success)",
  warning: "var(--t-warn)",
  danger: "var(--t-danger)",
  neutral: "var(--t-neutral)",
};

const toneIcon = {
  primary: "M3 17.5 9 11l4 4 8-8M21 7v5M21 7h-5",
  accent: "M4 19V9M10 19V4M16 19v-7M22 19H2",
  success: "M20 6 9 17l-5-5",
  warning: "M12 8.5v4.5M12 16.5v.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  danger: "M12 8.5v4.5M12 16.5v.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  neutral: "M4 6h16M4 12h16M4 18h10",
};

/** Splits "1,284" or "12.5%" into an animatable number plus its decoration. */
function parseValue(raw) {
  const text = String(raw ?? "");
  const match = text.match(/^(\D*?)(-?[\d,]*\.?\d+)(.*)$/);

  if (!match) {
    return null;
  }

  const numeric = Number(match[2].replace(/,/g, ""));

  if (!Number.isFinite(numeric)) {
    return null;
  }

  const decimals = (match[2].split(".")[1] || "").length;

  return { prefix: match[1], numeric, suffix: match[3], decimals, grouped: match[2].includes(",") };
}

function CountUp({ value }) {
  const parsed = parseValue(value);
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const [display, setDisplay] = useState(() => (parsed ? 0 : null));

  useEffect(() => {
    if (!parsed || !inView) {
      return undefined;
    }

    const duration = 900;
    const start = performance.now();
    let frame = 0;

    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      // easeOutExpo — fast then settles, reads as "snappy"
      const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      setDisplay(parsed.numeric * eased);

      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, parsed?.numeric]);

  if (!parsed) {
    return <span ref={ref}>{value}</span>;
  }

  const shown = (display ?? parsed.numeric).toLocaleString(undefined, {
    minimumFractionDigits: parsed.decimals,
    maximumFractionDigits: parsed.decimals,
    useGrouping: parsed.grouped,
  });

  return (
    <span ref={ref}>
      {parsed.prefix}
      {shown}
      {parsed.suffix}
    </span>
  );
}

function StatCard({ title, value, eyebrow, tone = "primary", helper }) {
  const accent = toneVar[tone] || toneVar.primary;

  return (
    <motion.div
      whileHover={{ y: -5 }}
      transition={{ type: "spring", stiffness: 380, damping: 26 }}
      style={{ "--tone": accent }}
      className="glass rounded-panel group relative overflow-hidden p-5"
    >
      {/* tone wash that intensifies on hover */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full opacity-40 blur-2xl transition-opacity duration-500 group-hover:opacity-80"
        style={{ background: "rgb(var(--tone) / 0.5)" }}
      />

      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          {eyebrow && <p className="text-faint mb-2 text-eyebrow uppercase">{eyebrow}</p>}

          <p className="text-muted text-sm font-semibold">{title}</p>

          <h3 className="text-ink mt-2 break-words text-metric tabular-nums">
            <CountUp value={value} />
          </h3>
        </div>

        <span
          className="line-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border transition-transform duration-500 group-hover:scale-110 group-hover:rotate-6"
          style={{ backgroundColor: "rgb(var(--tone) / 0.14)", color: "rgb(var(--tone))" }}
        >
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d={toneIcon[tone] || toneIcon.primary} />
          </svg>
        </span>
      </div>

      {helper && <p className="text-faint relative mt-4 text-xs font-medium">{helper}</p>}

      {/* bottom accent rail */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-px scale-x-0 transition-transform duration-500 group-hover:scale-x-100"
        style={{ background: "linear-gradient(90deg, transparent, rgb(var(--tone)), transparent)" }}
      />
    </motion.div>
  );
}

export default StatCard;
