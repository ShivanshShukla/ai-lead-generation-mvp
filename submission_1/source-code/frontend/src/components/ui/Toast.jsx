const toneClasses = {
  success: "tone-block [--tone:var(--t-success)]",
  warning: "tone-block [--tone:var(--t-warn)]",
  danger: "tone-block [--tone:var(--t-danger)]",
  info: "tone-block [--tone:var(--t-info)]",
  neutral: "tone-block [--tone:var(--t-neutral)]",
};

const icons = {
  success: "M20 6 9 17l-5-5",
  warning: "M12 8v5M12 16.5v.5M10.3 3.9 2.6 17.4A1.9 1.9 0 0 0 4.3 20.3h15.4a1.9 1.9 0 0 0 1.7-2.9L13.7 3.9a1.9 1.9 0 0 0-3.4 0Z",
  danger: "M12 8v5M12 16.5v.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  info: "M12 16v-5M12 8.5v.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  neutral: "M12 16v-5M12 8.5v.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
};

function Toast({ tone = "neutral", children, className = "" }) {
  return (
    <div
      role="status"
      className={[
        "animate-rise flex items-start gap-2.5 rounded-2xl border px-4 py-3 text-sm font-medium",
        toneClasses[tone] || toneClasses.neutral,
        className,
      ].join(" ")}
    >
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="mt-0.5 h-4 w-4 shrink-0"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={icons[tone] || icons.neutral} />
      </svg>
      <span className="min-w-0 break-anywhere">{children}</span>
    </div>
  );
}

export default Toast;
