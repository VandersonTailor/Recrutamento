import { ResponsiveContainer, Tooltip, XAxis, YAxis, Area, AreaChart, CartesianGrid } from 'recharts';

function AreaResumeChart({ data, dataKey = 'total' }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ left: -12, top: 8 }}>
          <defs>
            <linearGradient id="entriesColor" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#2f9b75" stopOpacity={0.28} />
              <stop offset="95%" stopColor="#2f9b75" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#edf1f3" strokeDasharray="4 4" />
          <XAxis dataKey="name" tick={{ fill: '#65778a', fontSize: 12 }} />
          <YAxis tick={{ fill: '#65778a', fontSize: 12 }} />
          <Tooltip
            cursor={{ stroke: '#a7e1cb', strokeWidth: 2 }}
            contentStyle={{ borderRadius: '12px', borderColor: '#d9dfe4' }}
          />
          <Area type="monotone" dataKey={dataKey} stroke="#2f9b75" strokeWidth={2.5} fill="url(#entriesColor)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export default AreaResumeChart;
