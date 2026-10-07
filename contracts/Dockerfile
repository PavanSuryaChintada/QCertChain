# Local / demo consortium chain: Hardhat node with the contracts compiled and deployed on boot.
# "Permissioned EVM for the prototype. Production would run Fabric or a consortium chain — the contract logic is unchanged."
#
# Build context is the REPO ROOT (same as Railway, which always builds from the repo root):
#   docker build -f contracts/Dockerfile -t qcertchain-hardhat .
# The root .dockerignore keeps the host's node_modules / artifacts / cache out of the image.
FROM node:20-alpine
WORKDIR /app
COPY contracts/package.json contracts/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY contracts/ ./
RUN npx hardhat compile
EXPOSE 8545
# Start the node, deploy once it answers, keep the node in the foreground.
# A fresh node always yields the addresses committed in contracts/deployments/localhost.json.
CMD ["sh", "-c", "npx hardhat node --hostname 0.0.0.0 & until wget -qO- --post-data='{\"jsonrpc\":\"2.0\",\"method\":\"eth_chainId\",\"params\":[],\"id\":1}' --header='content-type: application/json' http://127.0.0.1:8545 >/dev/null 2>&1; do sleep 1; done; npx hardhat run scripts/deploy.ts --network localhost && wait"]
