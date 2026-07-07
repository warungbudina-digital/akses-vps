// Dijalankan otomatis oleh image mongo resmi saat container pertama kali init
// (docker-entrypoint-initdb.d), HANYA jika MONGO_INITDB_ROOT_USERNAME/PASSWORD
// sudah diset via env — lihat docker-compose.reference.yml.
//
// Membuat database + user khusus GenieACS (least privilege, bukan root).

db = db.getSiblingDB('genieacs');

db.createUser({
  user: process.env.GENIEACS_MONGO_USER || 'genieacs',
  pwd: process.env.GENIEACS_MONGO_PASSWORD || 'CHANGE_ME',
  roles: [
    { role: 'readWrite', db: 'genieacs' }
  ]
});

// Role khusus grpc-server: read-only ke koleksi GenieACS (devices, dst),
// tapi read+write TERBATAS ke koleksi subscriber_links saja — dipakai untuk
// korelasi sesi RADIUS <-> device via LinkSubscriberSession RPC (lihat
// docs/13-accel-ppp-integration.md). Sengaja BUKAN readWrite penuh ke
// seluruh db genieacs supaya grpc-server tidak bisa mengubah data GenieACS.
db.createRole({
  role: 'grpcServerRole',
  privileges: [
    { resource: { db: 'genieacs', collection: 'devices' }, actions: ['find'] },
    { resource: { db: 'genieacs', collection: 'subscriber_links' }, actions: ['find', 'insert', 'update'] }
  ],
  roles: []
});

db.createUser({
  user: process.env.GRPC_MONGO_USER || 'grpc_readonly',
  pwd: process.env.GRPC_MONGO_PASSWORD || 'CHANGE_ME',
  roles: [
    { role: 'grpcServerRole', db: 'genieacs' }
  ]
});

// Index penting untuk performa query device GenieACS
db.devices.createIndex({ '_deviceId._SerialNumber': 1 });
db.devices.createIndex({ '_lastInform': 1 });
db.tasks.createIndex({ device: 1, timestamp: 1 });
db.faults.createIndex({ device: 1 });

// Index untuk korelasi subscriber <-> device (lihat docs/13-accel-ppp-integration.md)
db.subscriber_links.createIndex({ device_id: 1 });
db.subscriber_links.createIndex({ pop: 1, status: 1 });
