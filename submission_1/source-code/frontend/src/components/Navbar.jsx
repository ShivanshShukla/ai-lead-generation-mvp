import ThemeToggle from "./ui/ThemeToggle";

function Navbar({ pageTitle, collapsed, onMenuClick, onCollapseClick }) {
  return (
    <header className="glass sticky top-0 z-30 rounded-none border-x-0 border-t-0 px-4 sm:px-5 lg:px-8">
      <div className="mx-auto flex h-[72px] w-full max-w-[1440px] items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            className="btn btn-secondary h-10 w-10 shrink-0 rounded-2xl p-0 lg:hidden"
            aria-label="Open navigation"
            onClick={onMenuClick}
          >
            <svg viewBox="0 0 24 24" className="relative z-10 h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>

          <button
            type="button"
            className="btn btn-secondary hidden h-10 w-10 shrink-0 rounded-2xl p-0 lg:flex"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={onCollapseClick}
          >
            <svg viewBox="0 0 24 24" className="relative z-10 h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d={collapsed ? "M4 6h16M4 12h10M4 18h16" : "M4 6h16M10 12h10M4 18h16"} />
            </svg>
          </button>

          <div className="min-w-0">
            <p className="text-faint hidden truncate text-[11px] font-semibold uppercase tracking-[0.14em] sm:block">
              AI Lead Generation
            </p>
            <h1 className="text-ink truncate text-lg font-semibold tracking-tight sm:text-xl">
              {pageTitle}
            </h1>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <div className="tone tone-success hidden px-3 py-1.5 md:inline-flex">
            <span aria-hidden="true" className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-70" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
            </span>
            MVP Live
          </div>

          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

export default Navbar;
