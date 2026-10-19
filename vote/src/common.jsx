// Shared UI pieces for all election views. Loaded first; everything here is global.
const { useState, useEffect, useMemo } = React;

// Inline replacements for the lucide-react icons (no module loader in the browser)
const Icon = ({ size = 16, children }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const Plus = ({ size }) => <Icon size={size}><path d="M12 5v14M5 12h14" /></Icon>;
const Trash2 = ({ size }) => (
  <Icon size={size}>
    <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" />
  </Icon>
);

const nextIdOf = (items) => items.reduce((max, item) => Math.max(max, item.id), 0) + 1;

// Bulgarian number format: decimal comma, one decimal place
const fmtPct = (v) => `${v.toFixed(1).replace('.', ',')}%`;
const fmtDate = (iso) => iso ? iso.slice(8, 10) + '.' + iso.slice(5, 7) : '';

// Vote % field: edits stay local until Enter or leaving the field, so tiles don't jump while typing.
// Escape (or an invalid value) restores the current value.
const VotesInput = ({ value, onCommit, className, max = 100 }) => {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => { setDraft(String(value)); }, [value]);
  const submit = () => {
    const v = parseFloat(draft.replace(',', '.'));
    if (!isNaN(v) && v >= 0 && v <= max && v !== value) onCommit(v);
    else setDraft(String(value));
  };
  return (
    <input
      type="text"
      inputMode="decimal"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={submit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.target.blur();
        else if (e.key === 'Escape') { setDraft(String(value)); setTimeout(() => e.target.blur()); }
      }}
      className={className}
    />
  );
};

// Undoable document autosaved to localStorage, with Ctrl+Z / Ctrl+Y.
// replace() swaps the document without an undo step (used for first-load defaults).
const useUndoableDoc = (storageKey, defaults) => {
  const [h, setH] = useState(() => {
    let present = defaults;
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey));
      if (saved && typeof saved === 'object') present = { ...defaults, ...saved };
    } catch (e) { /* storage blocked or corrupt */ }
    return { past: [], present, future: [] };
  });

  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(h.present)); } catch (e) { /* ignore */ }
  }, [h.present]);

  const commit = (patch) => setH(s => ({
    past: [...s.past, s.present].slice(-100), present: { ...s.present, ...patch }, future: []
  }));
  const replace = (patch) => setH(s => ({ ...s, present: { ...s.present, ...patch } }));
  const undo = () => setH(s => s.past.length === 0 ? s : {
    past: s.past.slice(0, -1), present: s.past[s.past.length - 1], future: [s.present, ...s.future]
  });
  const redo = () => setH(s => s.future.length === 0 ? s : {
    past: [...s.past, s.present], present: s.future[0], future: s.future.slice(1)
  });

  useEffect(() => {
    const onKey = (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.target.type === 'text' || e.target.tagName === 'TEXTAREA') return;
      const key = e.key.toLowerCase();
      if (key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (key === 'y' || (key === 'z' && e.shiftKey)) { e.preventDefault(); redo(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return {
    doc: h.present, commit, replace, undo, redo,
    canUndo: h.past.length > 0, canRedo: h.future.length > 0,
    reset: () => commit(defaults)
  };
};

const buttonClass = 'px-3 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 text-sm font-medium';

const UndoBar = ({ history }) => (
  <>
    <button onClick={history.undo} disabled={!history.canUndo} title="Отмени (Ctrl+Z)" className={buttonClass}>↶</button>
    <button onClick={history.redo} disabled={!history.canRedo} title="Върни (Ctrl+Y)" className={buttonClass}>↷</button>
    <button
      onClick={() => { if (confirm('Да се върнат ли стойностите по подразбиране?')) history.reset(); }}
      className={buttonClass}
    >
      Нулирай
    </button>
  </>
);

// Horizontal 0–100% bar with labelled marker lines
const PctBar = ({ segments, markers = [], height = 'h-8' }) => (
  <div className="relative">
    <div className={`w-full ${height} flex rounded overflow-hidden bg-gray-100 border border-gray-200`}>
      {segments.map((s, i) => (
        <div key={i} className="h-full flex items-center justify-center text-xs font-bold text-white"
          style={{ width: `${Math.max(0, Math.min(100, s.value))}%`, backgroundColor: s.color }}
          title={s.title}>
          {s.label && s.value >= 8 ? s.label : ''}
        </div>
      ))}
    </div>
    {markers.map((m, i) => (
      <div key={i} className="absolute top-0 bottom-0 pointer-events-none" style={{ left: `${m.at}%` }}>
        <div className="h-full border-l-2 border-dashed border-gray-700" />
        <div className="absolute -bottom-5 -translate-x-1/2 text-xs text-gray-600 whitespace-nowrap">{m.label}</div>
      </div>
    ))}
  </div>
);
