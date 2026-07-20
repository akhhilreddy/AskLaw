function Button({
  children,
  type = "button",
  ...props
}) {
  return (
    <button
      type={type}
      {...props}
      className="
      w-full
      rounded-full
      bg-white
      py-4
      text-black
      font-medium
      transition
      hover:bg-zinc-200
      "
    >
      {children}
    </button>
  );
}

export default Button;