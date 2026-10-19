// App shell: one tab per election type. The tab is kept in the URL (#president), so views can be linked.
const ELECTION_TYPES = [
  { id: 'parliament', label: 'Парламентарни', title: 'Симулатор на Народно събрание', View: ParliamentSimulator },
  { id: 'president', label: 'Президент / кмет', title: 'Президентски избори', View: PresidentialSimulator },
  { id: 'referendum', label: 'Референдум', title: 'Национален референдум', View: ReferendumSimulator }
];

const typeFromHash = () => {
  const id = window.location.hash.slice(1);
  return ELECTION_TYPES.some(t => t.id === id) ? id : ELECTION_TYPES[0].id;
};

const App = () => {
  const [typeId, setTypeId] = useState(typeFromHash);
  useEffect(() => {
    const onHash = () => setTypeId(typeFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const type = ELECTION_TYPES.find(t => t.id === typeId);
  useEffect(() => { document.title = `${type.title} · Избори`; }, [type]);

  return (
    <div className="min-h-screen bg-white">
      <nav className="border-b border-gray-200 bg-gray-50">
        <div className="max-w-7xl mx-auto px-6 flex flex-wrap items-center gap-1">
          <span className="mr-4 py-3 font-bold text-gray-800">Избори</span>
          {ELECTION_TYPES.map(t => (
            <a key={t.id} href={`#${t.id}`}
              className={`px-4 py-3 text-sm font-medium border-b-2 ${t.id === typeId
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-gray-600 hover:text-gray-900'}`}>
              {t.label}
            </a>
          ))}
        </div>
      </nav>
      <type.View key={type.id} />
    </div>
  );
};
