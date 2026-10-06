# BUILD SPEC — contracts/

Solidity implementation contract. Read `../docs/BLOCKCHAIN.md` first — it covers *why* each contract exists. This covers *how* to build them.

---

## Why Hardhat and not Hyperledger Fabric

Fabric is the correct enterprise answer and a two-day install — channels, MSPs, CA setup, chaincode packaging. That is the entire build window.

Hardhat gives you a chain in one command, pre-funded accounts that stand in for different organisations, instant mining, and a test framework. **The multi-org demo is identical.**

Say this if asked: *"Permissioned EVM for the prototype. Production would run Fabric or a consortium chain — the contract logic is unchanged."*

---

## Layout

```
contracts/
├── Dockerfile
├── hardhat.config.ts
├── package.json
├── contracts/
│   ├── OrgRegistry.sol
│   ├── CampaignRegistry.sol
│   ├── EvidenceAnchor.sol
│   └── Attestation.sol
├── scripts/
│   ├── deploy.ts
│   └── seed-orgs.ts
├── test/
│   ├── OrgRegistry.test.ts
│   ├── CampaignRegistry.test.ts
│   └── EvidenceAnchor.test.ts
└── deployments/
    └── localhost.json        # addresses written here, read by the API
```

`deployments/localhost.json` is the handoff to Python. The deploy script writes it; `services/api/ledger_service.py` reads it. **Do not hardcode addresses anywhere.**

---

## Build order

```
1. hardhat init + config + Dockerfile     → npx hardhat node runs
2. OrgRegistry.sol   + test                → permissioning works
3. deploy.ts + seed-orgs.ts                → two orgs registered
4. CampaignRegistry.sol + test             → publish + query by kitHash
5. EvidenceAnchor.sol + test               → anchor + verify
6. Python wiring (services/api/ledger_service.py)
7. Attestation.sol + test                  → dispute flow
```

**Step 4's `kitHash` query is the demo payoff.** Get it working before anything else optional.

---

## 1. `hardhat.config.ts`

```ts
import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";

const config: HardhatUserConfig = {
  solidity: { version: "0.8.24", settings: { optimizer: { enabled: true, runs: 200 } } },
  networks: {
    hardhat: { chainId: 31337, mining: { auto: true } },
    localhost: { url: "http://127.0.0.1:8545", chainId: 31337 },
  },
};
export default config;
```

**`mining.auto: true`.** Interval mining adds latency to every write and makes the demo feel sluggish for no benefit.

---

## 2. `OrgRegistry.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract OrgRegistry {
    struct Org { string name; bool active; uint256 registeredAt; }

    address public admin;
    mapping(address => Org) public orgs;
    address[] private _orgList;

    event OrgRegistered(address indexed who, string name);
    event OrgDeactivated(address indexed who);

    error NotAdmin();
    error NotRegisteredOrg();
    error AlreadyRegistered();

    constructor() { admin = msg.sender; }

    modifier onlyAdmin() { if (msg.sender != admin) revert NotAdmin(); _; }

    function registerOrg(address who, string calldata name) external onlyAdmin {
        if (orgs[who].registeredAt != 0) revert AlreadyRegistered();
        orgs[who] = Org(name, true, block.timestamp);
        _orgList.push(who);
        emit OrgRegistered(who, name);
    }

    function deactivateOrg(address who) external onlyAdmin {
        orgs[who].active = false;
        emit OrgDeactivated(who);
    }

    function isActive(address who) external view returns (bool) {
        return orgs[who].active;
    }

    function listOrgs() external view returns (address[] memory) { return _orgList; }
}
```

**Custom errors, not `require` strings.** Cheaper, and they decode cleanly in ethers v6.

---

## 3. `CampaignRegistry.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IOrgRegistry { function isActive(address) external view returns (bool); }

