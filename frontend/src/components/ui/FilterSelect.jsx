function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className="flex min-w-[160px] flex-col gap-1">
      <span className="text-xs font-semibold uppercase tracking-wide text-slatewarm-300">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 text-sm text-slatewarm-50 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-700/30"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default FilterSelect;
