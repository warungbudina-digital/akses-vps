// Provision script "set-wifi" — dieksekusi genieacs-cwmp saat preset match.
// Contoh: set SSID & password default berbasis serial number device
// (baik untuk data model TR-098 InternetGatewayDevice maupun TR-181 Device:2).

const serial = declare('DeviceID.SerialNumber', { value: 1 }).value[0];
const ssid = `AKSES-${serial.slice(-6)}`;

// TR-098
declare('InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID', null, { value: ssid });
declare('InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.BeaconType', null, { value: 'WPAand11i' });
declare('InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.KeyPassphrase', null, {
  value: process.env.DEFAULT_WIFI_PASSWORD || 'ChangeMe123!'
});

// TR-181 (fallback jika device pakai Device:2 data model)
declare('Device.WiFi.SSID.1.SSID', null, { value: ssid });
declare('Device.WiFi.AccessPoint.1.Security.KeyPassphrase', null, {
  value: process.env.DEFAULT_WIFI_PASSWORD || 'ChangeMe123!'
});

log(`Provision set-wifi applied for serial=${serial}, ssid=${ssid}`);
