import { expect } from "chai";
import { deployAll, id } from "./fixture";

const bundle = id("bundle-1"), root = id("root"), camp = id("camp-1");

describe("EvidenceAnchor", () => {
  it("verify returns true for the anchored root", async () => {
    const { ea, org1 } = await deployAll();
    await (await ea.connect(org1).anchor(bundle, root, camp)).wait();
    expect(await ea.verify(bundle, root)).to.equal(true);
  });

  it("verify returns false for a tampered root — THE TAMPER TEST", async () => {
    const { ea, org1 } = await deployAll();
    await (await ea.connect(org1).anchor(bundle, root, camp)).wait();
    expect(await ea.verify(bundle, id("tampered"))).to.equal(false);
    expect(await ea.verify(id("never-anchored"), root)).to.equal(false);
  });

  it("the same bundleId cannot be re-anchored", async () => {
    const { ea, org1, org2 } = await deployAll();
    await (await ea.connect(org1).anchor(bundle, root, camp)).wait();
    await expect(ea.connect(org2).anchor(bundle, id("other"), camp)).to.be.revertedWithCustomError(ea, "AlreadyAnchored");
  });

  it("only orgs can anchor", async () => {
    const { ea, rando } = await deployAll();
    await expect(ea.connect(rando).anchor(bundle, root, camp)).to.be.revertedWithCustomError(ea, "NotOrg");
  });
});
