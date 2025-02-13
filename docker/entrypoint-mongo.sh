#!/bin/bash

# Exit on any command failure
set -e

export MONGO_HOSTNAME=${MONGO_HOSTNAME:-localhost}
echo "MONGO_HOSTNAME: ${MONGO_HOSTNAME}"

# start mongo service
mkdir -p /data/db1 /data/db2
echo "Starting mongo servers"
/usr/bin/mongod --port=27021 --dbpath=/data/db1 --bind_ip_all --replSet rs0 --logpath /dev/stderr &
/usr/bin/mongod --port=27022 --dbpath=/data/db2 --bind_ip_all --replSet rs0 --logpath /dev/stderr &

# Sleep and wait for server to start
while ! mongosh --quiet --port=27021 --eval "exit" 2>/dev/null; do sleep 1; done; echo "mongo1 started"
while ! mongosh --quiet --port=27022 --eval "exit" 2>/dev/null; do sleep 1; done; echo "mongo2 started"

# If not bootstrapped, bootstrap
if ! mongosh --quiet --port=27021 --eval "rs.status()" 1>/dev/null 2>&1; then
    mongosh --quiet --port=27021 <<EOF
        var config = {
            "_id": "rs0",
            "version": 1,
            "members": [
                {
                    "_id": 1,
                    "host": "${MONGO_HOSTNAME}:27021",
                    "priority": 1
                }, {
                    "_id": 2,
                    "host": "${MONGO_HOSTNAME}:27022",
                    "priority": 2
                },
            ]
        };
        rs.initiate(config, { force: true });
EOF
fi

# Wait for replicaset config to be accepted
while ! mongosh --quiet --port=27021 --eval "rs.status()" 1>/dev/null 2>&1; do sleep 1; done

# Wait for replicaset to form
while [[ 1 -ne "$(mongosh --quiet --port=27021 --eval "rs.status().ok")" ]]; do
  sleep 1;
done

sleep inf
