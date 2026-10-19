// Pure helpers for the vote simulator: seat allocation and CSV.
// Loaded as a plain <script> in the browser (exposes window.VoteSim) and via require() in tests.
(function (root) {
  // Largest remainder (Hare–Niemeyer) among parties at or above the threshold.
  // Equal remainders go to the party with more votes.
  function allocateSeats(parties, totalSeats, threshold) {
    const qualified = parties.filter(p => p.votes >= threshold && p.votes > 0);
    const qualifiedVotes = qualified.reduce((sum, p) => sum + p.votes, 0);
    if (qualifiedVotes === 0) return parties.map(p => ({ ...p, seats: 0, exactSeats: 0 }));

    const result = parties.map(p => {
      if (p.votes < threshold || p.votes <= 0) return { ...p, seats: 0, exactSeats: 0 };
      const exactSeats = (p.votes / qualifiedVotes) * totalSeats;
      return { ...p, exactSeats, seats: Math.floor(exactSeats) };
    });

    const assigned = result.reduce((sum, p) => sum + p.seats, 0);
    const byRemainder = result
      .filter(p => p.exactSeats > 0)
      .sort((a, b) => (b.exactSeats - b.seats) - (a.exactSeats - a.seats) || b.votes - a.votes);
    for (let i = 0; i < totalSeats - assigned; i++) byRemainder[i % byRemainder.length].seats++;

    return result;
  }

  // RFC 4180-style parser. Detects ',' or ';' (Bulgarian Excel) from the header line; strips a BOM.
  function parseCSV(text) {
    text = text.replace(/^﻿/, '');
    const firstLine = text.split(/\r?\n/, 1)[0];
    const delim = (firstLine.match(/;/g) || []).length > (firstLine.match(/,/g) || []).length ? ';' : ',';
    const rows = [];
    let row = [], field = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (c === '"') quoted = false;
        else field += c;
      } else if (c === '"') quoted = true;
      else if (c === delim) { row.push(field); field = ''; }
      else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(field); rows.push(row); row = []; field = '';
      } else field += c;
    }
    if (field !== '' || row.length) { row.push(field); rows.push(row); }
    return rows.filter(r => r.some(f => f.trim() !== ''));
  }

  // UTF-8 BOM so Excel opens Cyrillic correctly; quotes doubled inside fields.
  function toCSV(rows) {
    const cell = v => {
      const s = String(v);
      return /[",;\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    return '﻿' + rows.map(r => r.map(cell).join(',')).join('\r\n') + '\r\n';
  }

  // Parties from CSV rows: name, colour, vote % (header row skipped; decimal comma accepted).
  function partiesFromCSV(text, firstId) {
    return parseCSV(text).slice(1)
      .filter(r => r[0] && r[0].trim())
      .map((r, i) => {
        const votes = parseFloat(String(r[2] || '').replace(',', '.'));
        const color = /^#[0-9a-f]{6}$/i.test((r[1] || '').trim()) ? r[1].trim() : '#9ca3af';
        return { id: firstId + i, name: r[0].trim(), color, votes: isNaN(votes) ? 0 : votes };
      });
  }

  const api = { allocateSeats, parseCSV, toCSV, partiesFromCSV };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.VoteSim = api;
})(this);
