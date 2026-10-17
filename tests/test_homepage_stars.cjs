const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise the badge refresh independently of unrelated navigation and tracking.
const source = fs.readFileSync('assets/js/homepage.js', 'utf8');
const badgeScript = source.slice(0, source.indexOf('  // Keep the original MapMyVisitors')) + '\n})();';
const snapshotDate = '2026-10-17T01:00:00Z';
const valid = {
  schemaVersion: 1, username: 'JustlfC03', updated_at: '2026-10-18T01:00:00Z',
  total_stars: 500, owned_stars: 370, contributed_stars: 130,
};

async function render(data, {hostname = 'justlfc03.github.io', failure = false} = {}) {
  const attributes = {
    'data-github-user': 'JustlfC03', 'data-updated-at': snapshotDate,
    'data-stats-url': 'https://raw.githubusercontent.com/JustlfC03/JustlfC03.github.io/github-star-stats/github-stars.json',
  };
  const badge = {
    src: 'snapshot.svg', alt: 'Original total', title: 'Original details',
    getAttribute: key => attributes[key],
    setAttribute: (key, value) => { attributes[key] = value; },
  };
  let requests = 0;
  const fetch = async () => {
    requests++;
    if (failure) throw new Error('Offline');
    return {ok: true, json: async () => data};
  };
  vm.runInNewContext(badgeScript, {
    document: {currentScript: null, querySelector: () => badge},
    window: {fetch, location: {hostname, protocol: 'https:'}}, fetch,
  });
  await new Promise(resolve => setImmediate(resolve));
  return {badge, requests, attributes};
}

(async () => {
  const refreshed = await render(valid);
  assert.match(refreshed.badge.src, /Stars-500-/);
  assert.match(refreshed.badge.title, /370 owned \+ 130 contributed/);
  assert.match(refreshed.badge.alt, /500$/);
  assert.equal(refreshed.attributes['data-updated-at'], valid.updated_at);
  const lower = await render({...valid, total_stars: 2, owned_stars: 1, contributed_stars: 1});
  assert.match(lower.badge.src, /Stars-2-/); // Unstars must be reflected too.
  for (const invalid of [
    null,
    {...valid, username: 'SomeoneElse'},
    {...valid, schemaVersion: 2},
    {...valid, total_stars: 501},
    {...valid, total_stars: '500'},
    {...valid, owned_stars: -1, contributed_stars: 501},
    {...valid, updated_at: '2026-10-16T00:00:00Z'},
    {...valid, updated_at: 'invalid'},
  ]) {
    assert.equal((await render(invalid)).badge.src, 'snapshot.svg');
  }
  assert.equal((await render(valid, {failure: true})).badge.src, 'snapshot.svg');
  for (const hostname of ['localhost', '127.0.0.1', '[::1]']) {
    const local = await render(valid, {hostname});
    assert.equal(local.requests, 0);
    assert.equal(local.badge.src, 'snapshot.svg');
  }
  console.log('GitHub badge refresh, validation, fallback and local-preview checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
