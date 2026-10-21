import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownLeft,
  BarChart3,
  FileUp,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  Download,
  FileText,
  LayoutDashboard,
  Landmark,
  ListFilter,
  LogOut,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Wallet,
  X,
} from "lucide-react";
import BankingPanel from "./BankingPanel";
import Onboarding from "./Onboarding";
import CsvImport from "./CsvImport";
import HistoryPanel from "./HistoryPanel";
import { api, setCsrf } from "./api";
import { ActionForm, Empty, Field, Modal, Select } from "./components";
import {
  cents,
  decimal,
  frequencyLabel,
  money,
  monthLabel,
  shortDate,
} from "./money";
import type { Account, Budget, Charge, Forecast, Transaction } from "./types";

type Page =
  | "month"
  | "charges"
  | "budgets"
  | "transactions"
  | "review"
  | "settings"
  | "history"
  | "bank";
type Dialog =
  | {
      type:
        "charge" | "budget" | "adjustment" | "plan" | "transaction" | "import";
    }
  | { type: "balance"; item: Account }
  | { type: "charge-detail"; item: Charge }
  | { type: "budget-detail"; item: Budget }
  | { type: "classify"; item: Transaction };
const localToday = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Paris",
}).format(new Date());
const headings: Record<Page, [string, string]> = {
  month: [
    "Prévision du mois",
    "Ce qui doit rester sur CHARGES, avant les dépenses libres.",
  ],
  charges: [
    "Charges",
    "Les factures et échéances prévues pour le mois sélectionné.",
  ],
  budgets: [
    "Budgets protégés",
    "L’argent réservé aux dépenses nécessaires du foyer.",
  ],
  transactions: [
    "Opérations",
    "Renseigner les opérations réelles, puis leur rôle dans le budget.",
  ],
  review: [
    "À vérifier",
    "Les opérations à affecter et les différences avec vos règles.",
  ],
  history: [
    "Analyse historique",
    "Examiner les dépenses récurrentes et valider leur fonctionnement.",
  ],
  bank: [
    "Banque",
    "Associer les comptes, lire les opérations et vérifier avant de mettre à jour.",
  ],
  settings: ["Réglages", "Comptes suivis, données et sauvegardes."],
};
const nav = [
  ["month", LayoutDashboard, "Ce mois-ci"],
  ["charges", FileText, "Charges"],
  ["budgets", Wallet, "Budgets protégés"],
  ["transactions", ListFilter, "Opérations"],
  ["review", ClipboardCheck, "À vérifier"],
  ["bank", Landmark, "Banque"],
  ["history", BarChart3, "Analyse historique"],
  ["settings", Settings, "Réglages"],
] as const;
const kindLabels: Record<string, string> = {
  CHARGE: "Paiement d’une charge",
  FUNDED: "Financement d’un budget",
  SPENT: "Dépense d’un budget",
  INTERNAL: "Transfert interne",
  OTHER: "Autre opération",
};

