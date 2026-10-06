import { ethers } from "hardhat";

// signer[0] = admin (not an org), signer[1] = Bank One SOC, signer[2] = Bank Two SOC, signer[3] = outsider
export async function deployAll() {
  const [admin, org1, org2, rando] = await ethers.getSigners();
  const reg = await (await ethers.getContractFactory("OrgRegistry")).deploy();
  const regAddr = await reg.getAddress();
  const cr = await (await ethers.getContractFactory("CampaignRegistry")).deploy(regAddr);
  const ea = await (await ethers.getContractFactory("EvidenceAnchor")).deploy(regAddr);
  const at = await (await ethers.getContractFactory("Attestation")).deploy(regAddr);
  await (await reg.registerOrg(org1.address, "Bank One SOC")).wait();
  await (await reg.registerOrg(org2.address, "Bank Two SOC")).wait();
  return { reg, cr, ea, at, admin, org1, org2, rando };
}

export const id = (s: string) => ethers.id(s);
