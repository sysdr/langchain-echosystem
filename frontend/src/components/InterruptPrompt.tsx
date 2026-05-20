import "./InterruptPrompt.css";

export type InterruptPayload = {
  tool: string;
  description: string;
  interrupt_id?: string | null;
};

type Props = {
  interrupt: InterruptPayload;
  onApprove: () => void;
  onReject: () => void;
  busy: boolean;
};

export default function InterruptPrompt({
  interrupt,
  onApprove,
  onReject,
  busy,
}: Props) {
  return (
    <div className="interrupt-overlay" role="dialog" aria-labelledby="hitl-title">
      <div className="interrupt-card">
        <h2 id="hitl-title">Approve tool call?</h2>
        <p className="interrupt-tool">
          Tool: <strong>{interrupt.tool}</strong>
        </p>
        <pre className="interrupt-detail">{interrupt.description}</pre>
        <div className="interrupt-actions">
          <button
            type="button"
            className="secondary"
            onClick={onReject}
            disabled={busy}
          >
            Reject
          </button>
          <button
            type="button"
            className="primary"
            onClick={onApprove}
            disabled={busy}
          >
            {busy ? "Resuming…" : "Approve"}
          </button>
        </div>
      </div>
    </div>
  );
}
