# GenieACS tidak menerbitkan image Docker resmi — image ini dibangun dari
# paket npm resmi (https://www.npmjs.com/package/genieacs), berisi keempat
# binary (genieacs-cwmp/nbi/fs/ui) sehingga satu image dipakai untuk semua
# service GenieACS, dibedakan lewat `command:` di docker-compose.
#
# Catatan: symlink /usr/local/bin/genieacs-* dibuat manual (bukan di-copy
# langsung) karena `COPY` men-dereference symlink jadi file biasa, yang
# merusak resolusi node_modules relatif (butuh lokasi asli di
# node_modules/genieacs/bin agar bisa menemukan node_modules/genieacs/node_modules).
FROM node:20-alpine AS builder
RUN npm install -g genieacs@1.2.16

FROM node:20-alpine
RUN apk add --no-cache tini
COPY --from=builder /usr/local/lib/node_modules/genieacs /usr/local/lib/node_modules/genieacs
RUN ln -s /usr/local/lib/node_modules/genieacs/bin/genieacs-cwmp /usr/local/bin/genieacs-cwmp && \
    ln -s /usr/local/lib/node_modules/genieacs/bin/genieacs-nbi /usr/local/bin/genieacs-nbi && \
    ln -s /usr/local/lib/node_modules/genieacs/bin/genieacs-fs /usr/local/bin/genieacs-fs && \
    ln -s /usr/local/lib/node_modules/genieacs/bin/genieacs-ui /usr/local/bin/genieacs-ui

RUN mkdir -p /opt/genieacs/ext && chown -R node:node /opt/genieacs
USER node
WORKDIR /opt/genieacs

ENTRYPOINT ["/sbin/tini", "--"]
