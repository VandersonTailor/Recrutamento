function Button({ children, variant = 'primary', className = '', ...props }) {
  const variants = {
    primary: 'bg-brand-500 text-white hover:bg-brand-600',
    secondary: 'bg-slatewarm-800 text-slatewarm-50 hover:bg-slatewarm-700',
    outline: 'border border-slatewarm-700 bg-slatewarm-900 text-slatewarm-50 hover:border-brand-500',
    danger: 'bg-rose-600 text-white hover:bg-rose-700',
  };

  return (
    <button
      {...props}
      className={[
        'inline-flex items-center justify-center rounded-lg px-3.5 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60',
        variants[variant],
        className,
      ].join(' ')}
    >
      {children}
    </button>
  );
}

export default Button;
