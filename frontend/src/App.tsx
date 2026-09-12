import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  BadgeCheck,
  Banknote,
  BarChart3,
  ChevronRight,
  Download,
  FileSearch,
  LayoutDashboard,
  LogIn,
  Menu,
  Moon,
  Search,
  ShieldAlert,
  Sun,
  UploadCloud,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  AgentRun,
  Application,
  ApplicationPage,
  setAccessToken,
} from "./api";
const money = (v: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(v);
const statusClass = (s: string) => `badge ${s.toLowerCase()}`;

function Shell({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const navigate = useNavigate();
  const [dark, setDark] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [search, setSearch] = useState("");
  const links = [
    ["/", LayoutDashboard, "Overview"],
    ["/applications", FileSearch, "Applications"],
    ["/upload", UploadCloud, "Upload & Analyze"],
    ["/analytics", BarChart3, "Analytics"],
    ["/login", LogIn, "Sign in"],
  ] as const;
  return (
    <div className={dark ? "app dark" : "app"}>
      <aside className={menuOpen ? "open" : ""}>
        <div className="brand">
          <span>
            <Banknote />
          </span>
          <div>
            LoanLens<small>Decision Intelligence</small>
          </div>
        </div>
        <nav>
          {links.map(([to, Icon, label]) => (
            <Link
              key={to}
              onClick={() => setMenuOpen(false)}
              className={loc.pathname === to ? "active" : ""}
              to={to}
            >
              <Icon />
              {label}
            </Link>
          ))}
        </nav>
        <div className="side-foot">
          <div className="avatar">GR</div>
          <div>
            <b>Loan officer</b>
            <small>Human decision authority</small>
          </div>
        </div>
      </aside>
      <main>
        <header>
          <button
            className="mobile"
            aria-label="Open navigation"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <Menu />
          </button>
          <form
            className="search"
            onSubmit={(e) => {
              e.preventDefault();
              navigate(`/applications?q=${encodeURIComponent(search.trim())}`);
            }}
          >
            <Search />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search applications, customers..."
              aria-label="Search applications"
            />
          </form>
          <button
            className="icon"
            aria-label="Toggle color theme"
            onClick={() => setDark(!dark)}
          >
            {dark ? <Sun /> : <Moon />}
          </button>
        </header>
        {children}
      </main>
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: any;
  label: string;
  value: string | number;
  detail: string;
  tone: string;
}) {
  return (
    <div className="metric">
      <div className={`metric-icon ${tone}`}>
        <Icon />
      </div>
      <div>
        <p>{label}</p>
        <h2>{value}</h2>
        <small>{detail}</small>
      </div>
    </div>
  );
}
function Dashboard() {
  const { data: d } = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => (await api.get("/dashboard")).data,
  });
  if (!d) return <Loading />;
  const status = Object.entries(d.status_distribution).map(([name, value]) => ({
    name,
    value,
  }));
  return (
    <div className="page">
      <Title
        eyebrow={new Date()
          .toLocaleDateString("en-IN", {
            weekday: "long",
            day: "numeric",
            month: "long",
          })
          .toUpperCase()}
        title="Good morning, Gayathri"
        subtitle="Here’s what’s happening across your loan portfolio."
      />
      <div className="metrics">
        <Metric
          icon={FileSearch}
          label="Total applications"
          value={d.total_applications}
          detail="All processed cases"
          tone="blue"
        />
        <Metric
          icon={BadgeCheck}
          label="Approved loans"
          value={d.approved}
          detail="Strong credit profiles"
          tone="green"
        />
        <Metric
          icon={Activity}
          label="Pending review"
          value={d.pending}
          detail="Require officer action"
          tone="amber"
        />
        <Metric
          icon={ShieldAlert}
          label="Fraud alerts"
          value={d.fraud_alerts}
          detail="High attention signals"
          tone="red"
        />
      </div>
      <div className="grid-charts">
        <section className="card wide">
          <CardTitle
            title="Application volume"
            sub={`Monthly processing trend · ${d.monthly_year}`}
          />
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={d.monthly}>
              <defs>
                <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="#2857d7" stopOpacity=".3" />
                  <stop offset="1" stopColor="#2857d7" stopOpacity="0" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="applications"
                stroke="#2857d7"
                fill="url(#g)"
                strokeWidth={3}
                dot={{ r: 2, strokeWidth: 1 }}
                activeDot={{ r: 3, strokeWidth: 1 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </section>
        <section className="card">
          <CardTitle title="Decision mix" sub="Current portfolio" />
          <ResponsiveContainer width="100%" height={210}>
            <PieChart>
              <Pie
                data={status}
                innerRadius={55}
                outerRadius={82}
                dataKey="value"
                paddingAngle={4}
              >
                {status.map((_: any, i: number) => (
                  <Cell fill={["#23a36d", "#e6a127", "#df4b56"][i]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="legend">
            {status.map((x: any) => (
              <span>
                <i />
                {x.name} <b>{x.value}</b>
              </span>
            ))}
          </div>
        </section>
      </div>
      <Recent rows={d.recent} />
    </div>
  );
}
function Title({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow?: string;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="title">
      <div>
        {eyebrow && <small>{eyebrow}</small>}
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}
function CardTitle({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="card-title">
      <div>
        <h3>{title}</h3>
        <p>{sub}</p>
      </div>
    </div>
  );
}
function Recent({ rows }: { rows: Application[] }) {
  return (
    <section className="card table-card">
      <CardTitle
        title="Recent applications"
        sub="Latest applications analyzed by LoanLens AI"
      />
      <table>
        <thead>
          <tr>
            <th>Applicant</th>
            <th>Loan</th>
            <th>Amount</th>
            <th>Risk</th>
            <th>Fraud</th>
            <th>Decision</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((x) => (
            <tr>
              <td>
                <b>{x.applicant_name}</b>
                <small>{x.id}</small>
              </td>
              <td>{x.loan_type}</td>
              <td>{money(x.loan_amount)}</td>
              <td>
                <Score value={x.risk_score} />
              </td>
              <td>
                <Score value={x.fraud_score} />
              </td>
              <td>
                <span className={statusClass(x.status)}>{x.status}</span>
              </td>
              <td>
                <Link to={`/applications/${x.id}`}>
                  <ChevronRight />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
function Score({ value }: { value: number }) {
  return (
    <span className="score">
      <i
        style={{ width: `${value}%` }}
        className={value > 69 ? "high" : value > 39 ? "mid" : "low"}
      />
      <b>{value.toFixed(0)}</b>
    </span>
  );
}
function Applications() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page") || 1));
  const q = params.get("q") || "";
  const { data } = useQuery<ApplicationPage>({
    queryKey: ["applications", page, q],
    queryFn: async () =>
      (
        await api.get("/applications", {
          params: { page, page_size: 20, q: q || undefined },
        })
      ).data,
  });
  const move = (next: number) =>
    setParams((current) => {
      const copy = new URLSearchParams(current);
      copy.set("page", String(next));
      return copy;
    });
  return (
    <div className="page">
      <Title
        title="Loan applications"
        subtitle={
          q
            ? `Search results for “${q}”`
            : "Review every application and its AI-assisted decision."
        }
        action={
          <Link className="primary" to="/upload">
            <UploadCloud />
            Upload data
          </Link>
        }
      />
      <Recent rows={data?.items || []} />
      {data && data.pages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => move(page - 1)}>
            Previous
          </button>
          <span>
            Page {page} of {data.pages} · {data.total} records
          </span>
          <button disabled={page >= data.pages} onClick={() => move(page + 1)}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
function Upload() {
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [applicantName, setApplicantName] = useState("");
  const [loanType, setLoanType] = useState("Personal Loan");
  const mut = useMutation({
    mutationFn: async () => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      form.append("applicant_name", applicantName.trim());
      form.append("loan_type", loanType);
      return (await api.post("/upload", form)).data;
    },
    onSuccess: () => qc.invalidateQueries(),
  });
  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    setFiles((current) =>
      Array.from(
        new Map(
          [...current, ...Array.from(incoming)].map((file) => [
            `${file.name}-${file.size}`,
            file,
          ]),
        ).values(),
      ).slice(0, 25),
    );
  };
  return (
    <div className="page narrow">
      <Title
        title="Upload & analyze"
        subtitle="Analyze a complete applicant pack or multiple application files in one batch."
      />
      <section className="card upload">
        <div className="upload-icon">
          <UploadCloud />
        </div>
        <h2>Upload multiple loan documents</h2>
        <p>
          First identify the loan seeker, then attach up to 25 supporting
          documents.
        </p>
        <div className="upload-fields">
          <label>
            <span>Loan seeker name</span>
            <input
              value={applicantName}
              maxLength={160}
              placeholder="e.g. Priya Sharma"
              onChange={(e) => setApplicantName(e.target.value)}
            />
          </label>
          <label>
            <span>Type of loan</span>
            <select
              value={loanType}
              onChange={(e) => setLoanType(e.target.value)}
            >
              {[
                "Personal Loan",
                "Home Loan",
                "Car Loan",
                "Education Loan",
                "Business Loan",
                "Gold Loan",
              ].map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="file-help">
          CSV, Excel, JSON, text PDF, PNG, JPG or TIFF · maximum 1,000 records
          per structured file
        </div>
        <label className="primary">
          Choose files
          <input
            multiple
            type="file"
            accept=".csv,.xlsx,.xls,.pdf,.json,.png,.jpg,.jpeg,.tif,.tiff"
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        {files.length > 0 && (
          <div className="file-list">
            {files.map((file, index) => (
              <div className="chosen" key={`${file.name}-${file.size}`}>
                <FileSearch />
                <div>
                  <b>{file.name}</b>
                  <small>
                    {(file.size / 1024).toFixed(1)} KB · ready to analyze
                  </small>
                </div>
                <button
                  aria-label={`Remove ${file.name}`}
                  onClick={() =>
                    setFiles((items) => items.filter((_, i) => i !== index))
                  }
                >
                  <X />
                </button>
              </div>
            ))}
          </div>
        )}
        <button
          className="analyze"
          disabled={
            !files.length || applicantName.trim().length < 2 || mut.isPending
          }
          onClick={() => mut.mutate()}
        >
          {mut.isPending
            ? `Analyzing ${files.length} files…`
            : `Analyze ${files.length} file${files.length === 1 ? "" : "s"} for ${applicantName.trim() || "applicant"}`}
          <ArrowUpRight />
        </button>
        {mut.isSuccess && (
          <div className="batch-result">
            <div className="success">
              <BadgeCheck />
              <div>
                <b>Batch analysis complete</b>
                <p>
                  {mut.data.created} applications created from{" "}
                  {mut.data.files_analyzed} of {mut.data.files_received} files ·{" "}
                  {mut.data.duplicates_skipped} duplicates skipped
                </p>
              </div>
            </div>
            {mut.data.results.map((result: any) => (
              <div
                className={`file-result ${result.status}`}
                key={result.filename}
              >
                <FileSearch />
                <b>{result.filename}</b>
                <span>
                  {result.status === "analyzed"
                    ? `${result.records} record${result.records === 1 ? "" : "s"} analyzed`
                    : result.error}
                </span>
              </div>
            ))}
          </div>
        )}
        {mut.isError && (
          <div className="error">
            No applications could be extracted. Review the file formats and try
            again.
          </div>
        )}
      </section>
      <div className="steps">
        {[
          "Validate & clean",
          "Extract fields",
          "Detect anomalies",
          "Score & recommend",
        ].map((x, i) => (
          <div>
            <span>{i + 1}</span>
            <b>{x}</b>
            <small>
              {
                [
                  "Schema checks and deduplication",
                  "Normalize applicant financials",
                  "Fraud and sentiment signals",
                  "Explainable loan decision",
                ][i]
              }
            </small>
          </div>
        ))}
      </div>
    </div>
  );
}
function Detail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const [question, setQuestion] = useState(
    "What fraud, income, and eligibility evidence should a loan officer review?",
  );
  const [overrideStatus, setOverrideStatus] = useState("REVIEW");
  const [overrideReason, setOverrideReason] = useState("");
  const { data: x } = useQuery<Application>({
    queryKey: ["application", id],
    queryFn: async () => (await api.get(`/applications/${id}`)).data,
  });
  const { data: runs = [] } = useQuery<AgentRun[]>({
    queryKey: ["agent-runs", id],
    queryFn: async () => (await api.get(`/applications/${id}/agent/runs`)).data,
    enabled: !!id,
  });
  const ask = useMutation<AgentRun>({
    mutationFn: async () =>
      (
        await api.post(`/applications/${id}/agent/query`, {
          question,
          top_k: 5,
        })
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-runs", id] });
    },
  });
  const override = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/applications/${id}/override`, {
          new_status: overrideStatus,
          reason: overrideReason,
        })
      ).data,
    onSuccess: () => {
      setOverrideReason("");
      qc.invalidateQueries({ queryKey: ["application", id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const active = ask.data || runs[0];
  if (!x) return <Loading />;
  return (
    <div className="page">
      <Title
        title={x.applicant_name}
        subtitle={`${x.id} · received ${new Date(x.created_at).toLocaleDateString("en-IN")}`}
        action={
          <a
            className="secondary"
            href={`${api.defaults.baseURL}/reports/applications.csv`}
          >
            <Download />
            Download report
          </a>
        }
      />
      <div className="detail-grid">
        <section className="card profile">
          <h3>Applicant profile</h3>
          <dl>
            <div>
              <dt>Annual income</dt>
              <dd>{money(x.income)}</dd>
            </div>
            <div>
              <dt>Requested amount</dt>
              <dd>{money(x.loan_amount)}</dd>
            </div>
            <div>
              <dt>Credit score</dt>
              <dd>{x.credit_score}</dd>
            </div>
            <div>
              <dt>Debt-to-income</dt>
              <dd>{x.dti.toFixed(1)}%</dd>
            </div>
            <div>
              <dt>Employment</dt>
              <dd>{x.employment_years} years</dd>
            </div>
            <div>
              <dt>Sentiment</dt>
              <dd>
                <span className="badge neutral">
                  {x.sentiment} · {(x.sentiment_confidence * 100).toFixed(0)}%
                </span>
              </dd>
            </div>
          </dl>
        </section>
        <section className="card decision">
          <span>AGENTIC RECOMMENDATION</span>
          <h2 className={x.status.toLowerCase()}>{x.status}</h2>
          <p>{x.ai_summary}</p>
          <div className="gauges">
            <div>
              <b>{x.risk_score.toFixed(0)}</b>
              <small>Risk score</small>
            </div>
            <div>
              <b>{x.fraud_score.toFixed(0)}</b>
              <small>Fraud score</small>
            </div>
          </div>
          <details className="override">
            <summary>Record officer override</summary>
            <select
              value={overrideStatus}
              onChange={(event) => setOverrideStatus(event.target.value)}
            >
              <option>APPROVE</option>
              <option>REVIEW</option>
              <option>REJECT</option>
            </select>
            <textarea
              value={overrideReason}
              minLength={10}
              placeholder="Required reason for the final decision"
              onChange={(event) => setOverrideReason(event.target.value)}
            />
            <button
              disabled={overrideReason.trim().length < 10 || override.isPending}
              onClick={() => override.mutate()}
            >
              {override.isPending ? "Recording…" : "Record decision"}
            </button>
            {override.isSuccess && <small>Override recorded in the audit log.</small>}
          </details>
        </section>
        <section className="card reasoning">
          <h3>Decision reasoning</h3>
          <p>{x.explanation}</p>
          <h4>Processing trail</h4>
          {x.processing_log.map((t, i) => (
            <div className="log" key={`${t}-${i}`}>
              <BadgeCheck />
              {t}
            </div>
          ))}
        </section>
        <section className="card agent-panel">
          <div className="agent-head">
            <div>
              <h3>Evidence agent</h3>
              <p>
                Ask about fraud signals, income, eligibility, or missing
                documents. Every factual answer is citation-verified.
              </p>
            </div>
            {active && (
              <span
                className={`verify ${active.verification.verified ? "pass" : "fail"}`}
              >
                {active.verification.verified ? "Grounded" : "Review needed"} ·{" "}
                {(active.verification.groundedness * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <div className="agent-query">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && question.trim().length >= 3)
                  ask.mutate();
              }}
            />
            <button
              className="primary"
              disabled={question.trim().length < 3 || ask.isPending}
              onClick={() => ask.mutate()}
            >
              <Search />
              {ask.isPending ? "Investigating…" : "Ask agents"}
            </button>
          </div>
          {ask.isError && (
            <div className="error">
              The agent run failed. Please retry or inspect the API logs.
            </div>
          )}
          {active && (
            <div className="agent-result">
              <div className="agent-answer">
                {active.answer.split("\n").map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
              {active.fraud_assessment.signals.length > 0 && (
                <div className="signals">
                  <h4>Fraud signals</h4>
                  {active.fraud_assessment.signals.map((signal) => (
                    <div key={signal.code}>
                      <ShieldAlert />
                      <span>
                        <b>
                          {signal.severity} · {signal.code.replaceAll("_", " ")}
                        </b>
                        <small>{signal.description}</small>
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <details>
                <summary>
                  Agent trace · {active.trace.length} steps ·{" "}
                  {active.retrieved_evidence.length} evidence chunks
                </summary>
                <div className="trace">
                  {active.trace.map((step, i) => (
                    <span key={`${step.agent}-${i}`}>
                      <b>{i + 1}</b>
                      {step.agent.replaceAll("_", " ")}
                    </span>
                  ))}
                </div>
                <div className="evidence">
                  {active.retrieved_evidence.map((item) => (
                    <div key={item.id}>
                      <b>[{item.id}]</b>
                      <small>
                        {item.source} · score {item.score.toFixed(2)}
                      </small>
                      <p>{item.text}</p>
                    </div>
                  ))}
                </div>
              </details>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
function Analytics() {
  const { data } = useQuery({
    queryKey: ["analytics"],
    queryFn: async () => (await api.get("/analytics")).data,
  });
  if (!data) return <Loading />;
  const chart = (o: any) =>
    Object.entries(o).map(([name, value]) => ({ name, value }));
  return (
    <div className="page">
      <Title
        title="Portfolio analytics"
        subtitle="Understand risk, fraud and customer sentiment across the lending funnel."
        action={
          <a
            className="secondary"
            href={`${api.defaults.baseURL}/reports/applications.csv`}
          >
            <Download />
            Export CSV
          </a>
        }
      />
      <div className="analytics-grid">
        {[
          ["Risk categories", data.risk],
          ["Fraud distribution", data.fraud],
          ["Sentiment analysis", data.sentiment],
        ].map(([title, d]: any) => (
          <section className="card">
            <CardTitle title={title} sub="Analyzed applications" />
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chart(d)}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#2857d7" radius={[7, 7, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </section>
        ))}
      </div>
    </div>
  );
}
function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: async () =>
      (await api.post("/auth/login", { username, password })).data,
    onSuccess: (data) => {
      setAccessToken(data.access_token);
      navigate("/");
    },
  });
  return (
    <div className="page narrow">
      <Title
        title="Secure sign in"
        subtitle="Use your LoanLens officer or governance account."
      />
      <section className="card login-card">
        <div className="upload-icon">
          <ShieldAlert />
        </div>
        <label>
          <span>Username</span>
          <input
            value={username}
            autoComplete="username"
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label>
          <span>Password</span>
          <input
            value={password}
            type="password"
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && username && password) login.mutate();
            }}
          />
        </label>
        <button
          className="analyze"
          disabled={!username || !password || login.isPending}
          onClick={() => login.mutate()}
        >
          <LogIn />
          {login.isPending ? "Signing in…" : "Sign in"}
        </button>
        {login.isError && (
          <div className="error">
            Invalid credentials or authentication is not configured.
          </div>
        )}
        <small>
          Active scoring remains local. Your role controls access to officer and
          governance actions.
        </small>
      </section>
    </div>
  );
}
function Loading() {
  return (
    <div className="loading">
      <span />
      Loading intelligence…
    </div>
  );
}
export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/applications" element={<Applications />} />
        <Route path="/applications/:id" element={<Detail />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/login" element={<Login />} />
      </Routes>
    </Shell>
  );
}
