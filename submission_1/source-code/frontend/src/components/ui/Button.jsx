/**
 * Button — API unchanged.
 * variant: primary | secondary | success | danger | warning | ghost | indigo
 * size:    sm | md | lg
 */

const variantClasses = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost: "btn-ghost",
  success: "btn-tone [--tone:var(--t-success)]",
  danger: "btn-tone [--tone:var(--t-danger)]",
  warning: "btn-tone [--tone:var(--t-warn)]",
  indigo: "btn-tone [--tone:var(--t-violet)]",
};

const sizeClasses = {
  sm: "px-3 py-1.5 text-xs min-h-9 rounded-xl",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-2.5 text-sm min-h-12 rounded-2xl",
};

function Button({
  as: Component = "button",
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...props
}) {
  return (
    <Component
      className={[
        "btn",
        variantClasses[variant] || variantClasses.primary,
        sizeClasses[size] || sizeClasses.md,
        className,
      ].join(" ")}
      {...props}
    >
      <span className="relative z-10 inline-flex items-center gap-2">{children}</span>
    </Component>
  );
}

export default Button;
