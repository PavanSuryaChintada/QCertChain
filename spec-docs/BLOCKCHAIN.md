# BLOCKCHAIN — ledger and cryptography

Read before writing anything in `contracts/` or `packages/evidence/`.

---

## 1. Why a ledger at all

A judge will ask, and "because blockchain" loses. The honest answer is four specific properties, and this problem needs all four:

**Cross-organisation sharing.** SBI gets hit by a kit on Monday. HDFC gets hit by the same kit on Wednesday and starts from zero. Neither will send the other its internal telemetry. A shared commitment layer gives the second organisation the campaign instantly.

**Chain of custody.** Evidence supports abuse reports and, eventually, police complaints. You must be able to prove an artifact existed at a given time and was never altered. A screenshot in a folder cannot do that.

**Non-repudiation.** Every claim is signed by its reporter. A competitor cannot anonymously poison the feed to get a rival's domain blocked — every claim has a permanent author.

**No central honeypot.** A single database holding every bank's threat telemetry is the highest-value target in the country. We store hashes only.

> **If you cannot map a piece of on-chain data to one of these four, it does not go on-chain.**

---

## 2. What goes on-chain — and what never does

| On-chain | Never on-chain |
|---|---|
| Merkle root of a campaign's IOC set | The IOC list itself |
| SHA-256 of an evidence bundle | Screenshots, DOM, page content |
| Kit fingerprint hash | Any customer or victim data |
| Reporter org address + signature | Internal telemetry, alert volumes |
| Timestamp | Anything personally identifying |
| Takedown plan hash | |

Chain storage is expensive and permanent. **Permanent is the point for hashes and a liability for anything else.**

---

## 3. Chain choice

**Hardhat local EVM node + Solidity 0.8.24.** Not Hyperledger Fabric.

Fabric is the "correct" enterprise answer and a two-day install with channels, MSPs, chaincode packaging and CA setup. That is the whole build window.

Hardhat gives you: a chain in one command, multiple funded accounts to represent different organisations, instant mining, and `ethers.js` from Python via a thin service or direct RPC. The multi-org story demos identically.

**Say this if asked:** *"Permissioned EVM for the prototype. Production would run Fabric or a consortium chain — the contract logic is unchanged."* That is true and it is a better answer than a half-installed Fabric.

Optional stretch: anchor the daily root to **Polygon Amoy testnet** for public verifiability. Non-blocking.

---

## 4. Contracts

### 4.1 `OrgRegistry.sol`

Permissioning. Only registered organisations may publish.

```solidity
struct Org { string name; bool active; uint256 registeredAt; }
mapping(address => Org) public orgs;

function registerOrg(address who, string calldata name) external onlyAdmin;
function deactivateOrg(address who) external onlyAdmin;
modifier onlyOrg() { require(orgs[msg.sender].active, "not a registered org"); _; }
```

### 4.2 `CampaignRegistry.sol`

The cross-org intelligence layer.

```solidity
struct Campaign {
    bytes32 iocRoot;        // Merkle root over the IOC set
    bytes32 kitHash;        // DOM-structure fingerprint
    uint16  domainCount;
    uint8   confidence;     // 0-100
    address reporter;
    uint256 timestamp;
}
mapping(bytes32 => Campaign) public campaigns;   // campaignId => Campaign

event CampaignPublished(bytes32 indexed campaignId, bytes32 indexed kitHash,
                        address indexed reporter, uint16 domainCount);

function publishCampaign(bytes32 campaignId, bytes32 iocRoot, bytes32 kitHash,
                         uint16 domainCount, uint8 confidence) external onlyOrg;

function corroborate(bytes32 campaignId) external onlyOrg;   // second org confirms
```

**`kitHash` is indexed on purpose.** A second organisation queries by kit hash and instantly finds every campaign anyone has seen using that kit. That is the inheritance mechanism, and it's the demo's payoff.

### 4.3 `EvidenceAnchor.sol`

```solidity
struct Anchor {
    bytes32 bundleRoot;     // Merkle root over the artifact set
    bytes32 campaignId;
    address collector;
    uint256 timestamp;
}
mapping(bytes32 => Anchor) public anchors;   // bundleId => Anchor

event EvidenceAnchored(bytes32 indexed bundleId, bytes32 indexed campaignId,
                       address indexed collector, bytes32 bundleRoot);

function anchor(bytes32 bundleId, bytes32 bundleRoot, bytes32 campaignId) external onlyOrg;
function verify(bytes32 bundleId, bytes32 claimedRoot) external view returns (bool);
```

### 4.4 `Attestation.sol`

```solidity
enum Verdict { Confirmed, Dismissed, Disputed }

event Attested(bytes32 indexed subjectHash, address indexed org,
               Verdict verdict, uint256 timestamp);

function attest(bytes32 subjectHash, Verdict v) external onlyOrg;
```

