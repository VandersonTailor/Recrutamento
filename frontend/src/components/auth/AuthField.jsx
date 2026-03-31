function AuthField({
  icon: Icon,
  type = 'text',
  value,
  onChange,
  placeholder,
  autoComplete,
  rightAction = null,
  disabled = false,
  invalid = false,
}) {
  return (
    <label
      className={[
        'group flex items-center gap-2 rounded-xl border px-3 py-2 transition',
        invalid ? 'border-red-400/70 bg-red-500/5' : 'border-slatewarm-700 bg-slatewarm-900/80',
        disabled ? 'opacity-70' : 'focus-within:border-brand-400',
      ].join(' ')}
    >
      {Icon ? <Icon size={16} className={invalid ? 'text-red-200' : 'text-slatewarm-300'} /> : null}
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete={autoComplete}
        disabled={disabled}
        className="w-full bg-transparent text-sm text-slatewarm-50 outline-none placeholder:text-slatewarm-400"
      />
      {rightAction}
    </label>
  );
}

export default AuthField;
