function Skeleton({ className = "" }) {
  return <div aria-hidden="true" className={["shimmer rounded-2xl", className].join(" ")} />;
}

export default Skeleton;
