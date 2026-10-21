import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { X } from "lucide-react";

export function Field({
  label,
  name,
  value,
  type = "text",
  required = true,
  hint,
  min,
  max,
}: {
  label: string;
  name: string;
  value?: string | number;
  type?: string;
  required?: boolean;
  hint?: string;
  min?: string | number;
  max?: string | number;
}) {
  const id = useId();
  return (
    <label className="field">
      <span id={id + "-label"}>{label}</span>
      <input
        aria-labelledby={id + "-label"}
        aria-describedby={hint ? id + "-hint" : undefined}
        name={name}
        defaultValue={value}
        type={type}
        required={required}
        min={min}
        max={max}
        inputMode={
          name.includes("amount") || name.includes("balance")
            ? "decimal"
            : undefined
        }
        maxLength={type === "text" ? 120 : undefined}
      />
      {hint && <small id={id + "-hint"}>{hint}</small>}
    </label>
  );
}
export function Select({
  label,
  name,
  children,
  value,
}: {
  label: string;
  name: string;
  children: ReactNode;
  value?: string | number;
}) {
  const id = useId();
  return (
    <label className="field">
      <span id={id}>{label}</span>
      <select aria-labelledby={id} name={name} defaultValue={value} required>
        {children}
      </select>
    </label>
  );
}
export function ActionForm({
  children,
  onSave,
  submit = "Enregistrer",
  onCancel,
}: {
  children: ReactNode;
  onSave: (data: FormData) => Promise<unknown>;
  submit?: string;
  onCancel?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  async function handle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await onSave(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={handle}>
      {error && (
        <div
          className="notice danger"
          role="alert"
          ref={errorRef}
          tabIndex={-1}
        >
          {error}
        </div>
      )}
      <fieldset disabled={busy}>
        {children}
        <div className="form-actions">
          {onCancel && (
            <button type="button" onClick={onCancel}>
              Annuler
            </button>
          )}
          <button className="primary" disabled={busy}>
            {busy ? "Enregistrement…" : submit}
          </button>
        </div>
      </fieldset>
    </form>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      aria-labelledby="dialog-title"
      className={wide ? "dialog-wide" : undefined}
    >
      <div className="dialog-heading">
        <h2 id="dialog-title">{title}</h2>
        <button className="icon-button" aria-label="Fermer" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
