import { Sparkles } from 'lucide-react';
import SectionCard from '../components/ui/SectionCard';

function PlaceholderPage({ title }) {
  return (
    <SectionCard title={title} subtitle="Módulo pronto para receber integrações futuras">
      <div className="flex items-center gap-3 rounded-xl bg-brand-50 p-4 text-brand-800">
        <Sparkles size={18} />
        <p className="text-sm">Esta área já segue o design system e pode ser expandida no próximo sprint.</p>
      </div>
    </SectionCard>
  );
}

export default PlaceholderPage;
