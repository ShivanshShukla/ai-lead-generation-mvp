import { NavLink } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";

const navGroups = [
  {
    label: "Overview",
    items: [
      {
        to: "/",
        label: "Dashboard",
        icon: "M4 5.5A1.5 1.5 0 0 1 5.5 4h3A1.5 1.5 0 0 1 10 5.5v3A1.5 1.5 0 0 1 8.5 10h-3A1.5 1.5 0 0 1 4 8.5v-3Zm10 0A1.5 1.5 0 0 1 15.5 4h3A1.5 1.5 0 0 1 20 5.5v3a1.5 1.5 0 0 1-1.5 1.5h-3A1.5 1.5 0 0 1 14 8.5v-3ZM4 15.5A1.5 1.5 0 0 1 5.5 14h3a1.5 1.5 0 0 1 1.5 1.5v3A1.5 1.5 0 0 1 8.5 20h-3A1.5 1.5 0 0 1 4 18.5v-3Zm10 0a1.5 1.5 0 0 1 1.5-1.5h3a1.5 1.5 0 0 1 1.5 1.5v3a1.5 1.5 0 0 1-1.5 1.5h-3a1.5 1.5 0 0 1-1.5-1.5v-3Z",
      },
    ],
  },
  {
    label: "Plan",
    items: [
      {
        to: "/campaigns",
        label: "Campaigns",
        icon: "M5 5.5A2.5 2.5 0 0 1 7.5 3h9A2.5 2.5 0 0 1 19 5.5v13A2.5 2.5 0 0 1 16.5 21h-9A2.5 2.5 0 0 1 5 18.5v-13ZM8 7h8M8 11h8M8 15h5",
      },
      {
        to: "/opportunities",
        label: "Opportunities",
        icon: "M12 3l1.6 5h5.2l-4.2 3 1.6 5-4.2-3-4.2 3 1.6-5-4.2-3h5.2L12 3Zm-6 16h12",
      },
    ],
  },
  {
    label: "Source",
    items: [
      {
        to: "/discovery",
        label: "Lead Discovery",
        icon: "M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v7A2.5 2.5 0 0 1 17.5 15H13l-4 5v-5H6.5A2.5 2.5 0 0 1 4 12.5v-7Zm4 2.5h8M8 11h5",
      },
      {
        to: "/leads",
        label: "Leads",
        icon: "M16 11a4 4 0 1 0-8 0m8 0a4 4 0 1 1-8 0m8 0v1a4 4 0 0 1-8 0v-1m-3 9a7 7 0 0 1 14 0",
      },
    ],
  },
  {
    label: "Engage",
    items: [
      {
        to: "/calls",
        label: "Calls",
        icon: "M6.6 4.8 9 7.2 7.5 9c.8 1.7 2.1 3 3.8 3.8l1.8-1.5 2.4 2.4c.3.3.4.8.2 1.2-.7 1.4-2.1 2.3-3.7 2.3C12.7 17.2 6.8 11.3 6.8 5c0-1.6.9-3 2.3-3.7.4-.2.9-.1 1.2.2Z",
      },
      {
        to: "/emails",
        label: "Emails",
        icon: "M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5v-9Zm2-.5 6 5 6-5",
      },
    ],
  },
  {
    label: "System",
    items: [
      {
        to: "/knowledge",
        label: "Knowledge",
        icon: "M5 5.5A2.5 2.5 0 0 1 7.5 3H20v15.5A2.5 2.5 0 0 1 17.5 21h-10A2.5 2.5 0 0 1 5 18.5v-13Zm0 0A2.5 2.5 0 0 1 7.5 8H20M9 12h7M9 15h5",
      },
      {
        to: "/settings",
        label: "Settings",
        icon: "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm8.5 3.5a8.4 8.4 0 0 0-.1-1.2l2-1.5-2-3.4-2.4 1a8.8 8.8 0 0 0-2-1.2L16.2 3h-4.4l-.4 2.3a8.8 8.8 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.5A8.4 8.4 0 0 0 7 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.4-1a8.8 8.8 0 0 0 2 1.2l.4 2.3h4.4l.4-2.3a8.8 8.8 0 0 0 2-1.2l2.4 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2Z",
      },
    ],
  },
];

function Icon({ path }) {
  return (
    <svg
      aria-hidden="true"
      className="h-[18px] w-[18px] shrink-0"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
    >
      <path d={path} />
    </svg>
  );
}

