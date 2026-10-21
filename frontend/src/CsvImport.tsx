import { useRef, useState } from "react";
import { ArrowLeft, Check, FileUp } from "lucide-react";
import { api } from "./api";
import { ActionForm, Select } from "./components";
import { money, shortDate } from "./money";
import type { Account } from "./types";

type Mapping = {
  booking_date: string;
  raw_label: string;
  amount: string | null;
  debit: string | null;
  credit: string | null;
  operation_date: string | null;
  provider_id: string | null;
};
type CsvBody = {
  account_id: number;
  content: string;
  delimiter: string;
  date_format: string;
  decimal_separator: string;
  mapping: Mapping;
};
type Row = {
  line: number;
  status: string;
  message: string;
  booking_date?: string;
  raw_label?: string;
  amount_cents?: number;
};
type Preview = {
  rows: Row[];
  counts: Record<string, number>;
  preview_token: string;
  already_imported: boolean;
  date_from: string | null;
  date_until: string | null;
};
export type ImportResult = {
  imported_count: number;
  skipped_count: number;
  already_imported: boolean;
  date_from: string | null;
  date_until: string | null;
};
const statusLabels: Record<string, string> = {
  NEW: "À importer",
  DUPLICATE: "Déjà présent",
  AMBIGUOUS: "À décider",
  CONFLICT: "Conflit de référence",
  ERROR: "Ligne invalide",
};
const mappingLabels: Record<keyof Mapping, string> = {
  booking_date: "Date comptable",
  raw_label: "Libellé bancaire",
  amount: "Montant signé",
  debit: "Débit",
  credit: "Crédit",
  operation_date: "Date d’achat (facultative)",
  provider_id: "Référence bancaire (facultative)",
};
const initialMapping: Mapping = {
  booking_date: "",
  raw_label: "",
  amount: null,
  debit: null,
  credit: null,
  operation_date: null,
  provider_id: null,
};
const demoCsv =
  "Date;Libellé;Montant;Référence\n05/07/2026;PRLV ENERGIE EXEMPLE;-98,50;exemple-energie-juillet\n05/08/2026;PRLV ENERGIE EXEMPLE;-98,50;exemple-energie-aout\n05/09/2026;PRLV ENERGIE EXEMPLE;-105,00;exemple-energie-septembre\n12/09/2026;CHEQUE 123456;-100,00;exemple-cheque-1\n12/09/2026;CHEQUE 123457;-100,00;exemple-cheque-2\n";

function guess(headers: string[]): Mapping {
  const normalize = (s: string) =>
    s
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z]/g, "");
  const find = (...names: string[]) =>
    headers.find((h) => names.includes(normalize(h))) || null;
  const amount = find("montant", "amount", "montanteur");
  return {
    booking_date:
      find("date", "datecomptable", "bookingdate", "dateoperation") || "",
    raw_label:
      find("libelle", "libellebancaire", "label", "rawlabel", "description") ||
      "",
    amount,
    debit: amount ? null : find("debit"),
    credit: amount ? null : find("credit"),
    operation_date: find("datedachat", "dateachat", "operationdate"),
    provider_id: find(
      "reference",
      "id",
      "identifiant",
      "providerid",
      "providertransactionid",
    ),
  };
}

