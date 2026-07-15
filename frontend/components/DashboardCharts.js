'use client';

import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { motion } from 'motion/react';
import { TrendingUp, PieChart as PieChartIcon, BarChart3 } from 'lucide-react';
import './DashboardCharts.css';

/* ============================================================
   Constants
   ============================================================ */

const SEVERITY_COLORS = {
  low: '#059669',
  moderate: '#D97706',
  high: '#DC2626',
  critical: '#991B1B',
};

const SEVERITY_ORDER = ['low', 'moderate', 'high', 'critical'];

const LINE_TOTAL_COLOR = '#2563EB';
const LINE_COMPLETED_COLOR = '#059669';

const STAGGER_PARENT = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.15 },
  },
};

const STAGGER_CHILD = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: 'easeOut' },
  },
};

/* ============================================================
   Helpers
   ============================================================ */

/**
 * Build the last‑14‑days trend data from an array of jobs.
 * Returns an array of { date, dateLabel, total, completed }.
 */
function buildTrendData(jobs) {
  const now = new Date();
  const days = 14;

  // Map: 'YYYY-MM-DD' → { total, completed }
  const buckets = {};
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const key = toDateKey(d);
    buckets[key] = { total: 0, completed: 0 };
  }

  jobs.forEach((job) => {
    const key = toDateKey(new Date(job.created_at));
    if (buckets[key] !== undefined) {
      buckets[key].total += 1;
      if (job.status === 'completed') {
        buckets[key].completed += 1;
      }
    }
  });

  return Object.entries(buckets).map(([key, counts]) => ({
    date: key,
    dateLabel: formatShortDate(key),
    total: counts.total,
    completed: counts.completed,
  }));
}

/**
 * Build severity distribution from jobs that have a result.
 * Returns { data: [{ name, value, color }], total: number }.
 */
function buildSeverityData(jobs) {
  const counts = { low: 0, moderate: 0, high: 0, critical: 0 };

  jobs.forEach((job) => {
    const severity = job.result?.severity_overall?.toLowerCase();
    if (severity && counts[severity] !== undefined) {
      counts[severity] += 1;
    }
  });

  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  const data = SEVERITY_ORDER
    .filter((key) => counts[key] > 0)
    .map((key) => ({
      name: key,
      value: counts[key],
      color: SEVERITY_COLORS[key],
    }));

  return { data, total };
}

function toDateKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function formatShortDate(key) {
  const [, m, d] = key.split('-');
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return `${months[parseInt(m, 10) - 1]} ${parseInt(d, 10)}`;
}

/* ============================================================
   Custom Tooltip (Line Chart)
   ============================================================ */

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  return (
    <div className="customTooltip">
      <div className="tooltipDate">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="tooltipRow">
          <span
            className="tooltipDot"
            style={{ background: entry.color }}
          />
          <span className="tooltipLabel">{entry.name}</span>
          <span className="tooltipValue">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

/* ============================================================
   Custom Tooltip (Pie Chart)
   ============================================================ */

function SeverityTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { name, value, payload: item } = payload[0];

  return (
    <div className="customTooltip">
      <div className="tooltipRow">
        <span
          className="tooltipDot"
          style={{ background: item.color }}
        />
        <span className="tooltipLabel" style={{ textTransform: 'capitalize' }}>
          {name}
        </span>
        <span className="tooltipValue">{value}</span>
      </div>
    </div>
  );
}

/* ============================================================
   Custom Legend (Pie Chart)
   ============================================================ */

function SeverityLegend({ data, total }) {
  return (
    <div className="legendContainer">
      {data.map((entry) => {
        const pct = total > 0
          ? ((entry.value / total) * 100).toFixed(0)
          : 0;

        return (
          <div key={entry.name} className="legendItem">
            <span
              className="legendDot"
              style={{ background: entry.color }}
            />
            <span className="legendLabel">{entry.name}</span>
            <span className="legendCount">{entry.value}</span>
            <span className="legendPercent">({pct}%)</span>
          </div>
        );
      })}
    </div>
  );
}

/* ============================================================
   Empty State
   ============================================================ */

function EmptyChart({ message = 'No data available' }) {
  return (
    <div className="emptyChart">
      <BarChart3 size={40} strokeWidth={1.2} className="emptyChartIcon" />
      <span>{message}</span>
    </div>
  );
}

/* ============================================================
   Main Component
   ============================================================ */

export default function DashboardCharts({ jobs = [] }) {
  const trendData = useMemo(() => buildTrendData(jobs), [jobs]);
  const { data: severityData, total: severityTotal } = useMemo(
    () => buildSeverityData(jobs),
    [jobs],
  );

  const hasTrendData = trendData.some((d) => d.total > 0);
  const hasSeverityData = severityData.length > 0;

  return (
    <motion.div
      className="chartsContainer"
      variants={STAGGER_PARENT}
      initial="hidden"
      animate="visible"
    >
      {/* ── Analysis Trend ────────────────────────────────────── */}
      <motion.div className="chartCard" variants={STAGGER_CHILD}>
        <div className="chartHeader">
          <div className="chartIcon">
            <TrendingUp size={18} />
          </div>
          <div>
            <h3 className="chartTitle">Analysis Trend</h3>
            <p className="chartSubtitle">Last 14 days</p>
          </div>
        </div>

        {hasTrendData ? (
          <div className="lineChartWrapper">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={trendData}
                margin={{ top: 8, right: 16, left: -12, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--border)"
                  vertical={false}
                />
                <XAxis
                  dataKey="dateLabel"
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--border)' }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip content={<TrendTooltip />} />
                <Line
                  type="monotone"
                  dataKey="total"
                  name="Total"
                  stroke={LINE_TOTAL_COLOR}
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: LINE_TOTAL_COLOR, strokeWidth: 0 }}
                  activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
                  animationDuration={1200}
                  animationEasing="ease-out"
                />
                <Line
                  type="monotone"
                  dataKey="completed"
                  name="Completed"
                  stroke={LINE_COMPLETED_COLOR}
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: LINE_COMPLETED_COLOR, strokeWidth: 0 }}
                  activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
                  animationDuration={1200}
                  animationEasing="ease-out"
                  animationBegin={300}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChart message="No analyses in the last 14 days" />
        )}
      </motion.div>

      {/* ── Severity Distribution ─────────────────────────────── */}
      <motion.div className="chartCard" variants={STAGGER_CHILD}>
        <div className="chartHeader">
          <div className="chartIcon">
            <PieChartIcon size={18} />
          </div>
          <div>
            <h3 className="chartTitle">Severity Distribution</h3>
            <p className="chartSubtitle">Across all analyses</p>
          </div>
        </div>

        {hasSeverityData ? (
          <>
            <div className="pieChartWrapper">
              {/* Center label */}
              <div className="centerLabel">
                <span className="centerCount">{severityTotal}</span>
                <span className="centerCountLabel">Total</span>
              </div>

              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={severityData}
                    cx="50%"
                    cy="50%"
                    innerRadius="58%"
                    outerRadius="82%"
                    paddingAngle={3}
                    dataKey="value"
                    nameKey="name"
                    strokeWidth={0}
                    animationDuration={1000}
                    animationEasing="ease-out"
                  >
                    {severityData.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={entry.color}
                        style={{ outline: 'none' }}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<SeverityTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <SeverityLegend data={severityData} total={severityTotal} />
          </>
        ) : (
          <EmptyChart message="No severity data available" />
        )}
      </motion.div>
    </motion.div>
  );
}
