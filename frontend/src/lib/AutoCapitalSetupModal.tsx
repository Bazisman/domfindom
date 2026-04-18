type AutoCapitalSetupModalProps = {
  open: boolean;
  busy?: boolean;
  percent: number;
  accountName: string;
  dontAskAgain: boolean;
  error: string | null;
  onAccountNameChange: (value: string) => void;
  onDontAskAgainChange: (checked: boolean) => void;
  onClose: () => void;
  onSkip: () => void;
  onCreateNow: () => void;
};

export function AutoCapitalSetupModal({
  open,
  busy = false,
  percent,
  accountName,
  dontAskAgain,
  error,
  onAccountNameChange,
  onDontAskAgainChange,
  onClose,
  onSkip,
  onCreateNow,
}: AutoCapitalSetupModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="confirm-modal-backdrop" onClick={busy ? undefined : onClose}>
      <div className="confirm-modal auto-capital-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <h3>Нужен счет для автоотчислений</h3>
        <p>
          Автоотчисления включены на <strong>{percent}%</strong>, но счет для них пока не настроен.
        </p>
        <p>Можно отключить автоотчисления для этого сценария или сразу создать счет, чтобы доход и отчисление сохранились одним действием.</p>

        <label className="confirm-check">
          <input checked={dontAskAgain} disabled={busy} onChange={(event) => onDontAskAgainChange(event.target.checked)} type="checkbox" />
          <span>Больше не спрашивать и отключить автоотчисления</span>
        </label>

        <label className="confirm-field">
          <span>Добавить счет сейчас</span>
          <input
            disabled={busy}
            onChange={(event) => onAccountNameChange(event.target.value)}
            placeholder="Например, Копилка"
            value={accountName}
          />
        </label>

        {error ? <p className="form-error">{error}</p> : null}

        <div className="confirm-actions auto-capital-actions">
          <button className="ghost-button" disabled={busy} onClick={onClose} type="button">
            Отмена
          </button>
          <button className="ghost-button" disabled={busy} onClick={onSkip} type="button">
            {busy ? "Подождите..." : "Сохранить без отчислений"}
          </button>
          <button className="primary-button" disabled={busy} onClick={onCreateNow} type="button">
            {busy ? "Создаем..." : "Добавить сейчас"}
          </button>
        </div>
      </div>
    </div>
  );
}
