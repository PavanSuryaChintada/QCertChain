import { ethers } from "hardhat";
import fs from "fs";

// contracts/BUILD_SPEC.md §6. Writes deployments/localhost.json — the ONLY place addresses live; the API reads it.
// signer[0] = admin (deploys, registers orgs; NOT an org). signer[1] = org1, signer[2] = org2.
// .env: ORG_PRIVATE_KEY = Hardhat account #1, ORG2_PRIVATE_KEY = account #2 (account #0 would revert NotOrg).
async function main() {
  const [admin, org1, org2] = await ethers.getSigners();

  const registry = await (await ethers.getContractFactory("OrgRegistry")).deploy();
  await registry.waitForDeployment();
  const registryAddr = await registry.getAddress();

  const campaigns = await (await ethers.getContractFactory("CampaignRegistry")).deploy(registryAddr);
  const evidence = await (await ethers.getContractFactory("EvidenceAnchor")).deploy(registryAddr);
  const attest = await (await ethers.getContractFactory("Attestation")).deploy(registryAddr);
  await Promise.all([campaigns.waitForDeployment(), evidence.waitForDeployment(), attest.waitForDeployment()]);

  await (await registry.registerOrg(org1.address, "Bank One SOC")).wait();
  await (await registry.registerOrg(org2.address, "Bank Two SOC")).wait();

  const net = await ethers.provider.getNetwork();
  const out = {
    chainId: Number(net.chainId),
    admin: admin.address,
    OrgRegistry: registryAddr,
    CampaignRegistry: await campaigns.getAddress(),
    EvidenceAnchor: await evidence.getAddress(),
    Attestation: await attest.getAddress(),
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

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