export default function CsvImport({
  accounts,
  onImported,
  onFinish,
  demo,
}: {
  accounts: Account[];
  onImported: () => Promise<void>;
  onFinish: (page: "transactions" | "history", month?: string) => void;
  demo: boolean;
}) {
  const [fileName, setFileName] = useState("");
  const [encoding, setEncoding] = useState("utf-8");
  const [content, setContent] = useState("");
  const [delimiter, setDelimiter] = useState(";");
  const [headers, setHeaders] = useState<string[]>([]);
  const [sample, setSample] = useState<string[][]>([]);
  const [mapping, setMapping] = useState<Mapping>(initialMapping);
  const [amountMode, setAmountMode] = useState("signed");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [body, setBody] = useState<CsvBody | null>(null);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ImportResult | null>(null);
  const [fileError, setFileError] = useState("");
  const [reading, setReading] = useState(false);
  const bytes = useRef<ArrayBuffer | null>(null);
  const generation = useRef(0);
  async function inspect(text: string, separator: string) {
    const current = ++generation.current;
    setReading(true);
    setFileError("");
    setHeaders([]);
    setSample([]);
    try {
      const data = await api<{ headers: string[]; sample: string[][] }>(
        "/import/csv/columns",
        { content: text, delimiter: separator },
        "POST",
      );
      if (current !== generation.current) return;
      const proposed = guess(data.headers);
      setHeaders(data.headers);
      setSample(data.sample);
      setMapping(proposed);
      setAmountMode(
        proposed.amount || (!proposed.debit && !proposed.credit)
          ? "signed"
          : "split",
      );
    } catch (e) {
      if (current === generation.current) setFileError((e as Error).message);
    } finally {
      if (current === generation.current) setReading(false);
    }
  }
  async function decode(
    buffer: ArrayBuffer,
    name: string,
    codec: string,
    separator: string,
  ) {
    generation.current++;
    setFileName(name);
    setHeaders([]);
    setSample([]);
    setContent("");
    try {
      const text = new TextDecoder(codec, { fatal: true }).decode(buffer);
      setContent(text);
      setFileName(name);
      await inspect(text, separator);
    } catch {
      setHeaders([]);
      setReading(false);
      setFileError(
        "Le fichier n’est pas lisible avec cet encodage. Essayez Windows-1252.",
      );
    }
  }
  async function loadFile(file: File) {
    const current = ++generation.current;
    setFileName(file.name);
    setHeaders([]);
    setContent("");
    setSample([]);
    setFileError("");
    bytes.current = null;
    if (file.size > 2_000_000) {
      setReading(false);
      setFileError("Fichier trop volumineux : 2 Mo maximum.");
      return;
    }
    try {
      setReading(true);
      const buffer = await file.arrayBuffer();
      if (current !== generation.current) return;
      bytes.current = buffer;
      await decode(buffer, file.name, encoding, delimiter);
    } catch {
      if (current === generation.current) {
        setReading(false);
        setFileError("Impossible de lire ce fichier.");
      }
    }
  }
  const invalid =
    preview && (preview.counts.ERROR || 0) + (preview.counts.CONFLICT || 0) > 0;
  const ambiguous =
    preview?.rows.filter((row) => row.status === "AMBIGUOUS") || [];
  if (result)
    return (
      <section className="import-result" aria-live="polite">
        <span className="status-icon">
          <Check size={20} />
        </span>
        <h3>
          {result.already_imported
            ? "Ce fichier a déjà été traité"
            : "Import terminé"}
        </h3>
        <p>
          <strong>{result.imported_count}</strong> opération(s) ajoutée(s) ·{" "}
          <strong>{result.skipped_count}</strong> écartée(s) ou déjà
          présente(s).
        </p>
        <p className="muted">
          Le solde du compte et les règles n’ont pas été modifiés. Les nouvelles
          opérations attendent votre affectation.
        </p>
        <div className="form-actions">
          <button
            onClick={() =>
              onFinish("transactions", result.date_until?.slice(0, 7))
            }
          >
            Voir les opérations
          </button>
          <button className="primary" onClick={() => onFinish("history")}>
            Analyser l’historique
          </button>
        </div>
      </section>
    );
  if (preview && body)
    return (
      <>
        <div className="import-steps">
          <span>1. Fichier et colonnes</span>
          <strong>2. Vérifier et importer</strong>
        </div>
        <div className="notice">
          <span>
            <strong>{fileName}</strong> ·{" "}
            {accounts.find((a) => a.id === body.account_id)?.name}
            {preview.date_from &&
              ` · Du ${shortDate(preview.date_from)} au ${shortDate(preview.date_until!)}`}
          </span>
        </div>
        <div className="import-summary">
          {Object.entries(preview.counts).map(([status, count]) => (
            <span
              className={
                "tag " +
                (["ERROR", "CONFLICT", "AMBIGUOUS"].includes(status)
                  ? "warn"
                  : "")
              }
              key={status}
            >
              {count} {statusLabels[status].toLowerCase()}
            </span>
          ))}
        </div>
        {invalid && (
          <div className="notice danger" role="alert">
            Des lignes sont invalides ou en conflit. Corrigez le fichier ou le
            mapping : rien ne sera importé partiellement.
          </div>
        )}
        <ActionForm
          submit={
            preview.already_imported
              ? "Terminer sans doublon"
              : "Confirmer l’import"
          }
          onSave={async () => {
            if (invalid)
              throw new Error(
                "Corrigez les lignes invalides avant de confirmer.",
              );
            if (ambiguous.some((row) => !decisions[String(row.line)]))
              throw new Error(
                "Choisissez une décision pour chaque doublon possible.",
              );
            const imported = await api<ImportResult>(
              "/import/csv/commit",
              { ...body, preview_token: preview.preview_token, decisions },
              "POST",
            );
            setResult(imported);
            await onImported();
          }}
        >
          <div className="table-scroll import-preview">
            <table>
              <caption className="sr-only">
                Aperçu des opérations à importer
              </caption>
              <thead>
                <tr>
                  <th scope="col">Ligne / date</th>
                  <th scope="col">Libellé</th>
                  <th scope="col" className="numeric">
                    Montant
                  </th>
                  <th scope="col">Décision</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.line}>
                    <th scope="row">
                      {row.line}
                      {row.booking_date && (
                        <small className="row-sub">
                          {shortDate(row.booking_date)}
                        </small>
                      )}
                    </th>
                    <td>
                      {row.raw_label || "—"}
                      <small className="row-sub">{row.message}</small>
                    </td>
                    <td className="numeric">
                      {row.amount_cents !== undefined
                        ? money(row.amount_cents)
                        : "—"}
                    </td>
                    <td>
                      {row.status === "AMBIGUOUS" ? (
                        <select
                          aria-label={"Décision ligne " + row.line}
                          value={decisions[String(row.line)] || ""}
                          onChange={(e) =>
                            setDecisions({
                              ...decisions,
                              [String(row.line)]: e.target.value,
                            })
                          }
                          required
                        >
                          <option value="">Choisir…</option>
                          <option value="IMPORT">
                            Conserver cette opération
                          </option>
                          <option value="SKIP">Écarter comme doublon</option>
                        </select>
                      ) : (
                        <span
                          className={
                            "tag " +
                            (["ERROR", "CONFLICT"].includes(row.status)
                              ? "warn"
                              : "")
                          }
                        >
                          {statusLabels[row.status]}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setPreview(null);
              setDecisions({});
            }}
          >
            <ArrowLeft size={15} />
            Revenir aux colonnes ou recalculer l’aperçu
          </button>
        </ActionForm>
      </>
    );
  return (
    <>
      <div className="import-steps">
        <strong>1. Fichier et colonnes</strong>
        <span>2. Vérifier et importer</span>
      </div>
      <p className="dialog-copy">
        Choisissez un relevé, vérifiez ses colonnes et le compte destinataire.
        Aucun import n’a lieu avant l’aperçu et votre confirmation.
      </p>
      <div className="form-grid">
        <label className="field">
          <span>Fichier CSV</span>
          <input
            type="file"
            accept=".csv,.txt,text/csv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              void loadFile(file);
            }}
          />
        </label>
        <label className="field">
          <span>Encodage</span>
          <select
            value={encoding}
            onChange={async (e) => {
              setEncoding(e.target.value);
              if (bytes.current)
                await decode(
                  bytes.current,
                  fileName,
                  e.target.value,
                  delimiter,
                );
            }}
          >
            <option value="utf-8">UTF-8</option>
            <option value="windows-1252">Windows-1252 (anciens relevés)</option>
          </select>
        </label>
      </div>
      <label className="field">
        <span>Séparateur de colonnes</span>
        <select
          value={delimiter}
          onChange={async (e) => {
            setDelimiter(e.target.value);
            if (content) await inspect(content, e.target.value);
          }}
        >
          <option value=";">Point-virgule ;</option>
          <option value=",">Virgule ,</option>
          <option value={"\t"}>Tabulation</option>
        </select>
      </label>
      {demo && !content && (
        <button
          className="text-button"
          onClick={async () => {
            bytes.current = null;
            setContent(demoCsv);
            setFileName("exemple-fictif.csv");
            setDelimiter(";");
            await inspect(demoCsv, ";");
          }}
        >
          <FileUp size={16} />
          Charger un exemple fictif
        </button>
      )}
      {fileError && (
        <div className="notice danger" role="alert">
          {fileError}
        </div>
      )}
      {reading && <p role="status">Lecture des colonnes…</p>}
      {headers.length > 0 && !reading && (
        <ActionForm
          submit="Vérifier l’aperçu"
          onSave={async (form) => {
            const request: CsvBody = {
              account_id: Number(form.get("account_id")),
              content,
              delimiter,
              date_format: String(form.get("date_format")),
              decimal_separator: String(form.get("decimal_separator")),
              mapping: {
                ...mapping,
                amount: amountMode === "signed" ? mapping.amount : null,
                debit: amountMode === "split" ? mapping.debit : null,
                credit: amountMode === "split" ? mapping.credit : null,
              },
            };
            setBody(request);
            setPreview(
              await api<Preview>("/import/csv/preview", request, "POST"),
            );
            setDecisions({});
          }}
        >
          <Select
            label="Compte qui figure sur ce relevé"
            name="account_id"
            value={body?.account_id || ""}
          >
            <option value="" disabled>
              Choisir le compte…
            </option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
          <div className="form-grid">
            <Select
              label="Format des dates"
              name="date_format"
              value={body?.date_format || "%d/%m/%Y"}
            >
              <option value="%d/%m/%Y">Jour/mois/année · 31/10/2026</option>
              <option value="%Y-%m-%d">Année-mois-jour · 2026-10-31</option>
              <option value="%d-%m-%Y">Jour-mois-année · 31-10-2026</option>
            </Select>
            <Select
              label="Décimales des montants (€)"
              name="decimal_separator"
              value={body?.decimal_separator || ","}
            >
              <option value=",">Virgule · −100,50</option>
              <option value=".">Point · −100.50</option>
            </Select>
          </div>
          <label className="field">
            <span>Présentation des montants</span>
            <select
              value={amountMode}
              onChange={(e) => setAmountMode(e.target.value)}
            >
              <option value="signed">Une colonne signée (débit négatif)</option>
              <option value="split">
                Deux colonnes débit/crédit (positifs)
              </option>
            </select>
          </label>
          <div className="mapping-grid">
            {(Object.keys(mappingLabels) as (keyof Mapping)[])
              .filter((key) =>
                amountMode === "signed"
                  ? !["debit", "credit"].includes(key)
                  : key !== "amount",
              )
              .map((key) => (
                <label className="field" key={key}>
                  <span>{mappingLabels[key]}</span>
                  <select
                    value={mapping[key] || ""}
                    required={["booking_date", "raw_label", "amount"].includes(
                      key,
                    )}
                    onChange={(e) =>
                      setMapping({
                        ...mapping,
                        [key]:
                          e.target.value ||
                          (["booking_date", "raw_label"].includes(key)
                            ? ""
                            : null),
                      })
                    }
                  >
                    <option value="">
                      {["booking_date", "raw_label", "amount"].includes(key)
                        ? "Choisir une colonne…"
                        : "Ne pas utiliser"}
                    </option>
                    {headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
          </div>
          <details className="advanced">
            <summary>Voir les premières lignes du fichier</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {headers.map((h) => (
                      <th key={h} scope="col">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sample.map((row, i) => (
                    <tr key={i}>
                      {row.map((value, j) => (
                        <td key={j}>{value}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p className="dialog-copy">
            Montants en euros, deux décimales maximum. Sans référence bancaire,
            un paiement identique à une opération déjà présente nécessitera
            votre décision.
          </p>
        </ActionForm>
      )}
    </>
  );
}
