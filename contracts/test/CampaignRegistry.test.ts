import { expect } from "chai";
import { deployAll, id } from "./fixture";

const camp = id("camp-1"), kit = id("kit-a"), root = id("ioc-root");

describe("CampaignRegistry", () => {
  it("unregistered address cannot publish", async () => {
    const { cr, rando } = await deployAll();
    await expect(cr.connect(rando).publishCampaign(camp, root, kit, 1, 1)).to.be.revertedWithCustomError(cr, "NotOrg");
  });

  it("same campaignId cannot be published twice", async () => {
    const { cr, org1, org2 } = await deployAll();
    await (await cr.connect(org1).publishCampaign(camp, root, kit, 400, 94)).wait();
    await expect(cr.connect(org2).publishCampaign(camp, root, kit, 1, 1)).to.be.revertedWithCustomError(cr, "AlreadyPublished");
  });

  it("findByKit returns every campaign for a kit — THE INHERITANCE TEST", async () => {
    const { cr, org1, org2 } = await deployAll();
    await (await cr.connect(org1).publishCampaign(camp, root, kit, 400, 94)).wait();
    await (await cr.connect(org2).publishCampaign(id("camp-2"), root, kit, 12, 70)).wait();
    await (await cr.connect(org2).publishCampaign(id("camp-3"), root, id("other-kit"), 3, 50)).wait();
    expect(await cr.findByKit(kit)).to.deep.equal([camp, id("camp-2")]);
    const c = await cr.campaigns(camp);
    expect(c.reporter).to.equal(org1.address);
    expect(c.domainCount).to.equal(400n);
  });

  it("publish emits the indexed event", async () => {
    const { cr, org1 } = await deployAll();
    await expect(cr.connect(org1).publishCampaign(camp, root, kit, 400, 94))
      .to.emit(cr, "CampaignPublished").withArgs(camp, kit, org1.address, root, 400, 94);
  });

  it("reporter cannot corroborate own campaign", async () => {
    const { cr, org1 } = await deployAll();
    await (await cr.connect(org1).publishCampaign(camp, root, kit, 1, 1)).wait();
    await expect(cr.connect(org1).corroborate(camp)).to.be.revertedWithCustomError(cr, "SelfCorroboration");
  });

  it("second org corroborates; unknown campaign rejected", async () => {
    const { cr, org1, org2 } = await deployAll();
    await (await cr.connect(org1).publishCampaign(camp, root, kit, 1, 1)).wait();
    await (await cr.connect(org2).corroborate(camp)).wait();
    expect(await cr.corroborationsOf(camp)).to.deep.equal([org2.address]);
    await expect(cr.connect(org2).corroborate(id("nope"))).to.be.revertedWithCustomError(cr, "UnknownCampaign");
  });
});
