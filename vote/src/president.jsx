// Presidential and mayoral elections: candidates, round 1 rule, runoff.
const PRESIDENT_DATA_URL = 'data/president-2026.json';
const PARTIES_DATA_URL = 'data/parties.json';
const PRESIDENT_STORAGE_KEY = 'vote:president:v1';
const PRESIDENT_DEFAULTS = { mode: 'president', candidates: [], turnout: 40, runoffPair: null, runoffA: null, source: null };
const OTHER_COLOR = '#9ca3af';
const INDEPENDENT_COLORS = ['#6b7280', '#0d9488', '#7c3aed', '#be185d', '#a16207'];

// Fetch the candidate list, polls and party colours once
const usePresidentData = () => {
  const [data, setData] = useState(null);
  useEffect(() => {
    Promise.all([fetch(PRESIDENT_DATA_URL).then(r => r.json()), fetch(PARTIES_DATA_URL).then(r => r.json())])
      .then(([election, registry]) => {
        const partyColor = Object.fromEntries(
          [...(election.parties || []), ...registry.parties].map(p => [p.id, p.color]));
        const candidates = Object.fromEntries(election.candidates.map((c, i) => [c.id, {
          ...c,
          color: (c.backers || []).map(id => partyColor[id]).find(Boolean) || INDEPENDENT_COLORS[i % INDEPENDENT_COLORS.length]
        }]));
        setData({ election: election.election, candidates, polls: election.presets });
      })
      .catch(() => setData({ error: true }));
  }, []);
  return data;
};

// Example list: poll average first, then polls newest first
const buildExamples = (data) => {
  if (!data || data.error) return [];
  const toRows = (shares) => shares.map(s => s.isOther
    ? { id: 'other', name: 'Други', color: OTHER_COLOR, votes: s.share, isOther: true }
    : { id: s.id, name: data.candidates[s.id]?.name || s.id, color: data.candidates[s.id]?.color || OTHER_COLOR, votes: s.share });

  const polls = [...data.polls].sort((a, b) => (b.published || '').localeCompare(a.published || ''));
  const inAverage = polls.filter(p => p.kind === 'poll' && p.inAverage !== false);
  const sums = {};
  inAverage.forEach(p => window.VoteSim.pollToShares(p).forEach(s => { sums[s.id] = (sums[s.id] || 0) + s.share; }));
  const average = Object.entries(sums)
    .map(([id, total]) => ({ id, share: Math.round((total / inAverage.length) * 10) / 10, isOther: id === 'other' }))
    .sort((a, b) => b.share - a.share);
  const turnouts = inAverage.map(p => p.turnout?.value).filter(v => v != null);

  return [
    {
      id: 'average', label: `Средно от ${inAverage.length} проучвания`,
      source: `Средно от ${inAverage.map(p => p.name).join(', ')}`,
      candidates: toRows(average),
      turnout: turnouts.length ? Math.round(turnouts.reduce((a, b) => a + b, 0) / turnouts.length * 10) / 10 : null
    },
    ...polls.map(p => ({
      id: p.id,
      label: `${p.name} · ${fmtDate(p.published)}${p.inAverage === false ? ' (поръчково)' : ''}`,
      source: `${p.name}${p.client ? ', ' + p.client : ''}, публикувано ${fmtDate(p.published)}`,
      candidates: toRows(window.VoteSim.pollToShares(p)),
      turnout: p.turnout?.value ?? null
    }))
  ];
};

