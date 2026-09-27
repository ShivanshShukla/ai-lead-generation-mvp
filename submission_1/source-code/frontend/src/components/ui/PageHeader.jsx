function PageHeader({ title, description, eyebrow, actions }) {
  return (
    <div className="animate-rise mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        {eyebrow && (
          <p className="text-accent mb-2 text-eyebrow uppercase">{eyebrow}</p>
        )}

        <h2 className="text-ink text-display-sm">
          {title}
        </h2>

        {description && (
          <p className="text-muted mt-2.5 max-w-3xl text-sm leading-6">{description}</p>
        )}
      </div>

      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export default PageHeader;
