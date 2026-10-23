const [pathArg, paramsArg] = process.argv.slice(2);
let params = {};
try {
  params = JSON.parse(paramsArg || '{}');
} catch {
  process.exit(2);
}
const mode = params.__fake_mode || process.env.FAKE_QUERY_MODE || 'ok';
const okData = () => console.log(JSON.stringify({ ok: true, data: { path: pathArg, params, source: 'fake' } }));

if (mode === 'hang') {
  setInterval(() => {}, 1_000_000_000);
} else if (mode === 'slow') {
  setTimeout(okData, 600);
} else if (mode === 'crash') {
  console.error('fake crash');
  process.exit(1);
} else if (mode === 'fail') {
  console.log(JSON.stringify({ ok: false, error: { code: 'UPSTREAM_UNAVAILABLE', message: 'fake upstream down' } }));
} else {
  okData();
}
