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

// User read-only terpisah untuk grpc-server (kalau perlu baca ringkasan device,
// tanpa hak tulis ke koleksi GenieACS)
db.createUser({
  user: process.env.GRPC_MONGO_USER || 'grpc_readonly',
  pwd: process.env.GRPC_MONGO_PASSWORD || 'CHANGE_ME',
  roles: [
    { role: 'read', db: 'genieacs' }
  ]
});

// Index penting untuk performa query device GenieACS
db.devices.createIndex({ '_deviceId._SerialNumber': 1 });
db.devices.createIndex({ '_lastInform': 1 });
db.tasks.createIndex({ device: 1, timestamp: 1 });
db.faults.createIndex({ device: 1 });