contract CampaignRegistry {
    struct Campaign {
        bytes32 iocRoot;
        bytes32 kitHash;
        uint16  domainCount;
        uint8   confidence;      // 0-100
        address reporter;
        uint64  timestamp;
    }

    IOrgRegistry public immutable orgRegistry;

    mapping(bytes32 => Campaign) public campaigns;          // campaignId => Campaign
    mapping(bytes32 => bytes32[]) private _byKit;           // kitHash  => campaignIds
    mapping(bytes32 => address[]) private _corroborations;

    event CampaignPublished(
        bytes32 indexed campaignId,
        bytes32 indexed kitHash,
        address indexed reporter,
        bytes32 iocRoot,
        uint16  domainCount,
        uint8   confidence
    );
    event Corroborated(bytes32 indexed campaignId, address indexed org);

    error NotOrg();
    error AlreadyPublished();
    error UnknownCampaign();
    error SelfCorroboration();

    constructor(address registry) { orgRegistry = IOrgRegistry(registry); }

    modifier onlyOrg() {
        if (!orgRegistry.isActive(msg.sender)) revert NotOrg();
        _;
    }

    function publishCampaign(
        bytes32 campaignId, bytes32 iocRoot, bytes32 kitHash,
        uint16 domainCount, uint8 confidence
    ) external onlyOrg {
        if (campaigns[campaignId].timestamp != 0) revert AlreadyPublished();
        campaigns[campaignId] = Campaign(
            iocRoot, kitHash, domainCount, confidence, msg.sender, uint64(block.timestamp)
        );
        _byKit[kitHash].push(campaignId);
        emit CampaignPublished(campaignId, kitHash, msg.sender,
                               iocRoot, domainCount, confidence);
    }

    /// THE INHERITANCE QUERY — how org 2 gets org 1's work
    function findByKit(bytes32 kitHash) external view returns (bytes32[] memory) {
        return _byKit[kitHash];
    }

    function corroborate(bytes32 campaignId) external onlyOrg {
        Campaign memory c = campaigns[campaignId];
        if (c.timestamp == 0) revert UnknownCampaign();
        if (c.reporter == msg.sender) revert SelfCorroboration();
        _corroborations[campaignId].push(msg.sender);
        emit Corroborated(campaignId, msg.sender);
    }

    function corroborationsOf(bytes32 campaignId) external view returns (address[] memory) {
        return _corroborations[campaignId];
    }
}
```

**Traps**
- **`kitHash` must be indexed.** Three indexed params is the EVM maximum and all three here are needed.
- `_byKit` is unbounded. Fine at demo scale; note the limit rather than pretending it isn't there.
- `uint64` for timestamps, not `uint256` — packs into one slot with the address.
- **Never store an IOC list on-chain.** Only `iocRoot`. `BLOCKCHAIN.md` §2.

---

## 4. `EvidenceAnchor.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IOrgRegistry2 { function isActive(address) external view returns (bool); }

contract EvidenceAnchor {
    struct Anchor {
        bytes32 bundleRoot;
        bytes32 campaignId;
        address collector;
        uint64  timestamp;
    }

    IOrgRegistry2 public immutable orgRegistry;
    mapping(bytes32 => Anchor) public anchors;   // bundleId => Anchor

    event EvidenceAnchored(
        bytes32 indexed bundleId, bytes32 indexed campaignId,
        address indexed collector, bytes32 bundleRoot
    );

    error NotOrg();
    error AlreadyAnchored();

    constructor(address registry) { orgRegistry = IOrgRegistry2(registry); }

    modifier onlyOrg() { if (!orgRegistry.isActive(msg.sender)) revert NotOrg(); _; }

    function anchor(bytes32 bundleId, bytes32 bundleRoot, bytes32 campaignId)
        external onlyOrg
    {
        if (anchors[bundleId].timestamp != 0) revert AlreadyAnchored();
        anchors[bundleId] = Anchor(bundleRoot, campaignId, msg.sender, uint64(block.timestamp));
        emit EvidenceAnchored(bundleId, campaignId, msg.sender, bundleRoot);
    }

    function verify(bytes32 bundleId, bytes32 claimedRoot) external view returns (bool) {
        return anchors[bundleId].bundleRoot == claimedRoot
            && anchors[bundleId].timestamp != 0;
    }
}
```

**`AlreadyAnchored` is the whole point.** An anchor is immutable once written — that is what makes the timestamp mean something in an inquiry.

---

## 5. `Attestation.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IOrgRegistry3 { function isActive(address) external view returns (bool); }

