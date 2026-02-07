/** ConfidenceBadge component: colored score display (T039). */

interface ConfidenceBadgeProps {
  confidence: number;
  label?: string;
}

export function ConfidenceBadge({ confidence, label }: ConfidenceBadgeProps) {
  const color = confidence >= 0.8 ? "#16a34a" : confidence >= 0.5 ? "#ca8a04" : "#dc2626";
  const bg = confidence >= 0.8 ? "#dcfce7" : confidence >= 0.5 ? "#fef9c3" : "#fee2e2";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "2px 8px",
        borderRadius: "12px",
        fontSize: "12px",
        fontWeight: "bold",
        color,
        backgroundColor: bg,
      }}
    >
      {label && <span>{label}</span>}
      {(confidence * 100).toFixed(0)}%
    </span>
  );
}