const PresidentialSimulator = () => {
  const history = useUndoableDoc(PRESIDENT_STORAGE_KEY, PRESIDENT_DEFAULTS);
  const { doc, commit, replace } = history;
  const data = usePresidentData();
  const examples = useMemo(() => buildExamples(data), [data]);

  // First visit: start from the poll average instead of an empty list
  useEffect(() => {
    if (examples.length && doc.candidates.length === 0) replace(exampleDoc(examples[0]));
  }, [examples]);

  const exampleDoc = (ex) => ({
    candidates: ex.candidates, turnout: ex.turnout ?? doc.turnout, runoffPair: null, runoffA: null, source: ex.source
  });

  const isMayor = doc.mode === 'mayor';
  const result = useMemo(
    () => window.VoteSim.firstRound(doc.candidates, doc.turnout, { requireTurnout: !isMayor }),
    [doc.candidates, doc.turnout, isMayor]
  );

  // Any manual edit marks a loaded example as changed, so a presented source isn't misattributed
  const SOURCE_EDITED = ' (с промени)';
  const editCommit = (patch) => commit({
    ...patch,
    source: doc.source && !doc.source.endsWith(SOURCE_EDITED) ? doc.source + SOURCE_EDITED : doc.source
  });
  const updateCandidate = (id, patch) =>
    editCommit({ candidates: doc.candidates.map(c => c.id === id ? { ...c, ...patch } : c) });
  const addCandidate = () => editCommit({
    candidates: [...doc.candidates, {
      id: `c${Date.now()}`, name: `Кандидат ${doc.candidates.length + 1}`,
      color: INDEPENDENT_COLORS[doc.candidates.length % INDEPENDENT_COLORS.length], votes: 5
    }]
  });
  const removeCandidate = (id) => editCommit({ candidates: doc.candidates.filter(c => c.id !== id) });

  // Runoff: A's share defaults to the round 1 ratio of the two finalists until edited
  const pair = result.runoff;
  const pairKey = pair ? `${pair[0].id}|${pair[1].id}` : null;
  const defaultA = pair ? Math.round(pair[0].share / (pair[0].share + pair[1].share) * 1000) / 10 : 50;
  const runoffA = pairKey && doc.runoffPair === pairKey && doc.runoffA != null ? doc.runoffA : defaultA;
  const runoffWinner = pair ? (runoffA > 50 ? pair[0] : runoffA < 50 ? pair[1] : null) : null;

  const totalEntered = doc.candidates.reduce((sum, c) => sum + c.votes, 0);
  const title = isMayor ? 'Избори за кмет' : 'Президентски избори';
  const inputClass = 'px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500';

  return (
    <div className="w-full max-w-7xl mx-auto p-6 bg-white">
      <div className="flex flex-wrap justify-between items-center gap-3 mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-800">{title}</h1>
          {!isMayor && data?.election && (
            <p className="text-sm text-gray-500">
              {data.election.name}: първи тур {fmtDate(data.election.firstRound)}, балотаж {fmtDate(data.election.runoff)}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <select
            value=""
            onChange={(e) => {
              const ex = examples.find(x => x.id === e.target.value);
              if (ex) commit({ ...exampleDoc(ex), mode: 'president' });
            }}
            className={buttonClass}
            disabled={!examples.length}
          >
            <option value="">{data?.error ? 'Примерите не се заредиха' : 'Примери…'}</option>
            {examples.map(ex => <option key={ex.id} value={ex.id}>{ex.label}</option>)}
          </select>
          <UndoBar history={history} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Inputs */}
        <div className="space-y-4">
          <div className="p-4 bg-gray-50 rounded-lg space-y-3">
            <label className="flex items-center justify-between gap-2 text-sm text-gray-700">
              Вид избор
              <select value={doc.mode} onChange={(e) => commit({ mode: e.target.value })} className={inputClass}>
                <option value="president">Президент</option>
                <option value="mayor">Кмет</option>
              </select>
            </label>
            <label className="flex items-center justify-between gap-2 text-sm text-gray-700">
              Активност (%)
              <VotesInput value={doc.turnout} onCommit={(v) => editCommit({ turnout: v })} className={`${inputClass} w-20 text-right`} />
            </label>
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <h2 className="text-lg font-semibold text-gray-800">Кандидати</h2>
              <button onClick={addCandidate} title="Добави кандидат"
                className="px-3 py-1 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm">
                <Plus size={16} />
              </button>
            </div>
            <div className="space-y-1">
              {doc.candidates.map(c => (
                <div key={c.id} className="flex items-center gap-2 p-1 border border-gray-200 rounded">
                  <input type="color" value={c.color} onChange={(e) => updateCandidate(c.id, { color: e.target.value })}
                    className="w-6 h-6 rounded cursor-pointer flex-shrink-0" />
                  <input type="text" value={c.name} onChange={(e) => updateCandidate(c.id, { name: e.target.value })}
                    className={`${inputClass} flex-1 min-w-0`} />
                  <VotesInput value={c.votes} onCommit={(v) => updateCandidate(c.id, { votes: v })}
                    className={`${inputClass} w-16 text-right`} />
                  <span className="text-xs text-gray-500">%</span>
                  <button onClick={() => removeCandidate(c.id)} title="Премахни" className="p-1 text-gray-500 hover:text-red-600">
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Въведени: {fmtPct(totalEntered)}. Делът на всеки се смята спрямо сбора (действителните гласове).
            </p>
          </div>
        </div>

        {/* Results */}
        <div className="lg:col-span-2 space-y-6">
          <div className={`p-4 rounded-lg border ${result.winner ? 'bg-green-50 border-green-200' : 'bg-amber-50 border-amber-200'}`}>
            {result.winner ? (
              <div className="text-xl font-bold text-green-800">Печели на първи тур: {result.winner.name}</div>
            ) : pair ? (
              <>
                <div className="text-xl font-bold text-amber-800">Балотаж: {pair[0].name} срещу {pair[1].name}</div>
                <div className="text-sm text-amber-700">
                  {result.reason === 'turnout'
                    ? `${pair[0].name} има над 50%, но активността (${fmtPct(doc.turnout)}) не е над 50%.`
                    : 'Никой кандидат няма повече от половината от действителните гласове.'}
                </div>
              </>
            ) : (
              <div className="text-gray-600">Добавете поне двама кандидати с гласове.</div>
            )}
            {doc.source && <div className="mt-1 text-xs text-gray-500">Източник: {doc.source}</div>}
          </div>

          <div>
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Първи тур</h2>
            <div className="space-y-2">
              {result.ranked.map(c => (
                <div key={c.id} className="grid grid-cols-[10rem_1fr_3.5rem] items-center gap-2">
                  <span className="text-sm font-medium text-gray-800 truncate" title={c.name}>{c.name}</span>
                  <div className="relative h-6 bg-gray-100 rounded">
                    <div className="h-full rounded" style={{ width: `${c.share}%`, backgroundColor: c.color }} />
                    <div className="absolute top-0 bottom-0 border-l-2 border-dashed border-gray-700" style={{ left: '50%' }} />
                  </div>
                  <span className="text-sm text-gray-700 text-right">{fmtPct(c.share)}</span>
                </div>
              ))}
            </div>
            <p className="mt-1 text-xs text-gray-500">Пунктирът е 50% от действителните гласове.</p>
          </div>

          {!isMayor && (
            <div>
              <h2 className="text-lg font-semibold text-gray-800 mb-3">Активност</h2>
              <PctBar
                segments={[{ value: doc.turnout, color: doc.turnout > 50 ? '#16a34a' : '#d97706', label: fmtPct(doc.turnout) }]}
                markers={[{ at: 50, label: '50%' }]}
              />
              <div className="h-5" />
            </div>
          )}

          {pair && !result.winner && (
            <div>
              <h2 className="text-lg font-semibold text-gray-800 mb-3">Балотаж</h2>
              <div className="flex items-center gap-2 mb-2 text-sm text-gray-700">
                {pair[0].name}:
                <VotesInput value={runoffA} onCommit={(v) => commit({ runoffPair: pairKey, runoffA: v })}
                  className={`${inputClass} w-16 text-right`} />
                %
                <span className="text-gray-500">(по подразбиране по съотношението от първия тур)</span>
              </div>
              <PctBar
                height="h-10"
                segments={[
                  { value: runoffA, color: pair[0].color, label: `${pair[0].name} ${fmtPct(runoffA)}` },
                  { value: 100 - runoffA, color: pair[1].color, label: `${pair[1].name} ${fmtPct(100 - runoffA)}` }
                ]}
                markers={[{ at: 50, label: '50%' }]}
              />
              <div className="mt-7 text-base font-semibold text-gray-800">
                {runoffWinner ? `Печели: ${runoffWinner.name}` : 'Равенство'}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