export default function App() {
  const [session, setSession] = useState<{
    authenticated: boolean;
    demo: boolean;
  } | null>(null);
  const [month, setMonth] = useState(localToday.slice(0, 7));
  const [state, setState] = useState<Forecast | null>(null);
  const [page, setPage] = useState<Page>("month");
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const mainRef = useRef<HTMLElement>(null);
  const generation = useRef(0);

  const load = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true);
    setError("");
    try {
      const data = await api<Forecast>("/forecast?month=" + month);
      if (current === generation.current) setState(data);
    } catch (e) {
      if (current === generation.current) setError((e as Error).message);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [month]);

  useEffect(() => {
    api<{ authenticated: boolean; demo: boolean; csrf?: string }>("/session")
      .then((s) => {
        setCsrf(s.csrf || "");
        setSession(s);
        if (s.demo) setMonth("2026-10");
      })
      .catch((e) => setError(e.message));
    const expired = () => {
      setSession({ authenticated: false, demo: false });
      setState(null);
      setDialog(null);
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => {
    if (session?.authenticated) void load();
  }, [load, session?.authenticated]);
  useEffect(() => {
    document.title = headings[page][0] + " — BudgetWard";
  }, [page]);

  function navigate(next: Page) {
    setPage(next);
    setQuery("");
    setFilter("all");
    mainRef.current?.focus();
  }
  async function save(path: string, body?: unknown, method = "POST") {
    await api(path, body, method);
    setDialog(null);
    setNotice("Modification enregistrée. La prévision a été recalculée.");
    await load();
  }
  function shiftMonth(offset: number) {
    const d = new Date(month + "-01T12:00:00");
    d.setMonth(d.getMonth() + offset);
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    setNotice("");
    setState(null);
  }

  if (!session || (session.authenticated && !state))
    return (
      <div className="loading">
        <ShieldCheck size={28} />
        <p>{error || "Ouverture de BudgetWard…"}</p>
        {error && (
          <button onClick={() => window.location.reload()}>Réessayer</button>
        )}
      </div>
    );
  if (!session.authenticated)
    return (
      <div className="entry">
        <div className="entry-brand">
          <ShieldCheck /> BudgetWard
        </div>
        <section className="entry-panel">
          <span className="eyebrow">ESPACE DU FOYER</span>
          <h1>Ouvrir votre budget</h1>
          <p>
            Connectez-vous avec la clé administrateur configurée sur votre
            serveur.
          </p>
          <ActionForm
            submit="Se connecter"
            onSave={async (f) => {
              const s = await api<{
                authenticated: boolean;
                csrf: string;
                demo: boolean;
              }>("/session", { token: f.get("token") }, "POST");
              setCsrf(s.csrf);
              setSession(s);
            }}
          >
            <Field label="Clé d’accès" name="token" type="password" />
          </ActionForm>
        </section>
        <p className="entry-foot">Vos données restent sur votre serveur.</p>
      </div>
    );
  const data = state!;
  if (!data.configured)
    return <Onboarding onSave={(body) => save("/setup", body)} />;

  const reviewCount = data.anomalies.length + data.unclassified_count;
  const outOfDate = data.balance_date !== data.today;
  const searched = (name: string) =>
    name.toLocaleLowerCase("fr").includes(query.toLocaleLowerCase("fr"));
  const filteredTx = data.transactions.filter(
    (t) => searched(t.raw_label) && (filter !== "unknown" || !t.kind),
  );
  const totalExpected =
    data.charges.reduce((sum, c) => sum + c.expected_cents, 0) +
    data.budgets.reduce((sum, b) => sum + b.expected_cents, 0) +
    data.adjustments_cents +
    data.safety_cents +
    data.treasury_cents;

  function chargeTable(full = false) {
    const rows = data.charges.filter((c) => searched(c.name));
    return (
      <div className="table-scroll">
        <table className="charge-table">
          <caption className="sr-only">Charges de {monthLabel(month)}</caption>
          <thead>
            <tr>
              <th scope="col">Charge</th>
              <th scope="col" className="numeric">
                Prévu
              </th>
              <th scope="col" className="numeric">
                Payé
              </th>
              <th scope="col" className="numeric">
                À protéger
              </th>
              <th scope="col">État</th>
              <th scope="col">
                <span className="sr-only">Détail</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id}>
                <th scope="row">
                  <button
                    className="row-link"
                    onClick={() =>
                      setDialog({ type: "charge-detail", item: c })
                    }
                  >
                    {c.name}
                  </button>
                  {full && (
                    <small className="row-sub">
                      {frequencyLabel[c.frequency]}
                    </small>
                  )}
                </th>
                <td className="numeric muted">{money(c.expected_cents)}</td>
                <td className="numeric muted">{money(c.paid_cents)}</td>
                <td className="numeric strong">{money(c.remaining_cents)}</td>
                <td>
                  <span
                    className={
                      "tag " +
                      (c.status === "PAID"
                        ? "good"
                        : c.status === "REVIEW"
                          ? "warn"
                          : "")
                    }
                  >
                    {c.status === "PAID"
                      ? "Payé"
                      : c.status === "REVIEW"
                        ? "À vérifier"
                        : c.status === "EXPECTED"
                          ? "Non renseigné"
                          : c.status === "HISTORICAL"
                            ? "Historique"
                            : c.count
                              ? "Prévu"
                              : "Sans échéance"}
                  </span>
                </td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={"Comprendre " + c.name}
                    onClick={() =>
                      setDialog({ type: "charge-detail", item: c })
                    }
                  >
                    <ChevronRight size={17} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total charges</th>
              <td className="numeric">
                {money(data.charges.reduce((s, c) => s + c.expected_cents, 0))}
              </td>
              <td className="numeric">
                {money(data.charges.reduce((s, c) => s + c.paid_cents, 0))}
              </td>
              <td className="numeric">{money(data.charges_cents)}</td>
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
        {!rows.length && (
          <Empty title="Aucune charge affichée">
            {query
              ? "Essayez une autre recherche."
              : "Ajoutez votre première facture ou échéance."}
          </Empty>
        )}
      </div>
    );
  }

  function budgetTable() {
    const rows = data.budgets.filter((b) => searched(b.name));
    return (
      <div className="table-scroll">
        <table className="budget-table">
          <caption className="sr-only">
            Budgets protégés de {monthLabel(month)}
          </caption>
          <thead>
            <tr>
              <th scope="col">Budget</th>
              <th scope="col" className="numeric">
                Calcul du mois
              </th>
              <th scope="col" className="numeric">
                Déjà transféré
              </th>
              <th scope="col" className="numeric">
                À protéger
              </th>
              <th scope="col">
                <span className="sr-only">Détail</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.id}>
                <th scope="row">
                  <button
                    className="row-link"
                    onClick={() =>
                      setDialog({ type: "budget-detail", item: b })
                    }
                  >
                    {b.name}
                  </button>
                  <small className="row-sub">
                    {frequencyLabel[b.frequency]}
                    {b.frequency === "MANUAL" && b.manual_count === null
                      ? " · À compléter pour ce mois"
                      : ""}
                  </small>
                </th>
                <td className="numeric muted">
                  {b.count} × {money(b.amount_cents)}
                </td>
                <td className="numeric muted">{money(b.funded_cents)}</td>
                <td className="numeric strong">{money(b.remaining_cents)}</td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={"Comprendre " + b.name}
                    onClick={() =>
                      setDialog({ type: "budget-detail", item: b })
                    }
                  >
                    <ChevronRight size={17} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total budgets protégés</th>
              <td />
              <td />
              <td className="numeric">{money(data.budgets_cents)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
        {!rows.length && (
          <Empty title="Aucun budget affiché">
            {query
              ? "Essayez une autre recherche."
              : "Ajoutez les courses, le carburant ou un autre budget à protéger."}
          </Empty>
        )}
      </div>
    );
  }

  function transactionTable(rows: Transaction[]) {
    return (
      <div className="table-scroll">
        <table>
          <caption className="sr-only">Opérations du mois</caption>
          <thead>
            <tr>
              <th scope="col">Opération</th>
              <th scope="col">Compte</th>
              <th scope="col" className="numeric">
                Montant
              </th>
              <th scope="col">Affectation</th>
              <th scope="col">
                <span className="sr-only">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id}>
                <th scope="row">
                  {t.raw_label}
                  <small className="row-sub">
                    {shortDate(t.booking_date)}
                    {t.operation_date &&
                      " · Achat du " + shortDate(t.operation_date)}
                  </small>
                </th>
                <td>
                  {data.accounts.find((a) => a.id === t.account_id)?.role ===
                  "CHARGES"
                    ? "CHARGES"
                    : "DÉPENSES"}
                </td>
                <td className="numeric strong">{money(t.amount_cents)}</td>
                <td>
                  {t.kind ? (
                    <>
                      <span className="tag">{kindLabels[t.kind]}</span>
                      <small className="row-sub">
                        {t.charge_id
                          ? data.charges.find((c) => c.id === t.charge_id)?.name
                          : t.budget_id
                            ? data.budgets.find((b) => b.id === t.budget_id)
                                ?.name
                            : ""}
                      </small>
                    </>
                  ) : (
                    <span className="tag warn">À affecter</span>
                  )}
                </td>
                <td>
                  <button
                    onClick={() => setDialog({ type: "classify", item: t })}
                  >
                    {t.kind ? "Corriger" : "Affecter"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <Empty title="Aucune opération affichée">
            Importez un relevé CSV ou renseignez une opération réelle.
          </Empty>
        )}
      </div>
    );
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Aller au contenu
      </a>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("month");
          }}
        >
          <span className="brand-icon">
            <ShieldCheck size={23} strokeWidth={1.7} />
          </span>
          <span>
            BudgetWard<small>LE BUDGET DU FOYER</small>
          </span>
        </a>
        <div className="sidebar-section">ESPACE DE TRAVAIL</div>
        <nav aria-label="Navigation principale">
          {nav.map(([id, Icon, label]) => (
            <button
              key={id}
              className={"nav-item " + (page === id ? "active" : "")}
              aria-current={page === id ? "page" : undefined}
              onClick={() => navigate(id)}
            >
              <Icon size={18} strokeWidth={1.7} />
              <span>{label}</span>
              {id === "review" && reviewCount > 0 && (
                <span className="nav-count">{reviewCount}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <ShieldCheck size={16} />
          <div>
            Données sur votre serveur<small>Banque en lecture seule</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            Foyer <ChevronRight size={13} /> <span>{headings[page][0]}</span>
          </div>
          <div className="top-actions">
            <button
              className="text-button import-shortcut"
              aria-label="Importer un CSV"
              onClick={() => setDialog({ type: "import" })}
            >
              <FileUp size={15} />
              <span>Importer un CSV</span>
            </button>
            <span className="mode-label">
              <span className="dot" />
              Données locales
            </span>
            <button
              className="icon-button"
              aria-label="Recharger les données enregistrées"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? "spin" : ""} />
            </button>
            {!session.demo && (
              <button
                className="icon-button"
                aria-label="Se déconnecter"
                onClick={async () => {
                  await api("/session", undefined, "DELETE");
                  setSession({ authenticated: false, demo: false });
                  setState(null);
                }}
              >
                <LogOut size={16} />
              </button>
            )}
          </div>
        </header>
        {session.demo && (
          <div className="demo-bar">
            <span>
              <strong>Démonstration</strong> · Données fictives, séparées de
              votre futur budget.
            </span>
            <span>Les modifications restent dans la démo.</span>
          </div>
        )}
        <main id="workspace" ref={mainRef} tabIndex={-1}>
          <div className="page-heading">
            <div>
              <h1>{headings[page][0]}</h1>
              <p>{headings[page][1]}</p>
            </div>
            <div
              className="month-picker"
              hidden={
                page === "history" || page === "settings" || page === "bank"
              }
            >
              <button
                className="icon-button"
                aria-label="Mois précédent"
                onClick={() => shiftMonth(-1)}
              >
                <ChevronLeft size={18} />
              </button>
              <label className="month-input">
                <CalendarDays size={16} />
                <span className="sr-only">Mois de prévision</span>
                <input
                  type="month"
                  value={month}
                  min="2000-01"
                  max="2100-12"
                  onChange={(e) => {
                    if (/^\d{4}-\d{2}$/.test(e.target.value)) {
                      setMonth(e.target.value);
                      setState(null);
                      setNotice("");
                    }
                  }}
                />
              </label>
              <button
                className="icon-button"
                aria-label="Mois suivant"
                onClick={() => shiftMonth(1)}
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
          {error && (
            <div className="notice danger" role="alert">
              {error}
              <button onClick={() => void load()}>Réessayer</button>
            </div>
          )}
          {notice && (
            <div className="notice success" role="status">
              <Check size={16} />
              {notice}
              <button
                className="icon-button"
                aria-label="Masquer la confirmation"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {page === "month" && (
            <>
              {(data.bank_pending || data.bank_problem_count > 0) && (
                <div className="notice warning">
                  <span>
                    {data.bank_pending
                      ? "Une lecture bancaire attend votre confirmation. La prévision utilise encore les soldes enregistrés."
                      : "La dernière lecture bancaire a échoué. Les anciens soldes sont conservés."}
                  </span>
                  <button onClick={() => navigate("bank")}>
                    Voir la banque
                  </button>
                </div>
              )}
              <div className="account-strip">
                <span>
                  <span className="account-dot" />
                  CHARGES{" "}
                  <span className="muted">
                    · {data.accounts.find((a) => a.role === "CHARGES")?.name}
                  </span>
                </span>
                <button
                  className="text-button"
                  onClick={() =>
                    setDialog({
                      type: "balance",
                      item: data.accounts.find((a) => a.role === "CHARGES")!,
                    })
                  }
                >
                  Mettre à jour le solde <ArrowUpRight size={14} />
                </button>
              </div>
              <section
                className="balance-strip"
                aria-label="Résultat de la prévision"
              >
                <div>
                  <span>Solde CHARGES</span>
                  <strong>{money(data.balance_cents)}</strong>
                  <small>
                    Renseigné le {shortDate(data.balance_date!)}
                    {outOfDate ? " · à actualiser" : ""}
                  </small>
                </div>
                <div>
                  <span>À protéger encore</span>
                  <strong>{money(data.protected_cents)}</strong>
                  <small>Pour couvrir le reste du mois</small>
                </div>
                <div
                  className={data.deficit_cents ? "result deficit" : "result"}
                >
                  <span>
                    {data.deficit_cents
                      ? "Déficit prévisionnel"
                      : !data.is_current_month
                        ? "Écart simulé"
                        : "Transférable vers DÉPENSES"}{" "}
                    <ArrowUpRight size={17} />
                  </span>
                  <strong data-testid="transferable">
                    {money(data.deficit_cents || data.transferable_cents)}
                  </strong>
                  <small>
                    {data.deficit_cents
                      ? "Aucun montant transférable"
                      : "Après protection des montants ci-contre"}
                  </small>
                </div>
              </section>
              {(!data.is_current_month || outOfDate) && (
                <div className="notice warning">
                  <CircleHelp size={18} />
                  <span>
                    {!data.is_current_month
                      ? "Simulation : ce mois utilise le dernier solde renseigné, pas un solde historique ni des revenus futurs."
                      : "Le solde n’a pas été confirmé aujourd’hui. Actualisez-le avant de décider d’un virement."}
                  </span>
                </div>
              )}
              {(!data.charges.length ||
                !data.budgets.length ||
                data.budgets.some(
                  (b) => b.frequency === "MANUAL" && b.manual_count === null,
                )) && (
                <div className="notice warning">
                  <CircleHelp size={18} />
                  <span>
                    Prévision à compléter : ajoutez vos charges et vos budgets
                    avant d’utiliser le montant transférable.
                  </span>
                </div>
              )}
              <div className="work-status">
                <div>
                  <span
                    className={
                      "status-icon " +
                      (reviewCount
                        ? "attention"
                        : !data.transactions.length
                          ? "neutral"
                          : "")
                    }
                  >
                    {reviewCount || !data.transactions.length ? (
                      <CircleHelp size={18} />
                    ) : (
                      <Check size={18} />
                    )}
                  </span>
                  <span>
                    <strong>
                      {reviewCount
                        ? `${reviewCount} élément${reviewCount > 1 ? "s" : ""} à vérifier`
                        : !data.transactions.length
                          ? "Paiements du mois à renseigner"
                          : "Aucun écart signalé dans les opérations renseignées"}
                    </strong>
                    <small>
                      {data.transactions.length
                        ? `${data.transactions.length} opération(s) renseignée(s) ce mois-ci`
                        : "Aucune opération renseignée. Les paiements ne sont pas encore rapprochés."}
                    </small>
                  </span>
                </div>
                <button
                  onClick={() =>
                    navigate(reviewCount ? "review" : "transactions")
                  }
                >
                  {reviewCount ? "Vérifier" : "Voir les opérations"}
                  <ArrowRight size={15} />
                </button>
              </div>
              <section className="panel">
                <div className="section-heading">
                  <h2>
                    Charges obligatoires{" "}
                    <span className="count">{data.charges.length}</span>
                  </h2>
                  <button
                    className="text-button"
                    onClick={() => setDialog({ type: "charge" })}
                  >
                    <Plus size={16} />
                    Ajouter une charge
                  </button>
                </div>
                {chargeTable()}
              </section>
              <section className="panel">
                <div className="section-heading">
                  <h2>
                    Budgets protégés{" "}
                    <span className="count">{data.budgets.length}</span>
                  </h2>
                  <button
                    className="text-button"
                    onClick={() => setDialog({ type: "budget" })}
                  >
                    <Plus size={16} />
                    Ajouter un budget
                  </button>
                </div>
                {budgetTable()}
              </section>
              <section className="panel reserve-panel">
                <div className="section-heading">
                  <h2>Ajustements et réserve</h2>
                  <button
                    className="text-button"
                    onClick={() => setDialog({ type: "plan" })}
                  >
                    Modifier la réserve
                  </button>
                </div>
                <div className="reserve-row">
                  <span>
                    Marge de sécurité<small>Conservée sur CHARGES</small>
                  </span>
                  <strong>{money(data.safety_cents)}</strong>
                </div>
                <div className="reserve-row">
                  <span>
                    Objectif de trésorerie
                    <small>
                      Amélioration du solde ou réduction du découvert
                    </small>
                  </span>
                  <strong>{money(data.treasury_cents)}</strong>
                </div>
                {data.adjustments.map((a) => (
                  <div className="reserve-row" key={a.id}>
                    <span>
                      {a.name}
                      <small>
                        Pour ce mois uniquement · à retirer une fois payé
                      </small>
                    </span>
                    <div>
                      <strong>{money(a.amount_cents)}</strong>
                      <button
                        className="icon-button"
                        aria-label={"Retirer l’ajustement " + a.name}
                        onClick={async () => {
                          try {
                            await save(
                              "/adjustments/" + a.id,
                              undefined,
                              "DELETE",
                            );
                          } catch (e) {
                            setError((e as Error).message);
                          }
                        }}
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </div>
                ))}
                <button
                  className="text-button add-adjustment"
                  onClick={() => setDialog({ type: "adjustment" })}
                >
                  <Plus size={16} />
                  Ajouter une dépense ponctuelle
                </button>
              </section>
              <div className="calculation-foot">
                <span>
                  Besoin prévu au total :{" "}
                  <strong>{money(totalExpected)}</strong>
                </span>
                <span>
                  Reste à protéger :{" "}
                  <strong>{money(data.protected_cents)}</strong>
                </span>
                <span>
                  Chaque ligne est cliquable pour comprendre le calcul.
                </span>
              </div>
            </>
          )}
          {page === "charges" && (
            <>
              <div className="toolbar">
                <label className="search">
                  <ListFilter size={16} />
                  <span className="sr-only">Rechercher une charge</span>
                  <input
                    placeholder="Rechercher une charge…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
                <button
                  className="primary"
                  onClick={() => setDialog({ type: "charge" })}
                >
                  <Plus size={16} />
                  Ajouter une charge
                </button>
              </div>
              <section className="panel">{chargeTable(true)}</section>
              <p className="help-line">
                Un changement de montant crée une nouvelle période tarifaire.
                Les anciennes règles sont conservées.
              </p>
            </>
          )}
          {page === "budgets" && (
            <>
              <div className="toolbar">
                <p className="muted">
                  Prévu → transféré → consommé : trois montants distincts.
                </p>
                <button
                  className="primary"
                  onClick={() => setDialog({ type: "budget" })}
                >
                  <Plus size={16} />
                  Ajouter un budget
                </button>
              </div>
              <section className="panel">{budgetTable()}</section>
              <div className="notice">
                <CircleHelp size={18} />
                <span>
                  Un achat sur DÉPENSES ne réduit pas une deuxième fois le
                  montant à protéger sur CHARGES. C’est le financement du budget
                  qui le réduit.
                </span>
              </div>
            </>
          )}
          {page === "transactions" && (
            <>
              <div className="toolbar">
                <label className="search">
                  <ListFilter size={16} />
                  <span className="sr-only">Rechercher une opération</span>
                  <input
                    placeholder="Rechercher une opération…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
                <div className="toolbar-actions">
                  <select
                    aria-label="Filtrer les opérations"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    <option value="all">Toutes les opérations</option>
                    <option value="unknown">À affecter</option>
                  </select>
                  <button
                    className="primary"
                    onClick={() => setDialog({ type: "transaction" })}
                  >
                    <Plus size={16} />
                    Renseigner une opération
                  </button>
                </div>
              </div>
              <div className="notice">
                Le solde reste celui que vous avez constaté dans votre banque.
                Renseigner une opération ne le modifie pas automatiquement.
              </div>
              <section className="panel">
                {transactionTable(filteredTx)}
              </section>
            </>
          )}
          {page === "review" && (
            <>
              <div className="section-heading">
                <h2>
                  Écarts avec les règles{" "}
                  <span className="count">{data.anomalies.length}</span>
                </h2>
              </div>
              {data.anomalies.length ? (
                data.anomalies.map((a) => (
                  <article className="review-item" key={a.key}>
                    <CircleHelp size={20} />
                    <div>
                      <h3>{a.title}</h3>
                      <p>{a.message}</p>
                      {a.expected_cents !== undefined && (
                        <p>
                          Attendu : {money(a.expected_cents)} · Payé :{" "}
                          {money(a.actual_cents!)}
                        </p>
                      )}
                    </div>
                    {a.transaction_id && (
                      <button
                        onClick={() =>
                          setDialog({
                            type: "classify",
                            item: data.transactions.find(
                              (t) => t.id === a.transaction_id,
                            )!,
                          })
                        }
                      >
                        Voir l’affectation
                      </button>
                    )}
                  </article>
                ))
              ) : (
                <section className="panel">
                  <Empty title="Aucun écart détecté">
                    Seules les opérations renseignées et affectées sont
                    comparées aux règles. La détection des charges manquantes
                    par fenêtre bancaire viendra dans un prochain lot.
                  </Empty>
                </section>
              )}
              <div className="section-heading">
                <h2>
                  Opérations à affecter{" "}
                  <span className="count">{data.unclassified_count}</span>
                </h2>
              </div>
              <section className="panel">
                {transactionTable(data.transactions.filter((t) => !t.kind))}
              </section>
            </>
          )}
          {page === "history" && (
            <HistoryPanel
              accounts={data.accounts}
              charges={data.charges}
              onChanged={load}
              onImport={() => setDialog({ type: "import" })}
            />
          )}
          {page === "bank" && <BankingPanel onChanged={load} />}
          {page === "settings" && (
            <>
              <section className="panel">
                <div className="section-heading">
                  <h2>Comptes du foyer</h2>
                  <span className="tag">Données locales</span>
                </div>
                {data.accounts.map((a) => (
                  <div className="settings-row" key={a.id}>
                    <div>
                      <strong>{a.name}</strong>
                      <small>
                        {a.role === "CHARGES" ? "CHARGES" : "DÉPENSES"} · Solde
                        du {shortDate(a.balance_date)}
                      </small>
                    </div>
                    <strong className="numeric">
                      {money(a.balance_cents)}
                    </strong>
                    <button
                      onClick={() => setDialog({ type: "balance", item: a })}
                    >
                      Modifier le solde
                    </button>
                  </div>
                ))}
              </section>
              <section className="panel">
                <div className="section-heading">
                  <h2>Données et sauvegardes</h2>
                </div>
                <div className="settings-row">
                  <div>
                    <strong>Sauvegarde complète SQLite</strong>
                    <small>
                      Une copie cohérente de la base, à conserver hors du
                      serveur.
                    </small>
                  </div>
                  <a className="button" href="/api/backup">
                    <Download size={16} />
                    Télécharger
                  </a>
                </div>
                <div className="settings-row">
                  <div>
                    <strong>Export des données</strong>
                    <small>
                      Comptes, règles, budgets et opérations au format JSON.
                    </small>
                  </div>
                  <a
                    className="button"
                    href="/api/export"
                    download="budgetward-export.json"
                  >
                    <Download size={16} />
                    Exporter
                  </a>
                </div>
              </section>
              <section className="panel">
                <div className="section-heading">
                  <h2>À propos de BudgetWard</h2>
                </div>
                <p className="panel-copy">
                  Le moteur, l’import CSV et l’analyse historique fonctionnent
                  sans IA. La connexion Crédit Agricole permet une lecture
                  manuelle suivie d’un aperçu à confirmer. La démonstration
                  utilise exclusivement une banque fictive. Les prévisions des
                  charges variables restent à développer.
                </p>
              </section>
            </>
          )}
        </main>
        <footer>
          <span>
            BudgetWard <span className="muted">· Prévision du foyer</span>
          </span>
          <span>Aucun virement bancaire n’est effectué par l’application.</span>
        </footer>
      </div>
      {dialog && (
        <Modal
          wide={dialog.type === "import"}
          title={
            dialog.type === "import"
              ? "Importer un relevé CSV"
              : dialog.type === "charge"
                ? "Ajouter une charge"
                : dialog.type === "budget"
                  ? "Ajouter un budget protégé"
                  : dialog.type === "plan"
                    ? "Réserve de " + monthLabel(month)
                    : dialog.type === "adjustment"
                      ? "Dépense ponctuelle du mois"
                      : dialog.type === "balance"
                        ? "Mettre à jour le solde"
                        : dialog.type === "transaction"
                          ? "Renseigner une opération réelle"
                          : dialog.type === "classify"
                            ? "Affecter l’opération"
                            : "item" in dialog
                              ? dialog.item.name
                              : ""
          }
          onClose={() => setDialog(null)}
        >
          {dialog.type === "import" && (
            <CsvImport
              accounts={data.accounts}
              demo={session.demo}
              onImported={load}
              onFinish={(destination, importedMonth) => {
                setDialog(null);
                if (importedMonth && importedMonth !== month) {
                  setMonth(importedMonth);
                  setState(null);
                }
                navigate(destination);
              }}
            />
          )}
          {dialog.type === "balance" && (
            <ActionForm
              onCancel={() => setDialog(null)}
              onSave={(f) =>
                save(
                  "/accounts/" + dialog.item.id,
                  {
                    name: f.get("name"),
                    balance_cents: cents(f.get("balance")),
                    balance_date: f.get("balance_date"),
                  },
                  "PUT",
                )
              }
            >
              <p className="dialog-copy">
                Recopiez le solde affiché dans votre banque. Il ne sera pas
                recalculé à partir des opérations saisies.
              </p>
              <Field
                label="Nom du compte"
                name="name"
                value={dialog.item.name}
              />
              <div className="form-grid">
                <Field
                  label="Solde constaté (€)"
                  name="balance"
                  value={decimal(dialog.item.balance_cents)}
                />
                <Field
                  label="Date du solde"
                  name="balance_date"
                  type="date"
                  value={localToday}
                  max={localToday}
                />
              </div>
            </ActionForm>
          )}
          {(dialog.type === "charge" || dialog.type === "budget") && (
            <ActionForm
              onCancel={() => setDialog(null)}
              submit={
                dialog.type === "charge" ? "Créer la charge" : "Créer le budget"
              }
              onSave={(f) =>
                save(dialog.type === "charge" ? "/charges" : "/budgets", {
                  name: f.get("name"),
                  amount_cents: cents(f.get("amount")),
                  frequency: f.get("frequency"),
                  anchor_date: f.get("anchor_date"),
                  ...(dialog.type === "charge"
                    ? {
                        end_date: f.get("end_date") || null,
                        installment_count: f.get("installment_count")
                          ? Number(f.get("installment_count"))
                          : null,
                      }
                    : {}),
                })
              }
            >
              <Field label="Nom" name="name" />
              <div className="form-grid">
                <Field
                  label={
                    dialog.type === "charge"
                      ? "Montant par échéance (€)"
                      : "Montant par occurrence (€)"
                  }
                  name="amount"
                />
                <Select
                  label="Fréquence"
                  name="frequency"
                  value={dialog.type === "charge" ? "MONTHLY" : "WEEKLY"}
                >
                  {Object.entries(frequencyLabel)
                    .filter(
                      ([key]) => dialog.type === "budget" || key !== "MANUAL",
                    )
                    .map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                </Select>
              </div>
              <Field
                label="Première date de référence"
                name="anchor_date"
                type="date"
                value={month + "-01"}
                hint={
                  dialog.type === "budget"
                    ? "Pour une fréquence hebdomadaire, choisissez le bon jour. Pour toutes les 2 semaines, cette date fixe aussi l’alternance."
                    : "Fixe le jour habituel et le début du calendrier des échéances."
                }
              />
              {dialog.type === "charge" ? (
                <details className="advanced">
                  <summary>
                    Charge temporaire ou paiement en plusieurs fois
                  </summary>
                  <Field
                    label="Date de fin incluse"
                    name="end_date"
                    type="date"
                    required={false}
                  />
                  <Field
                    label="Nombre total d’échéances"
                    name="installment_count"
                    type="number"
                    min={1}
                    max={600}
                    required={false}
                    hint="Pour une charge mensuelle, trimestrielle ou annuelle."
                  />
                </details>
              ) : (
                <p className="dialog-copy">
                  Le nombre d’occurrences peut ensuite être ajusté pour un mois,
                  sans modifier cette référence.
                </p>
              )}
            </ActionForm>
          )}
          {dialog.type === "plan" && (
            <ActionForm
              onCancel={() => setDialog(null)}
              onSave={(f) =>
                save(
                  "/plans/" + month,
                  {
                    safety_cents: cents(f.get("safety_amount")),
                    treasury_cents: cents(f.get("treasury_amount")),
                  },
                  "PUT",
                )
              }
            >
              <p className="dialog-copy">
                Ces montants concernent uniquement {monthLabel(month)} et sont
                conservés sur CHARGES.
              </p>
              <Field
                label="Marge de sécurité (€)"
                name="safety_amount"
                value={decimal(data.safety_cents)}
              />
              <Field
                label="Objectif de trésorerie (€)"
                name="treasury_amount"
                value={decimal(data.treasury_cents)}
                hint="Par exemple, une somme réservée à la réduction du découvert."
              />
            </ActionForm>
          )}
          {dialog.type === "adjustment" && (
            <ActionForm
              onCancel={() => setDialog(null)}
              onSave={(f) =>
                save("/plans/" + month + "/adjustments", {
                  name: f.get("name"),
                  amount_cents: cents(f.get("amount")),
                })
              }
            >
              <p className="dialog-copy">
                À protéger uniquement pour {monthLabel(month)}. Retirez cet
                ajustement lorsqu’il est payé pour ne plus le conserver dans le
                reste à protéger.
              </p>
              <Field label="Dépense prévue" name="name" />
              <Field label="Montant à réserver (€)" name="amount" />
            </ActionForm>
          )}
          {dialog.type === "charge-detail" && (
            <>
              <div className="detail-amount">
                <span>À protéger encore</span>
                <strong>{money(dialog.item.remaining_cents)}</strong>
              </div>
              <p className="dialog-copy">{dialog.item.explanation}</p>
              <dl className="detail-list">
                <div>
                  <dt>Prévu ce mois</dt>
                  <dd>{money(dialog.item.expected_cents)}</dd>
                </div>
                <div>
                  <dt>Paiements affectés</dt>
                  <dd>{money(dialog.item.paid_cents)}</dd>
                </div>
                <div>
                  <dt>Fréquence</dt>
                  <dd>{frequencyLabel[dialog.item.frequency]}</dd>
                </div>
                <div>
                  <dt>Échéances prévues</dt>
                  <dd>
                    {dialog.item.dates.map(shortDate).join(", ") || "Aucune"}
                  </dd>
                </div>
              </dl>
              <details className="advanced">
                <summary>Définir une nouvelle période tarifaire</summary>
                <p className="dialog-copy">
                  La règle précédente est conservée. La nouvelle somme
                  s’applique aux échéances à partir de la date choisie.
                </p>
                <ActionForm
                  submit="Créer la période tarifaire"
                  onSave={(f) =>
                    save("/charges/" + dialog.item.id + "/revisions", {
                      amount_cents: cents(f.get("amount")),
                      effective_from: f.get("effective_from"),
                    })
                  }
                >
                  <Field
                    label="Nouveau montant (€)"
                    name="amount"
                    value={decimal(dialog.item.amount_cents)}
                  />
                  <Field
                    label="À partir du"
                    name="effective_from"
                    type="date"
                    value={localToday}
                  />
                </ActionForm>
              </details>
            </>
          )}
          {dialog.type === "budget-detail" && (
            <>
              <div className="detail-amount">
                <span>À protéger encore</span>
                <strong>{money(dialog.item.remaining_cents)}</strong>
              </div>
              <div className="formula">
                {dialog.item.count} × {money(dialog.item.amount_cents)} −{" "}
                {money(dialog.item.funded_cents)} transférés
              </div>
              <p className="dialog-copy">{dialog.item.explanation}</p>
              <dl className="detail-list">
                <div>
                  <dt>Budget prévu</dt>
                  <dd>{money(dialog.item.expected_cents)}</dd>
                </div>
                <div>
                  <dt>Transféré vers DÉPENSES</dt>
                  <dd>{money(dialog.item.funded_cents)}</dd>
                </div>
                <div>
                  <dt>Consommé renseigné</dt>
                  <dd>{money(dialog.item.spent_cents)}</dd>
                </div>
              </dl>
              <ActionForm
                submit="Ajuster pour ce mois"
                onSave={(f) =>
                  save(
                    "/plans/" + month + "/budgets/" + dialog.item.id,
                    { count: Number(f.get("count")) },
                    "PUT",
                  )
                }
              >
                <Field
                  label={"Nombre d’occurrences en " + monthLabel(month)}
                  name="count"
                  type="number"
                  min={0}
                  max={100}
                  value={dialog.item.count}
                  hint="Cet ajustement ne change pas la référence des autres mois."
                />
              </ActionForm>
              {dialog.item.manual_count !== null && (
                <button
                  className="text-button"
                  onClick={async () => {
                    try {
                      await save(
                        "/plans/" + month + "/budgets/" + dialog.item.id,
                        { count: null },
                        "PUT",
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Revenir au calendrier automatique
                </button>
              )}
            </>
          )}
          {dialog.type === "transaction" && (
            <ActionForm
              onCancel={() => setDialog(null)}
              submit="Enregistrer l’opération"
              onSave={(f) =>
                save("/transactions", {
                  account_id: Number(f.get("account_id")),
                  booking_date: f.get("booking_date"),
                  operation_date: f.get("operation_date") || null,
                  amount_cents: cents(f.get("amount")),
                  raw_label: f.get("raw_label"),
                  provider_id: f.get("provider_id") || null,
                })
              }
            >
              <div className="notice">
                Recopiez une opération déjà comptabilisée. Son affectation se
                fait ensuite dans le tableau. Le solde du compte reste inchangé.
              </div>
              <Field label="Libellé bancaire" name="raw_label" />
              <Select label="Compte" name="account_id">
                {data.accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
              <div className="form-grid">
                <Field
                  label="Montant signé (€)"
                  name="amount"
                  hint="Ex. −161,50 pour un débit, 500 pour un crédit."
                />
                <Field
                  label="Date comptable"
                  name="booking_date"
                  type="date"
                  value={localToday}
                  max={localToday}
                />
              </div>
              <details className="advanced">
                <summary>Date d’achat et référence bancaire</summary>
                <Field
                  label="Date d’achat réelle"
                  name="operation_date"
                  type="date"
                  required={false}
                  max={localToday}
                />
                <Field
                  label="Référence unique fournie par la banque"
                  name="provider_id"
                  required={false}
                  hint="Facultative. Empêche une seconde saisie de cette référence sur ce compte."
                />
              </details>
            </ActionForm>
          )}
          {dialog.type === "classify" && (
            <ClassificationForm
              transaction={dialog.item}
              data={data}
              onSave={(body) =>
                save(
                  "/transactions/" + dialog.item.id + "/classification",
                  body,
                  "PUT",
                )
              }
              onCancel={() => setDialog(null)}
            />
          )}
        </Modal>
      )}
    </div>
  );
}

function ClassificationForm({
  transaction,
  data,
  onSave,
  onCancel,
}: {
  transaction: Transaction;
  data: Forecast;
  onSave: (body: unknown) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [kind, setKind] = useState(transaction.kind || "CHARGE");
  const targets = kind === "CHARGE" ? data.charges : data.budgets;
  return (
    <ActionForm
      onCancel={onCancel}
      onSave={(f) =>
        onSave({
          kind,
          target_id: ["CHARGE", "FUNDED", "SPENT"].includes(kind)
            ? Number(f.get("target_id"))
            : null,
          other_account_id: ["FUNDED", "INTERNAL"].includes(kind)
            ? Number(f.get("other_account_id"))
            : null,
        })
      }
    >
      <div className="operation-context">
        <ArrowDownLeft size={20} />
        <div>
          <strong>{transaction.raw_label}</strong>
          <small>
            {transaction.account_name} · {shortDate(transaction.booking_date)}
          </small>
        </div>
        <strong>{money(transaction.amount_cents)}</strong>
      </div>
      <label className="field">
        <span>Rôle de cette opération</span>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {Object.entries(kindLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {["CHARGE", "FUNDED", "SPENT"].includes(kind) && (
        <Select
          key={kind}
          label={kind === "CHARGE" ? "Charge concernée" : "Budget concerné"}
          name="target_id"
          value={transaction.charge_id || transaction.budget_id || undefined}
        >
          {!targets.length && (
            <option value="">
              Créez d’abord une{" "}
              {kind === "CHARGE" ? "charge" : "référence de budget"}
            </option>
          )}
          {targets.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      )}
      {["FUNDED", "INTERNAL"].includes(kind) && (
        <Select label="Autre compte du transfert" name="other_account_id">
          {data.accounts
            .filter((a) => a.id !== transaction.account_id)
            .map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
        </Select>
      )}
      <p className="dialog-copy">
        {kind === "FUNDED"
          ? "Affectez uniquement la sortie de CHARGES vers DÉPENSES. La contrepartie entrante doit être classée comme transfert interne."
          : kind === "SPENT"
            ? "Alimente le consommé réel. Ne réduit pas une seconde fois la protection de CHARGES."
            : kind === "CHARGE"
              ? "Ce paiement remplace une échéance attendue dans le reste à protéger."
              : kind === "INTERNAL"
                ? "Un transfert entre vos comptes ne constitue pas une dépense du foyer."
                : "L’opération reste visible et ne modifie aucune règle de prévision."}
      </p>
    </ActionForm>
  );
}
