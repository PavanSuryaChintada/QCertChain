# Local / demo consortium chain: Hardhat node with the contracts compiled and deployed on boot.
# "Permissioned EVM for the prototype. Production would run Fabric or a consortium chain — the contract logic is unchanged."
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx hardhat compile
EXPOSE 8545
# Start the node, deploy once it answers, keep the node in the foreground.
CMD ["sh", "-c", "npx hardhat node --hostname 0.0.0.0 & until wget -qO- --post-data='{\"jsonrpc\":\"2.0\",\"method\":\"eth_chainId\",\"params\":[],\"id\":1}' --header='content-type: application/json' http://127.0.0.1:8545 >/dev/null 2>&1; do sleep 1; done; npx hardhat run scripts/deploy.ts --network localhost && wait"]
