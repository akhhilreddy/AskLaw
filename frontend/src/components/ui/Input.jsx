function Input({
  label,
  type = "text",
  name,
  value,
  onChange,
  placeholder,
}) {
  return (
    <div className="mb-6">
      <label
        htmlFor={name}
        className="mb-3 block text-sm font-medium text-zinc-300"
      >
        {label}
      </label>

      <input
        id={name}
        name={name}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete="off"
        className="
          w-full
          rounded-2xl
          border
          border-zinc-700
          bg-black
          px-6
          py-[18px]
          text-base
          text-white
          placeholder:text-zinc-500
          placeholder:font-normal
          outline-none
          transition-all
          duration-200
          focus:border-white
        "
      />
    </div>
  );
}

export default Input;