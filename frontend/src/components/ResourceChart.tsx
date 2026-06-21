import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import type { PlayerState, ResourceDef } from '../types/arena';

interface Props { players: PlayerState[]; resources: ResourceDef[]; }

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6'];

export function ResourceChart({ players, resources }: Props) {
  const primary = resources[0];
  if (!primary) return null;

  const data = players
    .filter((p) => p.is_alive)
    .map((p, i) => ({
      name: p.name.length > 8 ? p.name.slice(0, 8) : p.name,
      fullName: p.name,
      value: p.resources[primary.id] ?? 0,
      fill: COLORS[i % COLORS.length],
    }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="name" tick={{ fill: '#999', fontSize: 9 }} axisLine={{ stroke: '#eee' }} tickLine={false} />
        <YAxis tick={{ fill: '#999', fontSize: 9 }} axisLine={{ stroke: '#eee' }} tickLine={false} />
        <Tooltip
          contentStyle={{ background: '#fff', border: '1px solid #e5e5e5', borderRadius: 6, fontSize: 11, color: '#333' }}
          formatter={(v: number) => [`${v}${primary.unit}`, primary.label]}
          labelFormatter={(_: string, payload: any) => payload?.[0]?.payload?.fullName || ''}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {data.map((e, i) => <Cell key={i} fill={e.fill} fillOpacity={0.6} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
