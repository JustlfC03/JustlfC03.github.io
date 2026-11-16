const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise badge refresh independently of navigation and visitor tracking.
const source = fs.readFileSync('assets/js/homepage.js', 'utf8');
const badgeScript = source.slice(0, source.indexOf('  // Keep the original MapMyVisitors')) + '\n})();';
const snapshotDate = '2026-10-17T01:00:00Z';
const valid = {
  schemaVersion: 1, username: 'JustlfC03', updated_at: '2026-10-18T01:00:00Z',
  total_stars: 500, owned_stars: 370, contributed_stars: 130,
};
const makeSvg = count => `<svg xmlns="http://www.w3.org/2000/svg" width="90" height="20"><title>Stars &amp; code: ${count}</title><g font-family="Verdana,Geneva,sans-serif"><text x="10" textLength="40">Stars</text><text x="55" textLength="20">${count}</text></g></svg>`;
const decoded = badge => decodeURIComponent(badge.src.split(',').slice(1).join(','));

function image(attributes = {}) {
  return {
    src: 'snapshot.svg', alt: 'Original total', title: 'Original details',
    getAttribute: key => attributes[key],
    setAttribute: (key, value) => { attributes[key] = value; },
    attributes,
  };
}

async function render(data, {
  hostname = 'justlfc03.github.io', protocol = 'https:', failure = false,
  badgeFailure = false, badgeStatus = true, svg, ordinary = false, ordinaryStyle = 'social',
} = {}) {
  const badge = image({
    'data-github-user': 'JustlfC03', 'data-updated-at': snapshotDate,
    'data-stats-url': 'https://raw.githubusercontent.com/JustlfC03/JustlfC03.github.io/github-star-stats/github-stars.json',
    'data-badge-source': 'https://img.shields.io/badge/Stars-631-blue',
  });
  const other = ordinary ? image({'data-badge-source': 'https://img.shields.io/github/stars/owner/repo?label=Code+Stars&style=' + ordinaryStyle}) : null;
  const requests = [];
  const fetch = async url => {
    requests.push(url);
    if (failure) throw new Error('Offline');
    if (url === badge.attributes['data-stats-url']) return {ok: true, json: async () => data};
    if (badgeFailure) throw new Error('Badge offline');
    const count = other && url === other.attributes['data-badge-source'] ? '1.2k' : data.total_stars.toLocaleString('en-US');
    return {ok: badgeStatus, text: async () => svg === undefined ? makeSvg(count) : svg};
  };
  vm.runInNewContext(badgeScript, {
    document: {
      currentScript: null, querySelector: () => badge,
      querySelectorAll: () => other ? [badge, other] : [badge],
    },
    window: {fetch, location: {hostname, protocol}}, fetch,
  });
  await new Promise(resolve => setImmediate(resolve));
  return {badge, other, requests, attributes: badge.attributes};
}

function assertBadgeTypography(badge, count, social = false) {
  assert.match(badge.src, /^data:image\/svg\+xml;charset=utf-8,/);
  const svg = decoded(badge);
  assert.match(svg, /font-family="Helvetica Neue, Helvetica, Arial, sans-serif"/);
  assert.doesNotMatch(svg, /textLength|Verdana|Georgia/);
  for (const [, attributes, value] of svg.matchAll(/<text\b([^>]*)>([\s\S]*?)<\/text>/g)) {
    const expected = social ? '700' : value === count ? '600' : '400';
    assert.ok(attributes.includes(`font-weight="${expected}"`), `${value}: ${attributes}`);
    assert.equal((attributes.match(/font-weight=/g) || []).length, 1);
  }
  assert.ok(svg.includes(`>${count}</text>`));
  assert.ok(svg.includes('Stars &amp; code:')); // SVG entities survive data-URL encoding.
}

(async () => {
  const refreshed = await render(valid);
  assertBadgeTypography(refreshed.badge, '500');
  assert.match(refreshed.badge.title, /370 owned \+ 130 contributed/);
  assert.match(refreshed.badge.alt, /500$/);
  assert.equal(refreshed.attributes['data-updated-at'], valid.updated_at);
  assert.equal(refreshed.requests.length, 2); // No parallel request for the stale total.
  assert.match(refreshed.attributes['data-badge-source'], /Stars-500-/);
  const lower = await render({...valid, total_stars: 2, owned_stars: 1, contributed_stars: 1});
  assertBadgeTypography(lower.badge, '2'); // Unstars must be reflected too.
  const large = await render({...valid, total_stars: 12000, owned_stars: 10000, contributed_stars: 2000});
  assertBadgeTypography(large.badge, '12,000');
  assert.match(large.requests[1], /Stars-12%2C000-/);

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
    const result = await render(invalid);
    assert.equal(result.badge.src, 'snapshot.svg');
    assert.equal(result.requests.length, 1);
    assert.equal(result.attributes['data-updated-at'], snapshotDate);
  }
  for (const options of [
    {failure: true}, {badgeFailure: true}, {badgeStatus: false},
    {svg: '<html>Gateway error 502</html>'},
    {svg: '<svg xmlns="http://www.w3.org/2000/svg"><g font-family="Verdana"><text>repo not found</text></g></svg>'},
    {svg: '<svg xmlns="http://www.w3.org/2000/svg"><text>500</text></svg>'},
  ]) {
    const result = await render(valid, options);
    assert.equal(result.badge.src, 'snapshot.svg');
    assert.equal(result.badge.alt, 'Original total');
    assert.equal(result.badge.title, 'Original details');
    assert.equal(result.attributes['data-updated-at'], snapshotDate);
  }
  const other = await render(valid, {ordinary: true});
  assertBadgeTypography(other.other, '1.2k', true);
  assert.equal(other.requests.length, 3);
  const compactFlat = await render(valid, {ordinary: true, ordinaryStyle: 'flat'});
  assertBadgeTypography(compactFlat.other, '1.2k');
  const existingWeight = makeSvg('500').replace(/<text /g, '<text font-weight="900" ');
  assertBadgeTypography((await render(valid, {svg: existingWeight})).badge, '500');
  const singleQuotes = makeSvg('500').replace('font-family="Verdana,Geneva,sans-serif"', "font-family='Helvetica Neue,Helvetica,Arial,sans-serif'").replace(/textLength="(\d+)"/g, "textLength='$1'");
  assertBadgeTypography((await render(valid, {svg: singleQuotes})).badge, '500');
  for (const hostname of ['localhost', '127.0.0.1', '[::1]']) {
    const local = await render(valid, {hostname, ordinary: true});
    assert.equal(local.requests.length, 0);
    assert.equal(local.badge.src, 'snapshot.svg');
    assert.equal(local.other.src, 'snapshot.svg');
  }
  const file = await render(valid, {hostname: '', protocol: 'file:', ordinary: true});
  assert.equal(file.requests.length, 0);
  console.log('Badge typography, refresh, counts, validation, fallback and local-preview checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
