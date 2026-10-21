import { useEffect, useState } from "react";
import { Landmark, ShieldCheck } from "lucide-react";
import { api } from "./api";
import { ActionForm } from "./components";
import {
  AccountChoices,
  ConfigurationHelp,
  type BankChoice,
  type BankStatus,
} from "./BankingPanel";
import { cents, decimal } from "./money";

const localToday = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Paris",
}).format(new Date());

export default function Onboarding({
  onSave,
}: {
  onSave: (body: unknown) => Promise<void>;
}) {
  const [status, setStatus] = useState<BankStatus | null>(null);
  const [choices, setChoices] = useState<BankChoice[] | null>(null);
  const [selection, setSelection] = useState<{
    charges: BankChoice;
    expenses: BankChoice | null;
  } | null>(null);
  const [form, setForm] = useState({
    name: "Compte joint CHARGES",
    balance: "",
    balance_date: localToday,
    expenses_name: "Compte joint DÉPENSES",
    expenses_balance: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    void api<BankStatus>("/bank/status")
      .then(setStatus)
      .catch((e) => setError(e.message));
  }, []);
  async function discover() {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ accounts: BankChoice[] }>(
        "/bank/discover",
        {},
        "POST",
      );
      setChoices(result.accounts);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="entry onboarding-entry">
      <div className="entry-brand">
        <ShieldCheck />
        BudgetWard
      </div>
      <section className="entry-panel">
        <span className="eyebrow">PREMIER DÉMARRAGE</span>
        <h1>Poser le point de départ</h1>
        <p>
          Choisissez les comptes du foyer et confirmez leur solde actuel. Vous
          ajouterez ensuite les charges et les budgets.
        </p>
        {status && !selection && (
          <div className="onboarding-bank">
            {status.credentials_configured && status.module_installed ? (
              <>
                <button
                  type="button"
                  onClick={() => void discover()}
                  disabled={busy}
                >
                  <Landmark size={17} />
                  {busy
                    ? "Lecture des comptes…"
                    : "Choisir mes comptes dans la banque"}
                </button>
                <p className="dialog-copy">
                  {status.demo
                    ? "Comptes fictifs de démonstration."
                    : "Les comptes compatibles sont proposés sans être sélectionnés automatiquement."}{" "}
                  Vous pouvez aussi remplir les champs ci-dessous et continuer
                  avec des relevés CSV.
                </p>
              </>
            ) : (
              <ConfigurationHelp status={status} />
            )}
          </div>
        )}
        {error && (
          <div className="notice danger" role="alert">
            {error}
          </div>
        )}
        {choices && !selection && (
          <div className="setup-bank-choices">
            <h2>Quels comptes voulez-vous suivre ?</h2>
            {choices.length ? (
              <AccountChoices
                key={choices.map((a) => a.choice_id).join()}
                accounts={choices}
                submit="Utiliser ces comptes"
                onSave={async (charges, expenses) => {
                  setSelection({ charges, expenses });
                  setChoices(null);
                  setForm((current) => ({
                    ...current,
                    name: charges.name,
                    balance: decimal(charges.balance_cents),
                    balance_date: localToday,
                    ...(expenses
                      ? {
                          expenses_name: expenses.name,
                          expenses_balance: decimal(expenses.balance_cents),
                        }
                      : {}),
                  }));
                }}
              />
            ) : (
              <p className="dialog-copy">
                Aucun compte courant en euros disponible. Continuez par saisie
                manuelle ou avec le CSV.
              </p>
            )}
          </div>
        )}
        {selection && (
          <div className="notice">
            <div>
              <strong>Comptes bancaires choisis</strong>
              <p className="notice-paragraph">
                CHARGES : {selection.charges.name} ·{" "}
                {selection.charges.masked_iban}
                {selection.expenses && (
                  <>
                    <br />
                    DÉPENSES : {selection.expenses.name} ·{" "}
                    {selection.expenses.masked_iban}
                  </>
                )}
              </p>
              <button
                type="button"
                className="text-button"
                onClick={() => {
                  setSelection(null);
                  setChoices(null);
                }}
              >
                Modifier le choix, conserver la saisie
              </button>
            </div>
          </div>
        )}
        <ActionForm
          submit="Créer le suivi"
          onSave={(f) =>
            onSave({
              name: form.name,
              balance_cents: cents(form.balance),
              balance_date: form.balance_date,
              expenses_name: form.expenses_name,
              expenses_balance_cents: cents(form.expenses_balance),
              charges_choice_id: selection?.charges.choice_id || null,
              expenses_choice_id: selection?.expenses?.choice_id || null,
              bank_confirmed: !!f.get("bank_confirmed"),
            })
          }
        >
          <label className="field">
            <span>Nom du compte CHARGES</span>
            <input
              name="name"
              value={form.name}
              maxLength={120}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </label>
          <div className="form-grid">
            <label className="field">
              <span>Solde constaté (€)</span>
              <input
                name="balance"
                value={form.balance}
                inputMode="decimal"
                onChange={(e) => setForm({ ...form, balance: e.target.value })}
                required
              />
              <small>Le découvert peut être saisi avec un signe −.</small>
            </label>
            <label className="field">
              <span>Date de ce solde</span>
              <input
                name="balance_date"
                type="date"
                value={form.balance_date}
                max={localToday}
                onChange={(e) =>
                  setForm({ ...form, balance_date: e.target.value })
                }
                required
              />
            </label>
          </div>
          <label className="field">
            <span>Nom du compte DÉPENSES</span>
            <input
              name="expenses_name"
              value={form.expenses_name}
              maxLength={120}
              onChange={(e) =>
                setForm({ ...form, expenses_name: e.target.value })
              }
              required
            />
          </label>
          <label className="field">
            <span>Solde DÉPENSES à la même date (€)</span>
            <input
              name="expenses_balance"
              value={form.expenses_balance}
              inputMode="decimal"
              onChange={(e) =>
                setForm({ ...form, expenses_balance: e.target.value })
              }
              required
            />
          </label>
          {selection && (
            <>
              <p className="dialog-copy">
                Les soldes découverts sont actuels. Si vous changez la date,
                vérifiez les soldes de cette date dans votre banque.
              </p>
              <label className="check-field bank-confirm">
                <input type="checkbox" name="bank_confirmed" required />
                Je confirme les comptes choisis, la date et les soldes de
                départ.
              </label>
            </>
          )}
        </ActionForm>
      </section>
    </div>
  );
}
