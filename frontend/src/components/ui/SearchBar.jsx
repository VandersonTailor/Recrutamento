import { Search } from 'lucide-react';

function SearchBar({ value, onChange, placeholder = 'Buscar...' }) {
  return (
    <label className="flex w-full items-center gap-2 rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-700/30">
      <Search size={16} className="text-slatewarm-300" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full bg-transparent text-sm text-slatewarm-50 outline-none placeholder:text-slatewarm-400"
      />
    </label>
  );
}

export default SearchBar;
