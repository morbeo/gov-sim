// Pure election rules and helpers: parliamentary seats, presidential rounds, referendums, CSV.
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

  // Presidential round 1 (Bulgaria): more than half of valid votes AND turnout above 50% wins outright;
  // otherwise the top two go to a runoff. Mayors use the same rule without the turnout condition.
  // Rows flagged isOther ("Други") count towards the total but can't win or reach the runoff.
  function firstRound(candidates, turnout, { requireTurnout = true } = {}) {
    const total = candidates.reduce((sum, c) => sum + Math.max(0, c.votes), 0);
    const ranked = candidates
      .map(c => ({ ...c, share: total > 0 ? (Math.max(0, c.votes) / total) * 100 : 0 }))
      .sort((a, b) => b.share - a.share);
    const contenders = ranked.filter(c => !c.isOther && c.share > 0);
    const leader = contenders[0] || null;
    const hasMajority = !!leader && leader.share > 50;
    const turnoutOk = !requireTurnout || turnout > 50;
    if (hasMajority && turnoutOk) return { ranked, winner: leader, runoff: null, reason: null };
    return {
      ranked,
      winner: null,
      runoff: contenders.length >= 2 ? [contenders[0], contenders[1]] : null,
      reason: hasMajority ? 'turnout' : 'majority'
    };
  }

  // National referendum (Direct Participation Act, art. 23): adopted when turnout is at least the
  // turnout of the last National Assembly election and more than half vote yes; with lower turnout
  // but above 20% and a yes majority, the proposal goes to the National Assembly.
  function referendumOutcome(yesShare, turnout, lastElectionTurnout) {
    if (yesShare <= 50) return 'rejected';
    if (turnout >= lastElectionTurnout) return 'adopted';
    if (turnout > 20) return 'parliament';
    return 'rejected';
  }

  // A published poll -> candidate shares among decided voters. Undecided and "none" are dropped;
  // the published "other" share (or the unexplained remainder) becomes one "Други" row.
  function pollToShares(poll) {
    const listed = Object.entries(poll.shares).map(([id, share]) => ({ id, share }));
    const listedSum = listed.reduce((sum, c) => sum + c.share, 0);
    const excluded = (poll.undecided || 0) + (poll.none || 0);
    const other = poll.other != null ? poll.other : Math.max(0, 100 - listedSum - excluded);
    if (other >= 0.05) listed.push({ id: 'other', share: other, isOther: true });
    const decided = listed.reduce((sum, c) => sum + c.share, 0);
    return listed.map(c => ({ ...c, share: Math.round((c.share / decided) * 1000) / 10 }));
  }

  const api = { allocateSeats, parseCSV, toCSV, partiesFromCSV, firstRound, referendumOutcome, pollToShares };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.VoteSim = api;
})(this);