Lets a second organisation **dispute** a claim. That matters — a system that only accumulates accusations with no dissent mechanism is a censorship tool. Say this out loud if asked about false positives.

---

## 5. Evidence bundle — `packages/evidence/`

### Artifacts collected per target

| Artifact | Source |
|---|---|
| `screenshot.png` | Playwright full-page capture |
| `dom.html` | Rendered DOM after JS |
| `headers.json` | HTTP response headers, redirect chain |
| `cert.pem` | Full TLS chain as served |
| `whois.json` | Registrar, registrant, creation date |
| `dns.json` | A, AAAA, NS, MX, TXT |
| `asn.json` | ASN, netblock, country |
| `kit.json` | DOM-structure hash, favicon hash, JS bundle hashes |
| `meta.json` | Collector id, UTC timestamp, tool versions |

### Building the bundle

```python
def build_bundle(target, artifacts, signing_key) -> Bundle:
    """
    1. SHA-256 each artifact  -> leaf hashes
    2. Sort leaves by artifact name (DETERMINISTIC ORDER — critical)
    3. Build a Merkle tree    -> bundle_root
    4. Ed25519-sign bundle_root with the collector key
    5. Store artifacts on disk / object store; root + signature go on-chain
    """
```

**Sort the leaves.** If leaf order varies between runs, the same evidence produces different roots and verification fails for no reason. Sort by artifact name, always.

### Verifying

```python
def verify_bundle(bundle_dir, expected_root, signature, public_key) -> VerifyResult:
    """
    Recompute each artifact hash, rebuild the tree, compare to expected_root,
    check the Ed25519 signature. Return WHICH artifact failed, not just False.
    """
```

**Return the failing artifact.** "Verification failed" is useless. *"`dom.html` hash mismatch — expected a4f2…, got 91bc…"* is the demo moment.

### Generated abuse report

Registrar-ready markdown/JSON with the evidence summary and artifact hashes.

**Written to disk. Never sent.** `CLAUDE.md` §2.1. No SMTP, no abuse-form POST, no registrar API call anywhere in this repo.

---

## 6. Cryptography inventory

| Where | Primitive | Library |
|---|---|---|
| Evidence signing | Ed25519 | PyNaCl |
| Bundle integrity | SHA-256 Merkle | hand-rolled or `pymerkle` |
| IOC set commitment | SHA-256 Merkle root | same |
| On-chain identity | secp256k1 | ethers.js / eth-account |
| **Stretch:** cross-org IOC overlap | ECDH-based PSI | `cryptography` |
| **Stretch:** set membership proof | Merkle inclusion proof | same |

### PSI — stretch only, cut first

Two organisations want to know whether they have seen the same infrastructure **without either revealing its full IOC list**.

```
1. Both hash their IOCs to curve points
2. Each blinds with a private scalar and sends the blinded set
3. Each blinds the other's set with its own scalar
4. Double-blinded values match iff the underlying IOCs match
5. Each learns only the intersection
```

~150 lines with `cryptography`. **Cut this before anything in the core path.** The ledger alone tells the cross-org story adequately.

---

## 7. Service integration

```
services/api/ledger.py
├── publish_campaign(campaign)     -> tx hash
├── anchor_evidence(bundle)        -> tx hash
├── attest(subject_hash, verdict)  -> tx hash
├── find_by_kit_hash(kit_hash)     -> list[Campaign]     # the inheritance query
└── verify_anchor(bundle_id, root) -> bool
```

**Anchoring must be non-blocking.** Queue it, retry with backoff, surface the queue state in the UI. If the chain node is down, detection, clustering and interdiction all continue unaffected. Nothing in the critical path waits on a transaction.

---

## 8. Build order

1. `packages/evidence/` — Merkle + Ed25519 + verify. **No chain needed.** `test_evidence.py` green.
2. Hardhat project, `OrgRegistry.sol`, deploy script, two funded org accounts
3. `CampaignRegistry.sol` + publish/query, with the `kitHash` index working
4. `EvidenceAnchor.sol` + anchor/verify
5. `services/api/ledger.py` wiring, async queue
6. `Attestation.sol` + dispute flow
7. PSI — **stretch, cut first**

---

## 9. The demo beat

Second organisation's console, empty.

A campaign is published by org 1. Org 2's console **queries the chain by kit hash** and the campaign appears — 400 domains, with the reporter's identity and timestamp.

Then: **open an evidence bundle, change one byte of `dom.html`, re-verify.** Screen shows the specific artifact that failed and the root mismatch.

**That second beat is the one that proves the cryptography is real rather than decorative.**
