import { useEffect, useId, useRef } from "react";

export default function ComplaintConfirmation({ title, children, confirmLabel, onConfirm, onCancel, disabled = false }) {
  const titleId = useId();
  const cancelRef = useRef(null);
  useEffect(() => { cancelRef.current?.focus(); }, []);
  return <section className="complaint-confirmation" role="region" aria-labelledby={titleId}>
    <h3 id={titleId}>{title}</h3>
    {children}
    <div className="complaint-actions">
      <button ref={cancelRef} type="button" disabled={disabled} onClick={onCancel}>Cancel</button>
      <button type="button" disabled={disabled} onClick={onConfirm}>{confirmLabel}</button>
    </div>
  </section>;
}