function Sidebar({ collapsed, mobileOpen, onCloseMobile, onToggleCollapse }) {
  const showLabels = !collapsed || mobileOpen;

  return (
    <aside
      className={[
        "glass fixed inset-y-0 left-0 z-50 flex w-[286px] flex-col rounded-none border-y-0 border-l-0 transition-[width,transform] duration-400 ease-spring",
        collapsed ? "lg:w-sidebar-sm" : "lg:w-sidebar",
        mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
      ].join(" ")}
    >
      {/* ---- brand ---- */}
      <div className="flex h-[72px] shrink-0 items-center justify-between gap-3 px-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="bg-accent relative flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-[13px] font-bold shadow-glow"
            style={{ color: "var(--text-on-accent)" }}
          >
            LA
            <span
              aria-hidden="true"
              className="absolute inset-0 rounded-2xl opacity-60 blur-md"
              style={{ background: "linear-gradient(135deg, rgb(var(--accent-from)), rgb(var(--accent-to)))", zIndex: -1 }}
            />
          </div>

          <AnimatePresence initial={false}>
            {showLabels && (
              <motion.div
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.2 }}
                className="min-w-0"
              >
                <p className="text-ink truncate text-sm font-semibold tracking-tight">Lead Agent</p>
                <p className="text-faint truncate text-[11px]">Outreach MVP</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <button
          type="button"
          className="btn btn-ghost hidden h-9 w-9 shrink-0 rounded-xl p-0 lg:flex"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={onToggleCollapse}
        >
          <svg viewBox="0 0 24 24" className="relative z-10 h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={collapsed ? "m9 5 7 7-7 7" : "m15 5-7 7 7 7"} />
          </svg>
        </button>

        <button
          type="button"
          className="btn btn-ghost flex h-9 w-9 shrink-0 rounded-xl p-0 lg:hidden"
          aria-label="Close navigation"
          onClick={onCloseMobile}
        >
          <svg viewBox="0 0 24 24" className="relative z-10 h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M6 6 18 18M18 6 6 18" />
          </svg>
        </button>
      </div>

      <div className="divider mx-4 shrink-0" />

      {/* ---- nav ---- */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-4">
        {navGroups.map((group) => (
          <div key={group.label} className="mb-4 last:mb-0">
            {showLabels ? (
              <p className="text-faint mb-1.5 px-3 text-eyebrow uppercase">{group.label}</p>
            ) : (
              <div className="divider mx-2 mb-2.5" />
            )}

            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  onClick={onCloseMobile}
                  title={collapsed ? item.label : undefined}
                  className={({ isActive }) =>
                    [
                      "nav-item",
                      isActive ? "nav-item-active" : "",
                      collapsed && !mobileOpen ? "lg:justify-center lg:px-0" : "",
                    ].join(" ")
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <motion.span
                          layoutId="nav-active-pill"
                          transition={{ type: "spring", stiffness: 460, damping: 38 }}
                          aria-hidden="true"
                          className="bg-accent-soft line-2 absolute inset-0 rounded-[inherit] border"
                        />
                      )}

                      <span
                        className={[
                          "relative z-10 transition-colors",
                          isActive ? "text-accent" : "",
                        ].join(" ")}
                      >
                        <Icon path={item.icon} />
                      </span>

                      {showLabels && <span className="relative z-10 truncate">{item.label}</span>}

                      {isActive && showLabels && (
                        <motion.span
                          layoutId="nav-active-dot"
                          transition={{ type: "spring", stiffness: 460, damping: 38 }}
                          aria-hidden="true"
                          className="bg-accent relative z-10 ml-auto h-1.5 w-1.5 rounded-full"
                        />
                      )}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* ---- footer ---- */}
      <div className="shrink-0 p-3">
        <div className={["well overflow-hidden p-3.5", collapsed && !mobileOpen ? "lg:p-2" : ""].join(" ")}>
          <div
            aria-hidden="true"
            className="h-1.5 rounded-full"
            style={{
              background:
                "linear-gradient(90deg, rgb(var(--t-success)), rgb(var(--accent-from)), rgb(var(--accent-to)))",
            }}
          />

          {showLabels && (
            <>
              <p className="text-ink mt-3 text-xs font-semibold">Manual control</p>
              <p className="text-faint mt-1 text-[11px] leading-5">
                Emails and follow-ups send only after approval.
              </p>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
