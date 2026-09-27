function EmptyState({ title, description, children, icon = null }) {
  return (
    <div className="animate-rise rounded-panel line-1 surface-sunk border border-dashed px-6 py-10 text-center">
      <div className="bg-accent-soft line-1 mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border">
        {icon || (
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className="text-accent h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.6-3.6" />
          </svg>
        )}
      </div>

      <h3 className="text-ink text-base font-semibold tracking-tight">{title}</h3>

      {description && (
        <p className="text-muted mx-auto mt-2 max-w-md text-sm leading-6">{description}</p>
      )}

      {children && <div className="mt-5 flex flex-wrap justify-center gap-2">{children}</div>}
    </div>
  );
}

export default EmptyState;
