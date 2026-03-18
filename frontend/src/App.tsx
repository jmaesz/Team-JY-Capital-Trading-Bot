import { useEffect, useState, useCallback } from "react";
import {
  TrendingUp, TrendingDown, DollarSign, Activity,
  RefreshCw, Play, Square, BarChart2, WifiOff, RotateCcw,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card";
import { Badge } from "./components/ui/badge";
import { cn } from "./lib/utils";

const API = "https://enhancements-headers-funk-implied.trycloudflare.com";

// ── Coin icon with letter fallback ────────────────────────────────────────────
const ICON_BASE = "https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@master/svg/color";

function CoinIcon({ coin }: { coin: string }) {
  const [failed, setFailed] = useState(false);
  const symbol = coin.toLowerCase();

  if (failed) {
    return (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-muted text-[10px] font-bold text-muted-foreground shrink-0">
        {coin.slice(0, 2)}
      </span>
    );
  }

  return (
    <img
      src={`${ICON_BASE}/${symbol}.svg`}
      alt={coin}
      className="h-6 w-6 rounded-full shrink-0"
      onError={() => setFailed(true)}
    />
  );
}

interface Portfolio {
  total: number; cash: number; pnl: number; pnl_pct: number;
  drawdown_pct: number; peak: number; initial_wallet: number;
  holdings: { coin: string; qty: number; value: number; price: number }[];
}
interface Trade {
  timestamp_utc: string; coin: string; side: string;
  quantity: string; price_usd: string; trade_value_usd: string;
  signal_score: string; portfolio_value_usd: string;
  reason: string; api_success: string;
}
interface Metrics {
  sharpe: number | null; sortino: number | null;
  calmar: number | null; max_drawdown_pct: number;
}
interface ChartPoint { time: string; value: number }
interface BotStatus  { running: boolean; last_cycle: string | null }

function fmt(n: number) {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtMetric(v: number | null) {
  return v === null ? "—" : v.toFixed(3);
}

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({
  title, value, sub, icon: Icon, positive, small,
}: {
  title: string; value: string; sub?: string;
  icon: React.ElementType; positive?: boolean; small?: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{title}</CardTitle>
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent>
        <p className={cn(
          "font-bold",
          small ? "text-xl" : "text-2xl",
          positive === true  && "text-emerald-400",
          positive === false && "text-red-400",
          positive === undefined && "text-foreground",
        )}>
          {value}
        </p>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

// ── Custom chart tooltip ───────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-2 text-sm shadow-lg">
      <p className="text-muted-foreground mb-1">{label}</p>
      <p className="font-bold text-emerald-400">${fmt(payload[0].value)}</p>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades,    setTrades]    = useState<Trade[]>([]);
  const [metrics,   setMetrics]   = useState<Metrics | null>(null);
  const [history,   setHistory]   = useState<ChartPoint[]>([]);
  const [status,    setStatus]    = useState<BotStatus | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [botLoading, setBotLoading]       = useState(false);
  const [resetLoading, setResetLoading]   = useState(false);
  const [confirmReset, setConfirmReset]   = useState(false);
  const [connected, setConnected]         = useState(true);
  const [error, setError]                 = useState<string | null>(null);
  const [success, setSuccess]             = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [pRes, tRes, mRes, hRes, sRes] = await Promise.all([
        fetch(`${API}/api/portfolio`),
        fetch(`${API}/api/trades`),
        fetch(`${API}/api/metrics`),
        fetch(`${API}/api/portfolio/history`),
        fetch(`${API}/api/status`),
      ]);
      setPortfolio(await pRes.json());
      setTrades(await tRes.json());
      setMetrics(await mRes.json());
      setHistory(await hRes.json());
      setStatus(await sRes.json());
      setLastRefresh(new Date());
      setConnected(true);
    } catch {
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 30_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  async function resetBot() {
    setConfirmReset(false);
    setResetLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res  = await fetch(`${API}/api/bot/reset`, { method: "POST" });
      const body = await res.json();
      if (!body.ok) {
        setError(body.message ?? "Reset failed");
      } else {
        setSuccess(`Reset complete. Sold: ${body.sold?.length > 0 ? body.sold.join(", ") : "no open positions"}.`);
      }
      await new Promise(r => setTimeout(r, 800));
      await fetchAll();
    } catch {
      setError("Server unreachable.");
    }
    setResetLoading(false);
  }

  async function toggleBot() {
    if (!connected) {
      setError("Cannot reach server. Run: python server.py");
      return;
    }
    setBotLoading(true);
    setError(null);
    try {
      const endpoint = status?.running ? "/api/bot/stop" : "/api/bot/start";
      const res  = await fetch(`${API}${endpoint}`, { method: "POST" });
      const body = await res.json();
      if (!body.ok) setError(body.message ?? "Unknown error");
      await fetchAll();
    } catch {
      setError("Server unreachable. Make sure python server.py is running.");
    }
    setBotLoading(false);
  }

  const pnlPositive = portfolio ? portfolio.pnl >= 0 : undefined;
  const initialWallet = portfolio?.initial_wallet ?? 50_000;

  // Y-axis domain with 5% padding
  const yMin = history.length > 1
    ? Math.floor(Math.min(...history.map(p => p.value)) * 0.97 / 1000) * 1000
    : 45000;
  const yMax = history.length > 1
    ? Math.ceil( Math.max(...history.map(p => p.value)) * 1.03 / 1000) * 1000
    : 55000;

  return (
    <div className="min-h-screen bg-background p-6 space-y-6">

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Team JY Capital</h1>
          <p className="text-sm text-muted-foreground">Roostoo Trading Bot Dashboard</p>
        </div>
        <div className="flex items-center gap-3">

          {/* Connection indicator */}
          <span className={cn("h-2 w-2 rounded-full", connected ? "bg-emerald-400" : "bg-red-400")} />

          {/* Bot status badge */}
          {status && (
            <Badge variant={status.running ? "success" : "danger"}>
              {status.running ? "Bot Running" : "Bot Stopped"}
            </Badge>
          )}

          {/* Start / Stop button */}
          <button
            onClick={toggleBot}
            disabled={botLoading || resetLoading}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50",
              status?.running
                ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                : "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30"
            )}
          >
            {botLoading
              ? <><RefreshCw className="h-3.5 w-3.5 animate-spin" /> Working...</>
              : status?.running
                ? <><Square className="h-3.5 w-3.5" /> Stop Trading</>
                : <><Play   className="h-3.5 w-3.5" /> Start Trading</>
            }
          </button>

          {/* Reset button — two-step inline confirm */}
          {!confirmReset ? (
            <button
              onClick={() => setConfirmReset(true)}
              disabled={botLoading || resetLoading}
              className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors disabled:opacity-50"
            >
              {resetLoading
                ? <><RefreshCw className="h-3.5 w-3.5 animate-spin" /> Resetting...</>
                : <><RotateCcw className="h-3.5 w-3.5" /> Reset</>
              }
            </button>
          ) : (
            <div className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-1.5">
              <span className="text-xs text-red-400">Sure?</span>
              <button
                onClick={resetBot}
                className="text-xs font-medium text-red-400 hover:text-red-300 transition-colors"
              >
                Yes, reset
              </button>
              <span className="text-red-500/40">|</span>
              <button
                onClick={() => setConfirmReset(false)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancel
              </button>
            </div>
          )}

          {/* Refresh */}
          <button
            onClick={fetchAll}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {lastRefresh ? lastRefresh.toLocaleTimeString() : "—"}
          </button>
        </div>
      </div>

      {/* ── Server offline banner ── */}
      {!connected && (
        <div className="flex items-center gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <WifiOff className="h-4 w-4 shrink-0" />
          <span>
            Cannot reach the API server. Open a terminal and run:{" "}
            <code className="font-mono bg-red-500/20 px-1.5 py-0.5 rounded">python server.py</code>
          </span>
        </div>
      )}

      {/* ── Error message ── */}
      {error && (
        <div className="flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 hover:text-red-300">✕</button>
        </div>
      )}

      {/* ── Success message ── */}
      {success && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-400">
          <span>{success}</span>
          <button onClick={() => setSuccess(null)} className="ml-4 hover:text-emerald-300">✕</button>
        </div>
      )}

      {/* ── Top stat cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Portfolio Value"
          value={portfolio ? `$${fmt(portfolio.total)}` : "—"}
          sub={portfolio ? `Peak $${fmt(portfolio.peak)}` : undefined}
          icon={DollarSign}
        />
        <StatCard
          title="Total P&L"
          value={portfolio ? `${pnlPositive ? "+" : ""}$${fmt(portfolio.pnl)}` : "—"}
          sub={portfolio ? `${pnlPositive ? "+" : ""}${portfolio.pnl_pct.toFixed(2)}% vs start` : undefined}
          icon={pnlPositive ? TrendingUp : TrendingDown}
          positive={pnlPositive}
        />
        <StatCard
          title="USD Cash"
          value={portfolio ? `$${fmt(portfolio.cash)}` : "—"}
          sub={portfolio ? `${((portfolio.cash / portfolio.total) * 100).toFixed(1)}% of portfolio` : undefined}
          icon={DollarSign}
        />
        <StatCard
          title="Drawdown"
          value={portfolio ? `${portfolio.drawdown_pct.toFixed(2)}%` : "—"}
          sub="From portfolio peak"
          icon={Activity}
          positive={
            portfolio
              ? portfolio.drawdown_pct < 5 ? true : portfolio.drawdown_pct > 10 ? false : undefined
              : undefined
          }
        />
      </div>

      {/* ── Risk metrics ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Sharpe Ratio"
          value={fmtMetric(metrics?.sharpe ?? null)}
          sub="Return / total volatility"
          icon={BarChart2}
          positive={metrics?.sharpe !== null && metrics?.sharpe !== undefined ? metrics.sharpe > 1 ? true : metrics.sharpe < 0 ? false : undefined : undefined}
          small
        />
        <StatCard
          title="Sortino Ratio"
          value={fmtMetric(metrics?.sortino ?? null)}
          sub="Return / downside volatility"
          icon={BarChart2}
          positive={metrics?.sortino !== null && metrics?.sortino !== undefined ? metrics.sortino > 1 ? true : metrics.sortino < 0 ? false : undefined : undefined}
          small
        />
        <StatCard
          title="Calmar Ratio"
          value={fmtMetric(metrics?.calmar ?? null)}
          sub="Return / max drawdown"
          icon={BarChart2}
          positive={metrics?.calmar !== null && metrics?.calmar !== undefined ? metrics.calmar > 1 ? true : metrics.calmar < 0 ? false : undefined : undefined}
          small
        />
        <StatCard
          title="Max Drawdown"
          value={metrics ? `${metrics.max_drawdown_pct.toFixed(2)}%` : "—"}
          sub="Largest peak-to-trough drop"
          icon={TrendingDown}
          positive={metrics ? metrics.max_drawdown_pct < 5 ? true : metrics.max_drawdown_pct > 10 ? false : undefined : undefined}
          small
        />
      </div>

      {/* ── Portfolio chart ── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold text-foreground">Portfolio Value Over Time</CardTitle>
        </CardHeader>
        <CardContent>
          {history.length > 1 ? (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={history} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#34d399" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0}    />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(216 34% 17%)" />
                <XAxis
                  dataKey="time"
                  tick={{ fill: "hsl(215.4 16.3% 56.9%)", fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[yMin, yMax]}
                  tick={{ fill: "hsl(215.4 16.3% 56.9%)", fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip content={<ChartTooltip />} />
                <ReferenceLine
                  y={initialWallet}
                  stroke="hsl(215.4 16.3% 40%)"
                  strokeDasharray="4 4"
                  label={{ value: "Start", fill: "hsl(215.4 16.3% 56.9%)", fontSize: 11, position: "insideTopLeft" }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#34d399"
                  strokeWidth={2}
                  fill="url(#grad)"
                  dot={false}
                  activeDot={{ r: 4, fill: "#34d399" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[280px] flex items-center justify-center text-muted-foreground text-sm">
              Chart will populate once the bot starts trading
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Holdings + Recent Trades ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Holdings */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold text-foreground">Current Holdings</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {portfolio && portfolio.holdings.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {["Coin","Qty","Price","Value"].map((h, i) => (
                      <th key={h} className={cn("py-3 px-6 text-muted-foreground font-medium", i > 0 ? "text-right" : "text-left")}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {portfolio.holdings.map((h) => (
                    <tr key={h.coin} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-2 font-medium">
                          <CoinIcon coin={h.coin} />
                          {h.coin}
                        </div>
                      </td>
                      <td className="px-6 py-3 text-right text-muted-foreground">{h.qty.toFixed(4)}</td>
                      <td className="px-6 py-3 text-right text-muted-foreground">${fmt(h.price)}</td>
                      <td className="px-6 py-3 text-right font-medium">${fmt(h.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="px-6 py-10 text-center text-muted-foreground text-sm">No open positions</p>
            )}
          </CardContent>
        </Card>

        {/* Recent Trades */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold text-foreground">Recent Trades</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {trades.length > 0 ? (
              <div className="overflow-y-auto max-h-[320px]">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card">
                    <tr className="border-b border-border">
                      {["Time","Coin","Side","Value","Score"].map((h, i) => (
                        <th key={h} className={cn("py-3 px-4 text-muted-foreground font-medium", i > 1 ? "text-right" : "text-left")}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {trades.slice(0, 50).map((t, i) => (
                      <tr key={i} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-2.5 text-muted-foreground text-xs whitespace-nowrap">
                          {t.timestamp_utc ? new Date(t.timestamp_utc).toLocaleTimeString() : "—"}
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2 font-medium">
                            <CoinIcon coin={t.coin} />
                            {t.coin}
                          </div>
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge variant={t.side === "BUY" ? "success" : "danger"}>{t.side}</Badge>
                        </td>
                        <td className="px-4 py-2.5 text-right">${fmt(Number(t.trade_value_usd))}</td>
                        <td className={cn(
                          "px-4 py-2.5 text-right font-mono text-xs",
                          Number(t.signal_score) >= 0 ? "text-emerald-400" : "text-red-400",
                        )}>
                          {Number(t.signal_score) >= 0 ? "+" : ""}{Number(t.signal_score).toFixed(3)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="px-6 py-10 text-center text-muted-foreground text-sm">No trades yet</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Full trade log ── */}
      {trades.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold text-foreground">
              Full Trade Log
              <span className="ml-2 text-sm font-normal text-muted-foreground">({trades.length} trades)</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto overflow-y-auto max-h-[400px]">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card">
                  <tr className="border-b border-border">
                    {["Timestamp","Coin","Side","Qty","Price","Value","Signal","Portfolio","Reason","OK"].map((h, i) => (
                      <th key={h} className={cn("py-3 px-4 text-muted-foreground font-medium whitespace-nowrap", i > 2 ? "text-right" : "text-left")}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => (
                    <tr key={i} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-2.5 text-muted-foreground text-xs whitespace-nowrap">{t.timestamp_utc}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2 font-medium">
                          <CoinIcon coin={t.coin} />
                          {t.coin}
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant={t.side === "BUY" ? "success" : "danger"}>{t.side}</Badge>
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs">{Number(t.quantity).toFixed(4)}</td>
                      <td className="px-4 py-2.5 text-right">${fmt(Number(t.price_usd))}</td>
                      <td className="px-4 py-2.5 text-right">${fmt(Number(t.trade_value_usd))}</td>
                      <td className={cn(
                        "px-4 py-2.5 text-right font-mono text-xs",
                        Number(t.signal_score) >= 0 ? "text-emerald-400" : "text-red-400",
                      )}>
                        {Number(t.signal_score) >= 0 ? "+" : ""}{Number(t.signal_score).toFixed(3)}
                      </td>
                      <td className="px-4 py-2.5 text-right">${fmt(Number(t.portfolio_value_usd))}</td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">{t.reason}</td>
                      <td className="px-4 py-2.5 text-right">
                        <Badge variant={t.api_success === "True" ? "success" : "danger"}>
                          {t.api_success === "True" ? "OK" : "Fail"}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <p className="text-center text-xs text-muted-foreground pb-4">Auto-refreshes every 30 s</p>
    </div>
  );
}
