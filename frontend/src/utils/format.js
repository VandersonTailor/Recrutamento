export function formatDate(dateString) {
  if (!dateString) return '-';
  const parsed = new Date(dateString);
  if (Number.isNaN(parsed.getTime())) return '-';
  return parsed.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export function groupBy(items, key) {
  return items.reduce((accumulator, item) => {
    const value = item[key];
    accumulator[value] = (accumulator[value] || 0) + 1;
    return accumulator;
  }, {});
}

export const stageColorMap = {
  Recebido: 'bg-slatewarm-100 text-slatewarm-700',
  'Em análise': 'bg-blue-50 text-blue-700',
  'Pré-selecionado': 'bg-violet-50 text-violet-700',
  Entrevista: 'bg-amber-50 text-amber-700',
  'Teste técnico': 'bg-cyan-50 text-cyan-700',
  'Banco de talentos': 'bg-teal-50 text-teal-700',
  Aprovado: 'bg-emerald-50 text-emerald-700',
  Reprovado: 'bg-rose-50 text-rose-700',
};