contract Attestation {
    enum Verdict { Confirmed, Dismissed, Disputed }

    IOrgRegistry3 public immutable orgRegistry;
    mapping(bytes32 => mapping(address => Verdict)) public attestations;
    mapping(bytes32 => address[]) private _attestors;

    event Attested(bytes32 indexed subjectHash, address indexed org,
                   Verdict verdict, uint64 timestamp);

    error NotOrg();

    constructor(address registry) { orgRegistry = IOrgRegistry3(registry); }
    modifier onlyOrg() { if (!orgRegistry.isActive(msg.sender)) revert NotOrg(); _; }

    function attest(bytes32 subjectHash, Verdict v) external onlyOrg {
        if (attestations[subjectHash][msg.sender] == Verdict.Confirmed
            && _attestors[subjectHash].length == 0) {
            _attestors[subjectHash].push(msg.sender);
        }
        attestations[subjectHash][msg.sender] = v;
        emit Attested(subjectHash, msg.sender, v, uint64(block.timestamp));
    }

    function attestorsOf(bytes32 subjectHash) external view returns (address[] memory) {
        return _attestors[subjectHash];
    }
}
```

**`Disputed` matters more than it looks.** A system that only accumulates accusations with no dissent mechanism is a censorship tool. Say this if a judge asks about false positives.

---

## 6. `scripts/deploy.ts`

```ts
import { ethers } from "hardhat";
import fs from "fs";

async function main() {
  const [admin, org1, org2] = await ethers.getSigners();

  const registry = await (await ethers.getContractFactory("OrgRegistry")).deploy();
  await registry.waitForDeployment();
  const registryAddr = await registry.getAddress();

  const campaigns = await (await ethers.getContractFactory("CampaignRegistry"))
    .deploy(registryAddr);
  const evidence  = await (await ethers.getContractFactory("EvidenceAnchor"))
    .deploy(registryAddr);
  const attest    = await (await ethers.getContractFactory("Attestation"))
    .deploy(registryAddr);
  await Promise.all([campaigns.waitForDeployment(),
                     evidence.waitForDeployment(), attest.waitForDeployment()]);

  await (await registry.registerOrg(org1.address, "Bank One SOC")).wait();
  await (await registry.registerOrg(org2.address, "Bank Two SOC")).wait();

  const out = {
    chainId: 31337,
    OrgRegistry: registryAddr,
    CampaignRegistry: await campaigns.getAddress(),
    EvidenceAnchor:   await evidence.getAddress(),
    Attestation:      await attest.getAddress(),
    orgs: {
      org1: { address: org1.address, name: "Bank One SOC" },
      org2: { address: org2.address, name: "Bank Two SOC" },
    },
    deployedAt: new Date().toISOString(),
  };
  fs.mkdirSync("deployments", { recursive: true });
  fs.writeFileSync("deployments/localhost.json", JSON.stringify(out, null, 2));
  console.log(out);
}
main().catch((e) => { console.error(e); process.exit(1); });
```

**The API reads `deployments/localhost.json`.** Never hardcode addresses in Python.

---

## 7. Tests

```ts
// OrgRegistry.test.ts
"non-admin cannot register an org"           → reverts NotAdmin
"deactivated org loses write access"         → downstream calls revert NotOrg

// CampaignRegistry.test.ts
"unregistered address cannot publish"        → reverts NotOrg
"same campaignId cannot be published twice"  → reverts AlreadyPublished
"findByKit returns every campaign for a kit" → THE INHERITANCE TEST
"reporter cannot corroborate own campaign"   → reverts SelfCorroboration

// EvidenceAnchor.test.ts
"verify returns true for the anchored root"
"verify returns false for a tampered root"   → THE TAMPER TEST
"the same bundleId cannot be re-anchored"    → reverts AlreadyAnchored
```

**The last test in each of the bottom two files is a release gate.** They are the two demo beats.

---

## 8. Python wiring

```python
# services/api/ledger_service.py
import json
from web3 import Web3

DEPLOY = json.load(open("contracts/deployments/localhost.json"))
w3 = Web3(Web3.HTTPProvider(SETTINGS.chain_rpc))
```

**Use `web3.py`, not a Node subprocess.** ABIs come from `contracts/artifacts/contracts/*.sol/*.json` after compilation.

**Every write goes through the anchor queue.** Never call a contract synchronously inside a request handler. If the chain is down for the whole demo, detection, clustering and interdiction all continue and the UI shows the queue depth.

---

## 9. `Dockerfile`

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx hardhat compile
EXPOSE 8545
CMD ["npx", "hardhat", "node", "--hostname", "0.0.0.0"]
```

---

## 10. Failure protocol

| If | Then |
|---|---|
| Hardhat won't start | Contracts are still unit-testable offline. Anchoring queues and shows pending. Demo continues. |
| Deploy script fails | Check the node is up and accounts are funded. `npx hardhat node` gives 20 pre-funded accounts. |
| web3.py can't connect | Verify `CHAIN_RPC`. In Docker it is `http://hardhat:8545`, not `localhost`. |
| Gas errors | You are on a real network by mistake. Local Hardhat has no real gas cost. Check the RPC URL. |
