// National referendum: yes/no share, turnout and the validity rule of the Direct Participation Act.
const REFERENDUM_STORAGE_KEY = 'vote:referendum:v1';
const REFERENDUM_DEFAULTS = { question: 'Подкрепяте ли …?', yes: 55, turnout: 35, lastTurnout: 40 };

const REFERENDUM_OUTCOMES = {
  adopted: { text: 'Предложението е прието', tone: 'bg-green-50 border-green-200 text-green-800' },
  parliament: { text: 'Внася се в Народното събрание', tone: 'bg-amber-50 border-amber-200 text-amber-800' },
  rejected: { text: 'Предложението не е прието', tone: 'bg-red-50 border-red-200 text-red-800' }
};

const ReferendumSimulator = () => {
  const history = useUndoableDoc(REFERENDUM_STORAGE_KEY, REFERENDUM_DEFAULTS);
  const { doc, commit } = history;
  const outcome = window.VoteSim.referendumOutcome(doc.yes, doc.turnout, doc.lastTurnout);
  const inputClass = 'px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500';

  const explanation = doc.yes <= 50
    ? '„Да“ няма повече от половината от гласовете.'
    : outcome === 'adopted'
      ? `Активността (${fmtPct(doc.turnout)}) е поне колкото на последните парламентарни избори (${fmtPct(doc.lastTurnout)}) и „Да“ е мнозинство.`
      : outcome === 'parliament'
        ? `Активността е под тази на последните парламентарни избори (${fmtPct(doc.lastTurnout)}), но над 20% и „Да“ е мнозинство.`
        : 'Активността не е над 20%.';

  return (
    <div className="w-full max-w-7xl mx-auto p-6 bg-white">
      <div className="flex flex-wrap justify-between items-center gap-3 mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Национален референдум</h1>
        <div className="flex gap-2"><UndoBar history={history} /></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="p-4 bg-gray-50 rounded-lg space-y-3">
          <label className="block text-sm text-gray-700">
            Въпрос
            <textarea value={doc.question} rows={3} onChange={(e) => history.replace({ question: e.target.value })}
              onBlur={(e) => commit({ question: e.target.value })}
              className={`${inputClass} mt-1 w-full`} />
          </label>
          <label className="flex items-center justify-between gap-2 text-sm text-gray-700">
            „Да“ (% от гласувалите)
            <VotesInput value={doc.yes} onCommit={(v) => commit({ yes: v })} className={`${inputClass} w-20 text-right`} />
          </label>
          <label className="flex items-center justify-between gap-2 text-sm text-gray-700">
            Активност (%)
            <VotesInput value={doc.turnout} onCommit={(v) => commit({ turnout: v })} className={`${inputClass} w-20 text-right`} />
          </label>
          <label className="flex items-center justify-between gap-2 text-sm text-gray-700">
            Активност на последните парламентарни избори (%)
            <VotesInput value={doc.lastTurnout} onCommit={(v) => commit({ lastTurnout: v })} className={`${inputClass} w-20 text-right`} />
          </label>
        </div>

        <div className="lg:col-span-2 space-y-6">
          <div className={`p-4 rounded-lg border ${REFERENDUM_OUTCOMES[outcome].tone}`}>
            <div className="text-xl font-bold">{REFERENDUM_OUTCOMES[outcome].text}</div>
            <div className="text-sm">{explanation}</div>
            <div className="mt-2 text-base text-gray-800">{doc.question}</div>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Резултат</h2>
            <PctBar
              height="h-10"
              segments={[
                { value: doc.yes, color: '#16a34a', label: `Да ${fmtPct(doc.yes)}` },
                { value: 100 - doc.yes, color: '#dc2626', label: `Не ${fmtPct(100 - doc.yes)}` }
              ]}
              markers={[{ at: 50, label: '50%' }]}
            />
          </div>

          <div className="pt-4">
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Активност</h2>
            <PctBar
              segments={[{ value: doc.turnout, color: '#2563eb', label: fmtPct(doc.turnout) }]}
              markers={[
                { at: 20, label: '20%' },
                { at: doc.lastTurnout, label: `Последни избори ${fmtPct(doc.lastTurnout)}` }
              ]}
            />
          </div>

          <p className="pt-4 text-xs text-gray-500">
            Чл. 23 от Закона за прякото участие на гражданите: предложението е прието, ако са гласували не по-малко
            от участвалите в последните избори за Народно събрание и повече от половината са гласували „Да“.
            При по-ниска активност, но над 20% и мнозинство „Да“, предложението се внася в Народното събрание.
          </p>
        </div>
      </div>
    </div>
  );
};
