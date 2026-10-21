import { useCallback, useEffect, useRef, useState } from "react";
import { FileUp, RefreshCw } from "lucide-react";
import { api } from "./api";
import { ActionForm, Empty, Field, Modal, Select } from "./components";
import { cents, decimal, frequencyLabel, money, shortDate } from "./money";
import type { Account, Charge } from "./types";

type Group = {
  key: string;
  label: string;
  account_id: number;
  count: number;
  dismissed: boolean;
  frequency: string | null;
  ambiguous: boolean;
  explanation: string;
  first_date: string;
  last_date: string;
  last_cents: number;
  mean_cents: number;
  median_cents: number;
  min_cents: number;
  max_cents: number;
  total_cents: number;
  interval_days: number[];
  transactions: {
    id: number;
    date: string;
    raw_label: string;
    amount_cents: number;
  }[];
};
type Analysis = {
  account_id: number;
  transaction_count: number;
  unclassified_debit_count: number;
  groups: Group[];
  first_date: string | null;
  last_date: string | null;
};
const localToday = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Paris",
}).format(new Date());

export default function HistoryPanel({
  accounts,
  charges,
  onChanged,
  onImport,
}: {
  accounts: Account[];
  charges: Charge[];
  onChanged: () => Promise<void>;
  onImport: () => void;
}) {
  const [account, setAccount] = useState(
    accounts.find((a) => a.role === "CHARGES")!.id,
  );
  const [includeDismissed, setIncludeDismissed] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selected, setSelected] = useState<Group | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    setError("");
    setLoading(true);
    try {
      const data = await api<Analysis>(
        `/history?account_id=${account}&include_dismissed=${includeDismissed}`,
      );
      if (current === generation.current) setAnalysis(data);
    } catch (e) {
      if (current === generation.current) setError((e as Error).message);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [account, includeDismissed]);
  useEffect(() => {
    setAnalysis(null);
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  async function dismiss(group: Group) {
    try {
      await api(
        `/history/${group.key}/dismissal?account_id=${account}`,
        undefined,
        group.dismissed ? "DELETE" : "PUT",
      );
      setNotice(
        group.dismissed
          ? "Groupe rétabli dans les propositions."
          : "Groupe ignoré. Les opérations restent présentes et consultables.",
      );
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <div className="toolbar">
        <label className="field compact-field">
          <span>Compte à analyser</span>
          <select
            value={account}
            onChange={(e) => {
              setAccount(Number(e.target.value));
              setNotice("");
            }}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <div className="toolbar-actions">
          <button onClick={() => void load()} disabled={loading}>
            <RefreshCw size={15} />
            Actualiser
          </button>
          <button className="primary" onClick={onImport}>
            <FileUp size={16} />
            Importer un CSV
          </button>
        </div>
      </div>
      <div className="notice">
        L’analyse regroupe les libellés identiques, en ignorant la casse, les
        accents et les espaces. Elle porte sur les débits non affectés du compte
        choisi. Aucune proposition n’est validée automatiquement.
      </div>
      {error && (
        <div role="alert" className="notice danger">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="notice success">
          {notice}
        </div>
      )}
      <div className="history-context">
        <span>
          {analysis
            ? `${analysis.transaction_count} opération(s) · ${analysis.unclassified_debit_count} débit(s) non affecté(s)`
            : "Lecture de l’historique…"}
          {analysis?.first_date &&
            ` · ${shortDate(analysis.first_date)} → ${shortDate(analysis.last_date!)}`}
        </span>
        <label className="check-field">
          <input
            type="checkbox"
            checked={includeDismissed}
            onChange={(e) => setIncludeDismissed(e.target.checked)}
          />
          Voir aussi les groupes ignorés
        </label>
      </div>
      {loading && <p role="status">Analyse en cours…</p>}
      {analysis && !loading && (
        <section className="panel">
          <div className="table-scroll">
            <table className="history-table">
              <caption className="sr-only">
                Groupes de dépenses à examiner
              </caption>
              <thead>
                <tr>
                  <th scope="col">Libellé et fréquence observée</th>
                  <th scope="col" className="numeric">
                    Opérations
                  </th>
                  <th scope="col" className="numeric">
                    Dernier montant
                  </th>
                  <th scope="col" className="numeric">
                    Médiane
                  </th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {analysis.groups.map((group) => (
                  <tr key={group.key}>
                    <th scope="row">
                      <button
                        className="row-link"
                        onClick={() => setSelected(group)}
                      >
                        {group.label}
                      </button>
                      <small className="row-sub">
                        {group.frequency
                          ? frequencyLabel[group.frequency] + " · probable"
                          : group.ambiguous
                            ? "Bénéficiaire à identifier"
                            : "Fréquence à préciser"}
                        {group.dismissed ? " · Ignoré" : ""}
                      </small>
                    </th>
                    <td className="numeric">{group.count}</td>
                    <td className="numeric">{money(group.last_cents)}</td>
                    <td className="numeric">{money(group.median_cents)}</td>
                    <td>
                      <div className="row-actions">
                        <button onClick={() => setSelected(group)}>
                          Examiner
                        </button>
                        <button
                          className="text-button"
                          onClick={() => void dismiss(group)}
                        >
                          {group.dismissed ? "Rétablir" : "Ignorer"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!analysis.groups.length && (
            <Empty title="Aucun groupe à examiner">
              Importez votre historique ou consultez les groupes ignorés. Les
              opérations déjà affectées ne sont pas proposées une seconde fois.
            </Empty>
          )}
        </section>
      )}
      {selected && (
        <Modal
          title="Examiner une proposition"
          onClose={() => setSelected(null)}
          wide
        >
          <HistoryValidation
            key={selected.key}
            group={selected}
            charges={charges}
            onCancel={() => setSelected(null)}
            onSave={async (body) => {
              await api("/history/validate", body, "POST");
              setSelected(null);
              setNotice(
                "Validation enregistrée. Seules les opérations sélectionnées ont été affectées.",
              );
              await onChanged();
              await load();
            }}
          />
        </Modal>
      )}
    </>
  );
}

function HistoryValidation({
  group,
  charges,
  onSave,
  onCancel,
}: {
  group: Group;
  charges: Charge[];
  onSave: (body: unknown) => Promise<void>;
  onCancel: () => void;
}) {
  const [mode, setMode] = useState("new");
  const [chosen, setChosen] = useState<number[]>(
    group.ambiguous ? [] : group.transactions.map((t) => t.id),
  );
  const [amount, setAmount] = useState(decimal(group.last_cents));
  return (
    <>
      <p className="proposal-label">{group.label}</p>
      <p className="dialog-copy">{group.explanation}</p>
      <dl className="stats-strip">
        <div>
          <dt>Moyenne</dt>
          <dd>{money(group.mean_cents)}</dd>
        </div>
        <div>
          <dt>Médiane</dt>
          <dd>{money(group.median_cents)}</dd>
        </div>
        <div>
          <dt>Minimum</dt>
          <dd>{money(group.min_cents)}</dd>
        </div>
        <div>
          <dt>Maximum</dt>
          <dd>{money(group.max_cents)}</dd>
        </div>
      </dl>
      <ActionForm
        submit="Valider la règle et la sélection"
        onCancel={onCancel}
        onSave={(f) => {
          if (!chosen.length)
            throw new Error("Sélectionnez au moins une opération à rattacher.");
          return onSave({
            account_id: group.account_id,
            key: group.key,
            transaction_ids: chosen,
            existing_charge_id:
              mode === "existing" ? Number(f.get("existing_charge_id")) : null,
            name: mode === "new" ? f.get("name") : group.label.slice(0, 120),
            amount_cents: mode === "new" ? cents(amount) : group.last_cents,
            frequency: mode === "new" ? f.get("frequency") : "MONTHLY",
            anchor_date: mode === "new" ? f.get("anchor_date") : localToday,
          });
        }}
      >
        <label className="field">
          <span>Que voulez-vous valider ?</span>
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="new">Créer une nouvelle charge</option>
            {charges.length > 0 && (
              <option value="existing">Rattacher à une charge existante</option>
            )}
          </select>
        </label>
        {mode === "new" ? (
          <>
            <Field
              label="Nom de la charge"
              name="name"
              value={group.ambiguous ? "" : group.label.slice(0, 120)}
            />
            <div className="form-grid">
              <label className="field">
                <span>Montant de référence (€)</span>
                <input
                  name="amount"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  inputMode="decimal"
                  required
                />
                <small>
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => setAmount(decimal(group.last_cents))}
                  >
                    Dernier montant
                  </button>{" "}
                  ·{" "}
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => setAmount(decimal(group.median_cents))}
                  >
                    Médiane
                  </button>
                </small>
              </label>
              <Select
                label="Fréquence validée"
                name="frequency"
                value={group.frequency || ""}
              >
                <option value="" disabled>
                  Choisir la fréquence…
                </option>
                {Object.entries(frequencyLabel)
                  .filter(([key]) => key !== "MANUAL")
                  .map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
              </Select>
            </div>
            <Field
              label="Première échéance de la règle"
              name="anchor_date"
              type="date"
              value={
                localToday.slice(0, 8) +
                String(
                  Math.min(
                    Number(group.last_date.slice(8)),
                    new Date(
                      Number(localToday.slice(0, 4)),
                      Number(localToday.slice(5, 7)),
                      0,
                    ).getDate(),
                  ),
                ).padStart(2, "0")
              }
              hint="La prévision s’applique à partir de cette date. Les opérations antérieures sont conservées comme historique réel, sans règle rétroactive inventée."
            />
          </>
        ) : (
          <Select label="Charge existante" name="existing_charge_id">
            {charges.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        )}
        <div className="section-heading selection-heading">
          <h3>Opérations à rattacher</h3>
          <span>{chosen.length} sélectionnée(s)</span>
        </div>
        {group.ambiguous && (
          <div className="notice warning">
            Aucune opération n’est présélectionnée : identifiez manuellement les
            paiements qui correspondent à cette charge.
          </div>
        )}
        <div className="table-scroll history-selection">
          <table>
            <caption className="sr-only">
              Sélection des opérations historiques
            </caption>
            <thead>
              <tr>
                <th scope="col">Choix</th>
                <th scope="col">Date / libellé</th>
                <th scope="col" className="numeric">
                  Montant
                </th>
              </tr>
            </thead>
            <tbody>
              {group.transactions.map((t) => (
                <tr key={t.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={
                        "Rattacher l’opération du " + t.date + " numéro " + t.id
                      }
                      checked={chosen.includes(t.id)}
                      onChange={(e) =>
                        setChosen(
                          e.target.checked
                            ? [...chosen, t.id]
                            : chosen.filter((id) => id !== t.id),
                        )
                      }
                    />
                  </td>
                  <th scope="row">
                    {t.raw_label}
                    <small className="row-sub">{shortDate(t.date)}</small>
                  </th>
                  <td className="numeric">{money(t.amount_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="dialog-copy">
          Cette validation affecte uniquement la sélection ci-dessus. Elle ne
          crée aucune règle automatique de reconnaissance pour les prochains
          imports.
        </p>
      </ActionForm>
    </>
  );
}
