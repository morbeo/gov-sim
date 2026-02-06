import React, { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

const ParliamentSimulator = () => {
  const [assemblyType, setAssemblyType] = useState(240);
x   
  const [hoveredSeat, setHoveredSeat] = useState(null);
  const [hoveredParty, setHoveredParty] = useState(null);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [draggedParty, setDraggedParty] = useState(null);
  const [tileSize, setTileSize] = useState(120); // Default tile size in pixels
  const [nextId, setNextId] = useState(8);
  const [nextGroupId, setNextGroupId] = useState(3);

  const THRESHOLD = 4.0; // 4% electoral threshold

  // Calculate seats using proportional distribution
  const calculateSeats = () => {
    // Filter parties that meet the threshold
    const qualifiedParties = parties.filter(p => p.votes >= THRESHOLD);

    if (qualifiedParties.length === 0) return parties.map(p => ({ ...p, seats: 0 }));

    // Calculate total votes of qualified parties
    const totalQualifiedVotes = qualifiedParties.reduce((sum, p) => sum + p.votes, 0);

    // Distribute seats proportionally
    const partiesWithSeats = parties.map(party => {
      if (party.votes < THRESHOLD) {
        return { ...party, seats: 0 };
      }
      const proportion = party.votes / totalQualifiedVotes;
      const exactSeats = proportion * assemblyType;
      return { ...party, exactSeats, seats: Math.floor(exactSeats) };
    });

    // Distribute remaining seats using largest remainder method
    let assignedSeats = partiesWithSeats.reduce((sum, p) => sum + p.seats, 0);
    const remainingSeats = assemblyType - assignedSeats;

    if (remainingSeats > 0) {
      const sortedByRemainder = partiesWithSeats
        .filter(p => p.votes >= THRESHOLD)
        .sort((a, b) => (b.exactSeats - b.seats) - (a.exactSeats - a.seats));

      for (let i = 0; i < remainingSeats; i++) {
        sortedByRemainder[i].seats++;
      }
    }

    return partiesWithSeats;
  };

  const partiesWithSeats = calculateSeats();
  const totalVotes = parties.reduce((sum, party) => sum + party.votes, 0);
  const totalSeats = partiesWithSeats.reduce((sum, party) => sum + party.seats, 0);

  // Sort parties by votes (descending)
  const sortedParties = [...parties].sort((a, b) => b.votes - a.votes);

  const addParty = () => {
    const newParty = {
      id: nextId,
      name: `Партия ${nextId}`,
      color: `#${Math.floor(Math.random()*16777215).toString(16).padStart(6, '0')}`,
      votes: 5.0
    };
    setParties([...parties, newParty]);
    setNextId(nextId + 1);
  };

  const updateParty = (id, field, value) => {
    setParties(parties.map(party =>
      party.id === id ? { ...party, [field]: value } : party
    ));
  };

  const deleteParty = (id) => {
    setParties(parties.filter(party => party.id !== id));
  };

  const addGroup = () => {
    const newGroup = {
      id: nextGroupId,
      name: `Група ${nextGroupId}`,
      color: `#${Math.floor(Math.random()*16777215).toString(16).padStart(6, '0')}`,
      partyIds: []
    };
    setGroups([...groups, newGroup]);
    setNextGroupId(nextGroupId + 1);
  };

  const updateGroup = (id, field, value) => {
    setGroups(groups.map(group =>
      group.id === id ? { ...group, [field]: value } : group
    ));
  };

  const deleteGroup = (id) => {
    setGroups(groups.filter(group => group.id !== id));
  };

  const togglePartyInGroup = (groupId, partyId) => {
    setGroups(groups.map(group => {
      if (group.id === groupId) {
        const partyIds = group.partyIds.includes(partyId)
          ? group.partyIds.filter(id => id !== partyId)
          : [...group.partyIds, partyId];
        return { ...group, partyIds };
      }
      return group;
    }));
  };

  const handleDragStart = (e, party) => {
    setDraggedParty(party);
    e.dataTransfer.effectAllowed = 'copy';
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  };

  const handleDrop = (e, groupId) => {
    e.preventDefault();
    if (draggedParty) {
      togglePartyInGroup(groupId, draggedParty.id);
      setDraggedParty(null);
    }
  };

  const handleDragEnd = () => {
    setDraggedParty(null);
  };

  const getGroupStats = (group) => {
    const groupParties = partiesWithSeats.filter(p => group.partyIds.includes(p.id));
    const totalSeats = groupParties.reduce((sum, p) => sum + p.seats, 0);
    const totalVotes = groupParties.reduce((sum, p) => sum + p.votes, 0);
    return { totalSeats, totalVotes };
  };

  const saveToFile = () => {
    const data = {
      assemblyType,
      parties,
      groups,
      nextId,
      nextGroupId
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `parliament-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const loadFromFile = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target.result);
        setAssemblyType(data.assemblyType || 240);
        setParties(data.parties || []);
        setGroups(data.groups || []);
        setNextId(data.nextId || 1);
        setNextGroupId(data.nextGroupId || 1);
      } catch (error) {
        alert('Грешка при зареждане на файла');
      }
    };
    reader.readAsText(file);
  };

  const exportToCSV = () => {
    const csvHeader = 'Име,Цвят,Гласове (%)\n';
    const csvRows = parties.map(p =>
      `"${p.name}",${p.color},${p.votes}`
    ).join('\n');

    const csv = csvHeader + csvRows;
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `parties-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const importFromCSV = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target.result;
        const lines = text.split('\n').filter(line => line.trim());

        // Skip header
        const dataLines = lines.slice(1);

        const importedParties = dataLines.map((line, index) => {
          // Handle CSV parsing with quotes
          const matches = line.match(/(?:"([^"]*)"|([^,]+)),([^,]+),([^,]+)/);
          if (!matches) return null;

          const name = matches[1] || matches[2];
          const color = matches[3].trim();
          const votes = parseFloat(matches[4].trim());

          return {
            id: nextId + index,
            name: name.trim(),
            color: color,
            votes: isNaN(votes) ? 0 : votes
          };
        }).filter(p => p !== null);

        setParties([...parties, ...importedParties]);
        setNextId(nextId + importedParties.length);
      } catch (error) {
        alert('Грешка при импортиране на CSV файла');
      }
    };
    reader.readAsText(file);
  };

  // Generate rectangular grid visualization (3 groups of 8 rows x 10 seats)
  const generateRectangularGrid = () => {
    const seats = [];
    let seatIndex = 0;
    const groups = 3;
    const rows = 8;
    const cols = 10;
    const seatSize = 18;
    const spacing = 4;
    const groupSpacing = 20;

    for (let group = 0; group < groups; group++) {
      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          if (seatIndex >= assemblyType) break;

          const x = group * (cols * (seatSize + spacing) + groupSpacing) + col * (seatSize + spacing);
          const y = row * (seatSize + spacing);

          let partyInfo = null;
          let cumulativeSeats = 0;

          for (const party of partiesWithSeats) {
            if (seatIndex >= cumulativeSeats && seatIndex < cumulativeSeats + party.seats) {
              partyInfo = party;
              break;
            }
            cumulativeSeats += party.seats;
          }

          seats.push({
            x,
            y,
            size: seatSize,
            color: partyInfo ? partyInfo.color : '#e5e7eb',
            party: partyInfo,
            seatNumber: seatIndex + 1
          });
          seatIndex++;
        }
        if (seatIndex >= assemblyType) break;
      }
      if (seatIndex >= assemblyType) break;
    }

    return seats;
  };

  const gridSeats = generateRectangularGrid();
  const unqualifiedParties = parties.filter(p => p.votes < THRESHOLD);

  return (
    <div className="w-full max-w-7xl mx-auto p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Симулатор на Народно събрание</h1>
        <div className="flex gap-2">
          <button
            onClick={saveToFile}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            💾 JSON
          </button>
          <label className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium cursor-pointer">
            📂 JSON
            <input
              type="file"
              accept=".json"
              onChange={loadFromFile}
              className="hidden"
            />
          </label>
          <button
            onClick={exportToCSV}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
          >
            📊 CSV Export
          </button>
          <label className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium cursor-pointer">
            📥 CSV Import
            <input
              type="file"
              accept=".csv"
              onChange={importFromCSV}
              className="hidden"
            />
          </label>
        </div>
      </div>

      {/* Assembly Type Selector */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Тип събрание
        </label>
        <div className="flex gap-4">
          <button
            onClick={() => setAssemblyType(240)}
            className={`px-6 py-2 rounded-lg font-medium transition-colors ${
              assemblyType === 240
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
            }`}
          >
            Народно събрание (240 депутати)
          </button>
          <button
            onClick={() => setAssemblyType(400)}
            className={`px-6 py-2 rounded-lg font-medium transition-colors ${
              assemblyType === 400
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
            }`}
          >
            Велико народно събрание (400 депутати)
          </button>
        </div>
      </div>

      {/* Vote Summary */}
      <div className="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
        <div className="flex justify-between items-center">
          <div>
            <span className="text-lg font-semibold text-gray-800">
              Общо гласове: {totalVotes.toFixed(1)}%
            </span>
          </div>
          <div>
            <span className="text-lg font-semibold text-gray-800">
              Разпределени мандати: {totalSeats} / {assemblyType}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Party Management - Fixed-size Tile Grid */}
        <div>
          <div className="mb-3">
            <div className="flex justify-between items-center mb-2">
              <h2 className="text-lg font-semibold text-gray-800">Партии</h2>
              <button
                onClick={addParty}
                className="flex items-center gap-1 px-3 py-1 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm"
              >
                <Plus size={16} />
              </button>
            </div>

            {/* Size control */}
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-gray-600">Размер:</span>
              <input
                type="range"
                min="80"
                max="180"
                step="10"
                value={tileSize}
                onChange={(e) => setTileSize(parseInt(e.target.value))}
                className="flex-1"
              />
              <span className="text-xs text-gray-500 w-8">{tileSize}</span>
            </div>
          </div>

          {/* Tile Grid */}
          <div
            className="grid gap-2"
            style={{
              gridTemplateColumns: `repeat(auto-fill, minmax(${tileSize}px, 1fr))`
            }}
          >
            {sortedParties.map((party) => {
              const partyWithSeats = partiesWithSeats.find(p => p.id === party.id);
              const qualifies = party.votes >= THRESHOLD;

              return (
                <div
                  key={party.id}
                  draggable={qualifies}
                  onDragStart={(e) => qualifies && handleDragStart(e, party)}
                  onDragEnd={handleDragEnd}
                  className={`transition-opacity ${draggedParty?.id === party.id ? 'opacity-50' : ''}`}
                  onMouseEnter={() => setHoveredParty(party.id)}
                  onMouseLeave={() => setHoveredParty(null)}
                >
                  <div
                    className={`p-2 bg-white border rounded-lg shadow-sm h-full flex flex-col relative ${
                      qualifies ? 'border-gray-200 cursor-move' : 'border-red-200 bg-red-50'
                    } ${hoveredParty === party.id ? 'ring-2 ring-blue-400' : ''}`}
                    style={{
                      minHeight: `${tileSize}px`,
                      width: '100%'
                    }}
                  >
                    {/* Colored bar representing seats proportion */}
                    {qualifies && partyWithSeats && (
                      <div className="absolute top-2 left-2 right-2 h-1 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${(partyWithSeats.seats / assemblyType) * 100}%`,
                            backgroundColor: party.color
                          }}
                        />
                      </div>
                    )}

                    <div className="flex items-start gap-2 mb-2" style={{ marginTop: qualifies ? '8px' : '0' }}>
                      <input
                        type="color"
                        value={party.color}
                        onChange={(e) => updateParty(party.id, 'color', e.target.value)}
                        className="w-6 h-6 rounded cursor-pointer flex-shrink-0"
                      />

                      <div className="flex-1 min-w-0">
                        <input
                          type="text"
                          value={party.name}
                          onChange={(e) => updateParty(party.id, 'name', e.target.value)}
                          className="w-full mb-1 px-2 py-0.5 text-xs font-semibold border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          style={{ fontSize: tileSize > 120 ? '0.75rem' : '0.7rem' }}
                        />
                      </div>

                      <button
                        onClick={() => deleteParty(party.id)}
                        className="p-0.5 text-gray-600 hover:text-red-600 flex-shrink-0"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>

                    <div className="flex items-center gap-1 mb-2">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.1"
                        value={party.votes}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value) && value >= 0 && value <= 100) {
                            updateParty(party.id, 'votes', value);
                          }
                        }}
                        className="w-14 px-1 py-0.5 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                      <span className="text-xs text-gray-600">%</span>
                    </div>

                    <div className="mt-auto">
                      {qualifies ? (
                        <div className="text-center py-1 bg-green-100 rounded">
                          <span className="text-sm font-bold text-green-700">
                            {partyWithSeats?.seats || 0}
                          </span>
                          <span className="text-xs text-green-600 ml-1">мандата</span>
                        </div>
                      ) : (
                        <div className="text-center py-1 bg-red-100 rounded">
                          <span className="text-xs text-red-600 font-medium">
                            Под {THRESHOLD}%
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {partiesWithSeats.filter(p => p.seats > 0).length > 0 && (
            <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800">
              💡 Влачете партиите към групите
            </div>
          )}
        </div>

        {/* Groups Management - Horizontal Bars */}
        <div className="lg:col-span-1">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-lg font-semibold text-gray-800">Групи</h2>
            <button
              onClick={addGroup}
              className="flex items-center gap-1 px-3 py-1 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm"
            >
              <Plus size={16} />
            </button>
          </div>

          <div className="space-y-3">
            {groups.map(group => {
              const stats = getGroupStats(group);
              const isSelected = selectedGroup === group.id;
              const groupParties = partiesWithSeats.filter(p => group.partyIds.includes(p.id) && p.seats > 0);

              // Calculate marker positions (1/3, 1/2, 2/3 of assemblyType)
              const oneThird = assemblyType / 3;
              const oneHalf = assemblyType / 2;
              const twoThirds = (assemblyType * 2) / 3;

              return (
                <div
                  key={group.id}
                  className={`bg-white border rounded-lg shadow-sm transition-all ${
                    isSelected ? 'ring-2 ring-purple-500 border-purple-500' : 'border-gray-200'
                  }`}
                  onClick={() => setSelectedGroup(isSelected ? null : group.id)}
                >
                  {/* Group Header */}
                  <div className="p-2 flex items-center gap-2 border-b border-gray-200">
                    <input
                      type="color"
                      value={group.color}
                      onChange={(e) => {
                        e.stopPropagation();
                        updateGroup(group.id, 'color', e.target.value);
                      }}
                      className="w-6 h-6 rounded cursor-pointer flex-shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    />

                    <div className="flex-1 min-w-0">
                      <input
                        type="text"
                        value={group.name}
                        onChange={(e) => {
                          e.stopPropagation();
                          updateGroup(group.id, 'name', e.target.value);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-full px-2 py-0.5 text-xs font-semibold border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-purple-500"
                      />
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteGroup(group.id);
                      }}
                      className="p-1 text-gray-600 hover:text-red-600 flex-shrink-0"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  {/* Drop Zone - Horizontal Bar scaled to assemblyType */}
                  <div
                    onDragOver={handleDragOver}
                    onDrop={(e) => {
                      e.stopPropagation();
                      handleDrop(e, group.id);
                    }}
                    className="p-2 min-h-[100px] cursor-pointer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {groupParties.length === 0 ? (
                      <div className="h-full flex items-center justify-center text-xs text-gray-400 border-2 border-dashed border-gray-300 rounded p-4">
                        Влачете партии тук
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {/* Horizontal Bar with markers - scaled to assemblyType */}
                        <div className="relative">
                          {/* Marker lines - positioned absolutely */}
                          <div className="absolute inset-0 pointer-events-none">
                            {/* 1/3 marker */}
                            <div
                              className="absolute top-0 bottom-0 w-px bg-gray-300"
                              style={{ left: `${(oneThird / assemblyType) * 100}%` }}
                            ></div>
                            {/* 1/2 marker (majority) */}
                            <div
                              className="absolute top-0 bottom-0 w-0.5 bg-gray-400"
                              style={{ left: `${(oneHalf / assemblyType) * 100}%` }}
                            ></div>
                            {/* 2/3 marker */}
                            <div
                              className="absolute top-0 bottom-0 w-px bg-gray-300"
                              style={{ left: `${(twoThirds / assemblyType) * 100}%` }}
                            ></div>
                          </div>

                          {/* Horizontal bar */}
                          <div className="w-full h-10 flex rounded overflow-hidden border-2 border-gray-300 bg-gray-100 relative">
                            {groupParties.map(party => {
                              // Scale to assemblyType, not just group total
                              const percentage = (party.seats / assemblyType) * 100;
                              return (
                                <div
                                  key={party.id}
                                  className="relative group/bar hover:brightness-110 transition-all h-full"
                                  style={{
                                    width: `${percentage}%`,
                                    backgroundColor: party.color
                                  }}
                                  title={`${party.name}: ${party.seats} мандата`}
                                >
                                  {percentage > 8 && (
                                    <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white drop-shadow-md">
                                      {party.seats}
                                    </span>
                                  )}
                                  {/* Remove button on hover */}
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      togglePartyInGroup(group.id, party.id);
                                    }}
                                    className="absolute top-0.5 right-0.5 p-0.5 bg-red-600 text-white rounded opacity-0 group-hover/bar:opacity-100 transition-opacity shadow-lg"
                                    title="Премахни от групата"
                                  >
                                    <Trash2 size={12} />
                                  </button>
                                </div>
                              );
                            })}
                          </div>

                          {/* Marker labels */}
                          <div className="relative flex text-xs text-gray-500 mt-1">
                            <span className="absolute" style={{ left: '0' }}>0</span>
                            <span className="absolute" style={{ left: `${(oneThird / assemblyType) * 100}%`, transform: 'translateX(-50%)' }}>
                              {Math.round(oneThird)}
                            </span>
                            <span className="absolute font-semibold" style={{ left: `${(oneHalf / assemblyType) * 100}%`, transform: 'translateX(-50%)' }}>
                              {Math.round(oneHalf)}
                            </span>
                            <span className="absolute" style={{ left: `${(twoThirds / assemblyType) * 100}%`, transform: 'translateX(-50%)' }}>
                              {Math.round(twoThirds)}
                            </span>
                            <span className="absolute" style={{ right: '0' }}>{assemblyType}</span>
                          </div>
                        </div>

                        {/* Party chips with remove buttons */}
                        <div className="flex flex-wrap gap-1">
                          {groupParties.map(party => (
                            <div
                              key={party.id}
                              className="flex items-center gap-1 px-2 py-1 bg-gray-100 rounded text-xs group/chip hover:bg-gray-200 transition-colors"
                            >
                              <div
                                className="w-2 h-2 rounded"
                                style={{ backgroundColor: party.color }}
                              />
                              <span className="font-medium">{party.name}</span>
                              <span className="text-gray-600">{party.seats}</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  togglePartyInGroup(group.id, party.id);
                                }}
                                className="ml-1 text-gray-400 hover:text-red-600 opacity-0 group-hover/chip:opacity-100 transition-opacity"
                                title="Премахни"
                              >
                                <Trash2 size={10} />
                              </button>
                            </div>
                          ))}
                        </div>

                        {/* Stats */}
                        <div className="text-xs text-gray-700 font-semibold flex justify-between items-center">
                          <span>Общо: {stats.totalSeats} мандата</span>
                          <span className="text-gray-500">({((stats.totalSeats / assemblyType) * 100).toFixed(1)}%)</span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Visualization - Larger with grid */}
        <div className="lg:col-span-2">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Парламентарен състав</h2>

          <div className="bg-gray-50 rounded-lg p-4 relative">
            {/* Rectangular Grid */}
            <svg viewBox="0 0 720 220" className="w-full mb-4">
              {gridSeats.map((seat, i) => {
                const isHovered = hoveredParty && seat.party && seat.party.id === hoveredParty;
                const isInSelectedGroup = selectedGroup && seat.party &&
                  groups.find(g => g.id === selectedGroup)?.partyIds.includes(seat.party.id);
                const selectedGroupData = selectedGroup ? groups.find(g => g.id === selectedGroup) : null;

                return (
                  <g key={i}>
                    {isInSelectedGroup && selectedGroupData && (
                      <rect
                        x={seat.x - 2}
                        y={seat.y - 2}
                        width={seat.size + 4}
                        height={seat.size + 4}
                        rx="6"
                        fill="none"
                        stroke={selectedGroupData.color}
                        strokeWidth="2"
                      />
                    )}
                    <rect
                      x={seat.x}
                      y={seat.y}
                      width={seat.size}
                      height={seat.size}
                      rx="4"
                      fill={seat.color}
                      stroke="#fff"
                      strokeWidth="1"
                      className="cursor-pointer transition-all"
                      style={{
                        transform: isHovered ? 'scale(1.3)' : 'scale(1)',
                        transformOrigin: `${seat.x + seat.size/2}px ${seat.y + seat.size/2}px`
                      }}
                      onMouseEnter={() => {
                        setHoveredSeat(seat);
                        if (seat.party) setHoveredParty(seat.party.id);
                      }}
                      onMouseLeave={() => {
                        setHoveredSeat(null);
                        setHoveredParty(null);
                      }}
                    />
                  </g>
                );
              })}
            </svg>

            {/* Tooltip */}
            {hoveredSeat && hoveredSeat.party && (
              <div className="absolute top-2 left-2 bg-white border-2 border-gray-300 rounded-lg shadow-lg p-2 z-10 text-xs">
                <div className="flex items-center gap-2 mb-1">
                  <div
                    className="w-3 h-3 rounded"
                    style={{ backgroundColor: hoveredSeat.party.color }}
                  />
                  <span className="font-semibold">{hoveredSeat.party.name}</span>
                </div>
                <div className="text-xs text-gray-600 space-y-0.5">
                  <div>Мандати: {hoveredSeat.party.seats}</div>
                  <div>Гласове: {hoveredSeat.party.votes.toFixed(1)}%</div>
                  <div>% мандати: {((hoveredSeat.party.seats / assemblyType) * 100).toFixed(1)}%</div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              {/* Legend */}
              <div>
                <h3 className="text-xs font-semibold mb-2 text-gray-700">Легенда</h3>
                <div className="space-y-1">
                  {partiesWithSeats
                    .filter(party => party.seats > 0)
                    .sort((a, b) => b.seats - a.seats)
                    .map(party => (
                      <div
                        key={party.id}
                        className={`flex items-center gap-2 text-xs p-1 rounded transition-all ${
                          hoveredParty === party.id ? 'bg-blue-100' : ''
                        }`}
                        onMouseEnter={() => setHoveredParty(party.id)}
                        onMouseLeave={() => setHoveredParty(null)}
                      >
                        <div
                          className="w-3 h-3 rounded flex-shrink-0"
                          style={{ backgroundColor: party.color }}
                        />
                        <span className="flex-1 font-medium truncate">{party.name}</span>
                        <span className="text-gray-600 flex-shrink-0">
                          {party.seats} ({party.votes.toFixed(1)}%)
                        </span>
                      </div>
                    ))}
                </div>
              </div>

              {/* Unqualified Parties */}
              {unqualifiedParties.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold mb-2 text-red-700">Под бариерата ({THRESHOLD}%)</h3>
                  <div className="bg-red-50 border border-red-200 rounded p-2 space-y-1">
                    {unqualifiedParties.map(party => (
                      <div key={party.id} className="flex items-center gap-2 text-xs">
                        <div
                          className="w-3 h-3 rounded flex-shrink-0"
                          style={{ backgroundColor: party.color }}
                        />
                        <span className="flex-1 truncate">{party.name}</span>
                        <span className="text-red-600 flex-shrink-0">{party.votes.toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ParliamentSimulator;
