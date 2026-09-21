// TEST-ONLY Node ESM loader hook: redirects the one real import of
// './locationService' inside photoLocationResolver.ts to a dependency-free
// stub, so the test can exercise the REAL photoLocationResolver.ts decision
// tree under plain Node without needing a full React Native/Expo test
// harness (this project has none). Nothing else is stubbed or mocked --
// coordinateValidation.ts and photoLocationResolver.ts run unmodified.
const STUB_URL = new URL('./src/location/__locationServiceStub__.ts', import.meta.url).href;

export async function resolve(specifier, context, nextResolve) {
  if (specifier.includes('locationService') && !specifier.includes('Stub')) {
    process.stderr.write(`[test-loader] intercepting ${specifier}\n`);
    return { url: STUB_URL, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}
