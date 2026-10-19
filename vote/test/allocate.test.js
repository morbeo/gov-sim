// Run: node --test vote/test/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const { allocateSeats, parseCSV, toCSV, partiesFromCSV } = require('../src/allocate.js');

const seatsOf = (parties, n = 240, t = 4) =>
  Object.fromEntries(allocateSeats(parties, n, t).map(p => [p.name, p.seats]));

test('allocates every seat among parties over the threshold', () => {
  const parties = [
    { name: 'А', votes: 26.5 }, { name: 'Б', votes: 24.3 }, { name: 'В', votes: 17.2 },
    { name: 'Г', votes: 13.8 }, { name: 'Д', votes: 9.0 }, { name: 'Е', votes: 5.2 }, { name: 'Ж', votes: 3.8 },
  ];
  for (const n of [240, 400]) {
    const s = seatsOf(parties, n);
    assert.equal(Object.values(s).reduce((a, b) => a + b, 0), n);
    assert.equal(s['Ж'], 0);
  }
});

test('matches a hand-computed Hare–Niemeyer split', () => {
  // quotas for 10 seats: 4.7, 3.2, 2.1 -> floors 4,3,2 (9); largest remainder 0.7 -> А
  assert.deepEqual(seatsOf([{ name: 'А', votes: 47 }, { name: 'Б', votes: 32 }, { name: 'В', votes: 21 }], 10, 0),
    { 'А': 5, 'Б': 3, 'В': 2 });
});

test('party exactly at the threshold qualifies', () => {
  assert.ok(seatsOf([{ name: 'А', votes: 96 }, { name: 'Б', votes: 4 }])['Б'] > 0);
});

test('equal remainders go to the party with more votes', () => {
  // quotas for 2 seats: 0.5, 1.5 -> floors 0,1; remainders tie at 0.5 -> Б has more votes
  assert.deepEqual(seatsOf([{ name: 'А', votes: 25 }, { name: 'Б', votes: 75 }], 2, 0), { 'А': 0, 'Б': 2 });
});

test('no qualified parties gives zero seats', () => {
  assert.deepEqual(seatsOf([{ name: 'А', votes: 3 }, { name: 'Б', votes: 0 }]), { 'А': 0, 'Б': 0 });
});

test('CSV round-trip keeps quotes, commas and Cyrillic', () => {
  const rows = [['Име', 'Цвят', 'Гласове (%)'], ['"Нова", партия', '#112233', '4.5']];
  assert.deepEqual(parseCSV(toCSV(rows)), rows);
});

test('CSV import accepts semicolons and decimal commas', () => {
  const p = partiesFromCSV('Име;Цвят;Гласове (%)\r\nГЕРБ-СДС;#0054a6;26,5\r\nБСП;bad;9\r\n', 10);
  assert.deepEqual(p, [
    { id: 10, name: 'ГЕРБ-СДС', color: '#0054a6', votes: 26.5 },
    { id: 11, name: 'БСП', color: '#9ca3af', votes: 9 },
  ]);
});

test('CSV import reads the example file format', () => {
  const p = partiesFromCSV('Име,Цвят,Гласове (%)\n"ГЕРБ-СДС",#3b82f6,26.5\n"ПП-ДБ",#ef4444,24.3\n', 1);
  assert.equal(p.length, 2);
  assert.equal(p[1].name, 'ПП-ДБ');
});
