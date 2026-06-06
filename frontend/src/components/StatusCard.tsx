interface StatusCardProps {
  label: string;
  value: string | number;
  hint?: string;
}

export function StatusCard({ label, value, hint }: StatusCardProps) {
  return (
    <div className="status-card">
      <div className="status-card__label">{label}</div>
      <div className="status-card__value">{value}</div>
      {hint ? <div className="status-card__hint">{hint}</div> : null}
    </div>
  );
}
