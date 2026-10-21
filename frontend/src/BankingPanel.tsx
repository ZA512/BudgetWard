import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Landmark, RefreshCw } from "lucide-react";
import { api } from "./api";
import { ActionForm, Empty, Field } from "./components";
import { money, shortDate } from "./money";

export type BankChoice = {
  choice_id: string;
  name: string;
  masked_iban: string;
  balance_cents: number;
};
export type BankStatus = {
  demo: boolean;
  provider: string;
  credentials_configured: boolean;
  module_installed: boolean;
  running: boolean;
  pending: boolean;
  discovery_error: string | null;
  bindings: {
    account_id: number;
    role: string;
    name: string;
    masked_iban: string;
    last_attempt_at: string | null;
    last_success_at: string | null;
    error: string | null;
  }[];
};
type BankRow = {
  line: number;
  status: string;
  message: string;
  raw_label?: string;
  booking_date?: string;
  amount_cents?: number;
};
type BankPreview = {
  snapshot_id: string;
  balance_date: string;
  since: string;
  demo: boolean;
  accounts: {
    account_id: number;
    name: string;
    role: string;
    masked_iban: string;
    balance_cents: number;
    previous_balance_cents: number;
    preview: { rows: BankRow[]; counts: Record<string, number> };
  }[];
};
const localToday = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Paris",
}).format(new Date());
const timestamp = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("fr-FR", {
        dateStyle: "short",
        timeStyle: "short",
        timeZone: "Europe/Paris",
      }).format(new Date(value))
    : "Aucun";
const statusLabels: Record<string, string> = {
  NEW: "À importer",
  DUPLICATE: "Déjà présent",
  AMBIGUOUS: "À décider",
  ERROR: "Invalide",
  CONFLICT: "Conflit de référence",
};

