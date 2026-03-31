function SectionCard({ title, subtitle, children, action }) {
  return (
    <section className="card-surface p-4 md:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slatewarm-50">{title}</h2>
          {subtitle && <p className="text-sm text-slatewarm-300">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export default SectionCard;
