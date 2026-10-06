import { expect } from "chai";
import { deployAll, id } from "./fixture";

describe("OrgRegistry", () => {
  it("non-admin cannot register an org", async () => {
    const { reg, org1, rando } = await deployAll();
    await expect(reg.connect(org1).registerOrg(rando.address, "X")).to.be.revertedWithCustomError(reg, "NotAdmin");
  });

  it("an address cannot be registered twice", async () => {
    const { reg, org1 } = await deployAll();
    await expect(reg.registerOrg(org1.address, "again")).to.be.revertedWithCustomError(reg, "AlreadyRegistered");
  });

  it("admin is not an org", async () => {
    const { reg, admin } = await deployAll();
    expect(await reg.isActive(admin.address)).to.equal(false);
  });

  it("deactivated org loses write access", async () => {
    const { reg, cr, org1 } = await deployAll();
    await (await reg.deactivateOrg(org1.address)).wait();
    await expect(cr.connect(org1).publishCampaign(id("c"), id("root"), id("kit"), 1, 1))
      .to.be.revertedWithCustomError(cr, "NotOrg");
  });

  it("lists registered orgs", async () => {
    const { reg, org1, org2 } = await deployAll();
    expect(await reg.listOrgs()).to.deep.equal([org1.address, org2.address]);
  });
});