export function AccountChoices({
  accounts,
  submit,
  onSave,
}: {
  accounts: BankChoice[];
  submit: string;
  onSave: (charges: BankChoice, expenses: BankChoice | null) => Promise<void>;
}) {
  const [charges, setCharges] = useState("");
  const [expenses, setExpenses] = useState("");
  return (
    <ActionForm
      submit={submit}
      onSave={async (form) => {
        if (!form.get("confirmed"))
          throw new Error(
            "Confirmez que les comptes choisis sont bien ceux du suivi.",
          );
        const charge = accounts.find((a) => a.choice_id === charges);
        if (!charge)
          throw new Error("Choisissez explicitement le compte CHARGES.");
        await onSave(
          charge,
          accounts.find((a) => a.choice_id === expenses) || null,
        );
      }}
    >
      <label className="field">
        <span>Compte bancaire pour CHARGES</span>
        <select
          value={charges}
          onChange={(e) => {
            setCharges(e.target.value);
            if (expenses === e.target.value) setExpenses("");
          }}
          required
        >
          <option value="" disabled>
            Choisir le compte CHARGES…
          </option>
          {accounts.map((a) => (
            <option key={a.choice_id} value={a.choice_id}>
              {a.name} · {a.masked_iban} · {money(a.balance_cents)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Compte bancaire pour DÉPENSES</span>
        <select value={expenses} onChange={(e) => setExpenses(e.target.value)}>
          <option value="">Continuer sans association DÉPENSES</option>
          {accounts
            .filter((a) => a.choice_id !== charges)
            .map((a) => (
              <option key={a.choice_id} value={a.choice_id}>
                {a.name} · {a.masked_iban} · {money(a.balance_cents)}
              </option>
            ))}
        </select>
      </label>
      <label className="check-field bank-confirm">
        <input type="checkbox" name="confirmed" required />
        Je confirme que ces comptes correspondent bien à CHARGES et DÉPENSES.
      </label>
    </ActionForm>
  );
}

export function ConfigurationHelp({ status }: { status: BankStatus }) {
  return (
    <div className="notice warning">
      <div>
        <strong>
          {!status.credentials_configured
            ? "Connexion bancaire à configurer sur le serveur"
            : "Le module bancaire doit être installé"}
        </strong>
        <p className="notice-paragraph">
          Le CSV reste utilisable. Les identifiants bancaires se configurent par
          fichiers secrets sur le serveur et ne sont jamais saisis ici.
        </p>
        <a
          href="https://github.com/ZA512/BudgetWard/blob/main/docs/WOOB.md"
          target="_blank"
          rel="noreferrer"
        >
          Ouvrir le guide de connexion bancaire
        </a>
      </div>
    </div>
  );
}

export default function BankingPanel({
  onChanged,
}: {
  onChanged: () => Promise<void>;
}) {
  const [status, setStatus] = useState<BankStatus | null>(null);
  const [choices, setChoices] = useState<BankChoice[] | null>(null);
  const [preview, setPreview] = useState<BankPreview | null>(null);
  const [decisions, setDecisions] = useState<
    Record<string, Record<string, string>>
  >({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    const [state, pending] = await Promise.all([
      api<BankStatus>("/bank/status"),
      api<BankPreview | null>("/bank/pending"),
    ]);
    setStatus(state);
    setPreview(pending);
  }, []);
  useEffect(() => {
    void load().catch((e) => setError(e.message));
  }, [load]);
  async function discover() {
    setBusy(true);
    setError("");
    setNotice("");
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
      await load().catch(() => {});
    }
  }
  if (!status)
    return (
      <div className="notice" role="status">
        {error || "Lecture de la configuration bancaire…"}
      </div>
    );
  const configured = status.credentials_configured && status.module_installed;
  const invalid = preview?.accounts.some(
    (a) => (a.preview.counts.ERROR || 0) + (a.preview.counts.CONFLICT || 0) > 0,
  );
  return (
    <>
      {status.demo && (
        <div className="notice warning">
          <strong>Banque de démonstration</strong>
          <span>
            Les comptes et opérations ci-dessous sont fictifs. Aucun identifiant
            réel n’est lu et aucune banque n’est contactée.
          </span>
        </div>
      )}
      {error && (
        <div className="notice danger" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="notice success" role="status">
          {notice}
        </div>
      )}
      {!configured && <ConfigurationHelp status={status} />}
      <section className="panel">
        <div className="section-heading">
          <h2>{status.provider}</h2>
          <button
            onClick={() => void discover()}
            disabled={busy || !configured}
          >
            <RefreshCw size={15} className={busy ? "spin" : ""} />
            {busy ? "Lecture en cours…" : "Découvrir les comptes"}
          </button>
        </div>
        {!status.bindings.length && (
          <Empty title="Aucun compte bancaire associé">
            Choisissez explicitement vos comptes. La découverte ne modifie ni
            vos opérations ni vos soldes enregistrés.
          </Empty>
        )}
        {status.bindings.map((binding) => (
          <div className="bank-binding" key={binding.account_id}>
            <div>
              <span className="tag">
                {binding.role === "DEPENSES" ? "DÉPENSES" : "CHARGES"}
              </span>
              <strong>{binding.name}</strong>
              <span className="muted">{binding.masked_iban}</span>
            </div>
            <dl>
              <div>
                <dt>Dernière tentative de lecture</dt>
                <dd>{timestamp(binding.last_attempt_at)}</dd>
              </div>
              <div>
                <dt>Dernier import confirmé</dt>
                <dd>{timestamp(binding.last_success_at)}</dd>
              </div>
            </dl>
            {binding.error && <p className="notice danger">{binding.error}</p>}
          </div>
        ))}
      </section>
      {choices && (
        <section className="panel bank-form-panel">
          <div className="section-heading">
            <h2>Choisir les comptes à suivre</h2>
          </div>
          {choices.length ? (
            <AccountChoices
              key={choices.map((a) => a.choice_id).join()}
              accounts={choices}
              submit="Associer les comptes choisis"
              onSave={async (charges, expenses) => {
                await api(
                  "/bank/bind",
                  {
                    charges_choice_id: charges.choice_id,
                    expenses_choice_id: expenses?.choice_id || null,
                    confirmed: true,
                  },
                  "POST",
                );
                setChoices(null);
                setNotice(
                  "Comptes associés. Les soldes et les opérations seront mis à jour après confirmation d’un aperçu.",
                );
                await load();
              }}
            />
          ) : (
            <Empty title="Aucun compte courant en euros proposé">
              Vérifiez votre accès ou continuez avec les relevés CSV.
            </Empty>
          )}
        </section>
      )}
      {status.bindings.length > 0 && (
        <section className="panel bank-form-panel">
          <div className="section-heading">
            <h2>Lire les soldes et les opérations</h2>
            <Landmark size={18} />
          </div>
          <ActionForm
            submit={
              status.demo
                ? "Préparer l’aperçu fictif"
                : "Lire la banque et préparer l’aperçu"
            }
            onSave={async (form) => {
              setError("");
              setNotice("");
              setBusy(true);
              try {
                const result = await api<BankPreview>(
                  "/bank/preview",
                  { since: form.get("since") },
                  "POST",
                );
                setPreview(result);
                setDecisions({});
                await onChanged();
              } finally {
                setBusy(false);
                await load();
              }
            }}
          >
            <p className="dialog-copy">
              Lecture jusqu’à aujourd’hui, limitée aux opérations
              comptabilisées. Les virements internes seront à identifier lors de
              l’affectation. Rien n’est ajouté ni remplacé avant votre
              confirmation.
            </p>
            <Field
              label="Importer l’historique depuis le"
              name="since"
              type="date"
              value={new Date(
                Date.parse(localToday + "T12:00:00") - 365 * 86400000,
              )
                .toISOString()
                .slice(0, 10)}
              max={localToday}
            />
            <p className="dialog-copy">
              La lecture peut prendre quelques minutes. La banque peut limiter
              l’historique disponible.
            </p>
          </ActionForm>
        </section>
      )}
      {preview && (
        <section className="panel bank-form-panel">
          <div className="section-heading">
            <h2>Vérifier avant de mettre à jour</h2>
            <span className="tag">Aperçu valable 10 minutes</span>
          </div>
          <p className="dialog-copy">
            Lecture du {shortDate(preview.balance_date)}. Les anciens soldes
            restent utilisés par la prévision jusqu’à votre confirmation.
          </p>
          {invalid && (
            <div className="notice danger" role="alert">
              Une opération est invalide ou en conflit. Aucune mise à jour
              partielle des comptes ne sera faite.
            </div>
          )}
          <ActionForm
            submit="Confirmer l’import et les soldes"
            onSave={async (form) => {
              if (invalid)
                throw new Error(
                  "Résolvez les conflits avant de confirmer une lecture bancaire.",
                );
              if (!form.get("confirmed"))
                throw new Error(
                  "Confirmez les opérations et les soldes affichés.",
                );
              const result = await api<{ imported_count: number }>(
                "/bank/commit",
                {
                  snapshot_id: preview.snapshot_id,
                  decisions,
                  confirmed: true,
                },
                "POST",
              );
              setPreview(null);
              setDecisions({});
              setNotice(
                `${result.imported_count} opération(s) ajoutée(s). Les soldes des comptes sélectionnés ont été actualisés.`,
              );
              await load();
              await onChanged();
            }}
          >
            {preview.accounts.map((account) => (
              <div className="bank-preview-account" key={account.account_id}>
                <h3>
                  {account.role === "DEPENSES" ? "DÉPENSES" : "CHARGES"} ·{" "}
                  {account.name}{" "}
                  <span className="muted">{account.masked_iban}</span>
                </h3>
                <div className="bank-balance-change">
                  <span>
                    Solde enregistré{" "}
                    <strong>{money(account.previous_balance_cents)}</strong>
                  </span>
                  <ArrowRight size={16} />
                  <span>
                    Solde bancaire lu{" "}
                    <strong>{money(account.balance_cents)}</strong>
                  </span>
                </div>
                <div className="import-summary">
                  {Object.entries(account.preview.counts).map(
                    ([key, count]) => (
                      <span
                        className={
                          "tag " +
                          (["ERROR", "CONFLICT", "AMBIGUOUS"].includes(key)
                            ? "warn"
                            : "")
                        }
                        key={key}
                      >
                        {count} {statusLabels[key].toLowerCase()}
                      </span>
                    ),
                  )}
                </div>
                <div className="table-scroll import-preview">
                  <table>
                    <caption className="sr-only">
                      Opérations bancaires {account.role}
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Opération</th>
                        <th scope="col" className="numeric">
                          Montant
                        </th>
                        <th scope="col">Décision</th>
                      </tr>
                    </thead>
                    <tbody>
                      {account.preview.rows.map((row) => (
                        <tr key={row.line}>
                          <th scope="row">
                            {row.raw_label || "Données invalides"}
                            <small className="row-sub">
                              {row.booking_date
                                ? shortDate(row.booking_date)
                                : ""}{" "}
                              · {row.message}
                            </small>
                          </th>
                          <td className="numeric">
                            {row.amount_cents !== undefined
                              ? money(row.amount_cents)
                              : "—"}
                          </td>
                          <td>
                            {row.status === "AMBIGUOUS" ? (
                              <select
                                aria-label={`Décision ${account.role} ligne ${row.line}`}
                                value={
                                  decisions[String(account.account_id)]?.[
                                    String(row.line)
                                  ] || ""
                                }
                                required
                                onChange={(e) =>
                                  setDecisions({
                                    ...decisions,
                                    [String(account.account_id)]: {
                                      ...decisions[String(account.account_id)],
                                      [String(row.line)]: e.target.value,
                                    },
                                  })
                                }
                              >
                                <option value="">Choisir…</option>
                                <option value="IMPORT">
                                  Conserver cette opération
                                </option>
                                <option value="SKIP">
                                  Écarter comme doublon
                                </option>
                              </select>
                            ) : (
                              <span className="tag">
                                {statusLabels[row.status]}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!account.preview.rows.length && (
                    <Empty title="Aucune opération sur la période">
                      Le solde affiché peut néanmoins être actualisé après votre
                      confirmation.
                    </Empty>
                  )}
                </div>
              </div>
            ))}
            <label className="check-field bank-confirm">
              <input type="checkbox" name="confirmed" required />
              Je confirme l’import de cette sélection et le remplacement des
              soldes enregistrés par les soldes bancaires affichés.
            </label>
          </ActionForm>
        </section>
      )}
      <p className="help-line">
        L’application ne peut effectuer aucun virement. La synchronisation est
        manuelle ; les secrets bancaires restent sur le serveur.
      </p>
    </>
  );
}
