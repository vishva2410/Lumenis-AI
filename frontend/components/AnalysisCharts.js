'use client';

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { motion } from 'motion/react';
import { BarChart3, SearchX } from 'lucide-react';
import './AnalysisCharts.css';

const SEVERITY_COLORS = {
  low: '#059669',
  moderate: '#D97706',
  high: '#DC2626',
  critical: '#991B1B',
};

function getSeverityColor(severity) {
  return SEVERITY_COLORS[severity?.toLowerCase()] || '#94A3B8';
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;

  const data = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{data.name}</div>
      <div className="chart-tooltip-value">
        Confidence: {data.confidence}% &middot; Severity: {data.severity}
      </div>
    </div>
  );
}

export default function AnalysisCharts({ report }) {
  const chartData = useMemo(() => {
    if (!report?.findings?.length) return [];

    return report.findings.map((f) => ({
      name:
        f.finding?.name?.length > 28
          ? f.finding.name.substring(0, 25) + '...'
          : f.finding?.name || 'Unknown',
      fullName: f.finding?.name || 'Unknown',
      confidence: Math.round((f.finding?.confidence || 0) * 100),
      severity: f.finding?.severity || 'low',
    }));
  }, [report]);

  if (!chartData.length) {
    return (
      <div className="analysis-charts-container">
        <div className="charts-header">
          <BarChart3 size={16} color="var(--text-muted)" />
          <h2>Findings Analysis</h2>
        </div>
        <div className="no-chart-data">
          <SearchX size={32} />
          <span>No findings detected</span>
        </div>
      </div>
    );
  }

  const chartHeight = Math.max(200, chartData.length * 52 + 40);

  return (
    <motion.div
      className="analysis-charts-container"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="charts-header">
        <BarChart3 size={16} color="var(--primary)" />
        <h2>Findings Confidence</h2>
      </div>

      <div className="charts-body">
        <div className="chart-wrapper">
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart
              layout="vertical"
              data={chartData}
              margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
              barCategoryGap="20%"
            >
              <CartesianGrid
                strokeDasharray="3 3"
                horizontal={false}
                stroke="var(--border)"
              />
              <XAxis
                type="number"
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                axisLine={{ stroke: 'var(--border)' }}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={160}
                tick={{ fontSize: 12, fill: 'var(--text-secondary)' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                content={<CustomTooltip />}
                cursor={{ fill: 'var(--muted)', opacity: 0.5 }}
              />
              <Bar dataKey="confidence" radius={[0, 4, 4, 0]} maxBarSize={28}>
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={getSeverityColor(entry.severity)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-legend">
          <div className="legend-item">
            <span className="legend-dot low" />
            Low
          </div>
          <div className="legend-item">
            <span className="legend-dot moderate" />
            Moderate
          </div>
          <div className="legend-item">
            <span className="legend-dot high" />
            High
          </div>
          <div className="legend-item">
            <span className="legend-dot critical" />
            Critical
          </div>
        </div>
      </div>
    </motion.div>
  );
}
