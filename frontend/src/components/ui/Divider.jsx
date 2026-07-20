function Divider() {
  return (
    <div className="my-8 flex items-center gap-4">
      <div className="h-px flex-1 bg-zinc-800" />

      <span className="text-xs uppercase tracking-widest text-zinc-500">
        OR
      </span>

      <div className="h-px flex-1 bg-zinc-800" />
    </div>
  );
}

export default Divider;