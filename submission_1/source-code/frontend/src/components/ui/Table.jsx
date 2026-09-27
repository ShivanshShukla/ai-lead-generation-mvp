/**
 * Table — API unchanged (columns, children, className).
 * Wrapper handles horizontal scroll on narrow screens without clipping the
 * panel's rounded corners.
 */
function Table({ columns = [], children, className = "" }) {
  return (
    <div className={["glass rounded-panel overflow-hidden", className].join(" ")}>
      <div className="scroll-x">
        <table className="min-w-full text-left text-sm">
          {columns.length > 0 && (
            <thead className="t-head">
              <tr>
                {columns.map((column) => (
                  <th key={column} scope="col" className="line-1 border-b px-4 py-3 whitespace-nowrap">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody className="divide-line text-ink-2 divide-y">{children}</tbody>
        </table>
      </div>
    </div>
  );
}

export default Table;
