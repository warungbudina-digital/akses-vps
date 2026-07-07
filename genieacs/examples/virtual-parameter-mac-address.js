// Virtual Parameter "mac_address" — menyeragamkan lokasi MAC address CPE
// lintas vendor/data-model (TR-098 vs TR-181) ke satu path konsisten:
// VirtualParameters.mac_address._value. Dipakai grpc-server (LinkSubscriberSession,
// lihat internal/store/mongo.go) sebagai kandidat pencarian PERTAMA sebelum
// fallback ke path bawaan yang bervariasi antar perangkat.

const tr098Lan = declare('InternetGatewayDevice.LANDevice.1.LANEthernetInterfaceConfig.1.MACAddress', { value: 1 });
const tr098Wan = declare('InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANEthernetLinkConfig.MACAddress', { value: 1 });
const tr181Eth = declare('Device.Ethernet.Interface.1.MACAddress', { value: 1 });

const mac =
  (tr098Lan.value && tr098Lan.value[0]) ||
  (tr098Wan.value && tr098Wan.value[0]) ||
  (tr181Eth.value && tr181Eth.value[0]) ||
  null;

return [
  ['mac_address', mac, 'xsd:string']
];
