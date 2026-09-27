/**
 * Card — API unchanged (children, className, padded).
 * `interactive` is optional and adds the hover lift.
 */
function Card({ children, className = "", padded = true, interactive = false }) {
  return (
    <section
      className={[
        "glass rounded-panel",
        interactive ? "glass-hover" : "",
        padded ? "p-4 sm:p-5 lg:p-6" : "",
        className,
      ].join(" ")}
    >
      {children}
    </section>
  );
}

export default Card;
