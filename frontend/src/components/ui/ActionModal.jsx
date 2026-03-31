import Button from './Button';

function ActionModal({ isOpen, title, description, onClose, onConfirm, confirmLabel = 'Confirmar' }) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slatewarm-900/35 p-4">
      <div className="w-full max-w-md rounded-xl2 border border-slatewarm-700 bg-slatewarm-900 p-5 shadow-soft">
        <h3 className="text-lg font-semibold text-slatewarm-50">{title}</h3>
        {description && <p className="mt-2 text-sm text-slatewarm-300">{description}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              onConfirm?.();
              onClose?.();
            }}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default ActionModal;
