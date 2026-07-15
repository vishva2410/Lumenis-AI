'use client';

import dynamic from 'next/dynamic';

const DashboardCharts = dynamic(() => import('@/components/DashboardCharts'), {
  ssr: false,
  loading: () => <div className="skeleton" style={{ height: 400 }} />,
});

export default function DashboardChartsWrapper({ jobs }) {
  return <DashboardCharts jobs={jobs} />;
}
