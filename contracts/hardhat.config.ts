import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";

// contracts/BUILD_SPEC.md §1. mining.auto: interval mining adds latency to every write for no benefit.
const config: HardhatUserConfig = {
  solidity: { version: "0.8.24", settings: { optimizer: { enabled: true, runs: 200 } } },
  networks: {
    hardhat: { chainId: 31337, mining: { auto: true } },
    localhost: { url: process.env.CHAIN_RPC || "http://127.0.0.1:8545", chainId: 31337 },
  },
};
export default config;
