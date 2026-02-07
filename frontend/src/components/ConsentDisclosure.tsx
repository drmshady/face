/** ConsentDisclosure component per T018a — constitution Principle II. */

interface ConsentDisclosureProps {
  onConsent: () => void;
  hasConsented: boolean;
}

export function ConsentDisclosure({
  onConsent,
  hasConsented,
}: ConsentDisclosureProps) {
  if (hasConsented) return null;

  return (
    <div
      style={{
        border: "1px solid #ccc",
        borderRadius: "8px",
        padding: "24px",
        margin: "16px 0",
        backgroundColor: "#f9f9f9",
      }}
    >
      <h3 style={{ marginTop: 0 }}>Before We Analyze Your Photos</h3>

      <section>
        <h4>What will be analyzed</h4>
        <ul>
          <li>Facial landmark detection (eyes, nose, ears)</li>
          <li>Bite fork marker detection</li>
          <li>Reference line computation for dental alignment</li>
        </ul>
      </section>

      <section>
        <h4>What data is collected</h4>
        <ul>
          <li>Face photos you upload</li>
          <li>Basic device information (screen size, browser)</li>
        </ul>
      </section>

      <section>
        <h4>How your data is handled</h4>
        <ul>
          <li>All processing happens in-memory only</li>
          <li>No data is saved to disk or any database</li>
          <li>No data is shared with third parties</li>
          <li>Data is automatically deleted when your session ends</li>
        </ul>
      </section>

      <button
        onClick={onConsent}
        style={{
          marginTop: "16px",
          padding: "12px 24px",
          fontSize: "16px",
          backgroundColor: "#2563eb",
          color: "white",
          border: "none",
          borderRadius: "6px",
          cursor: "pointer",
        }}
      >
        I Understand &amp; Consent
      </button>
    </div>
  );
}
