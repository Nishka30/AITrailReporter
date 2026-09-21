async function run() {
  console.log('about to import photoLocationResolver...');
  const mod = await import('./src/location/photoLocationResolver');
  console.log('photoLocationResolver loaded OK:', typeof mod.resolvePhotoProvenance);
}
run();
