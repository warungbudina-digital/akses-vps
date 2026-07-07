// Virtual Parameter "rssi_summary" — expose nilai turunan tanpa mengubah
// data model asli. Dieksekusi tiap kali parameter terkait di-refresh.

const tr181 = declare('Device.WiFi.Radio.1.Stats.SignalStrength', { value: 1 });
const tr098 = declare('InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.X_RSSI', { value: 1 });

const rssi = (tr181.value && tr181.value[0]) || (tr098.value && tr098.value[0]) || null;

let quality = 'unknown';
if (rssi !== null) {
  if (rssi >= -60) quality = 'good';
  else if (rssi >= -75) quality = 'fair';
  else quality = 'poor';
}

return [
  ['rssi_summary', `${rssi ?? 'n/a'} dBm (${quality})`, 'xsd:string']
];
