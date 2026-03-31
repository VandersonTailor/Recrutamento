import { ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart, CartesianGrid } from 'recharts';

function BarJobsChart({ data, dataKey = 'total' }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ left: -14, top: 6 }}>
          <CartesianGrid vertical={false} stroke="#edf1f3" strokeDasharray="3 3" />
          <XAxis dataKey="job" tick={{ fill: '#65778a', fontSize: 12 }} />
          <YAxis tick={{ fill: '#65778a', fontSize: 12 }} />
          <Tooltip contentStyle={{ borderRadius: '12px', borderColor: '#d9dfe4' }} />
          <Bar dataKey={dataKey} fill="#4ab58f" radius={[8, 8, 0, 0]} maxBarSize={44} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default BarJobsChart;
