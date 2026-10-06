import { expect } from "chai";
import { deployAll, id } from "./fixture";

const subject = id("subject");
const Confirmed = 0, Dismissed = 1, Disputed = 2;

describe("Attestation", () => {
  it("records every attesting org once — fixes BUILD_SPEC §5 first-org-only bug", async () => {
    const { at, org1, org2 } = await deployAll();
    await (await at.connect(org1).attest(subject, Confirmed)).wait();
    await (await at.connect(org2).attest(subject, Disputed)).wait();
    await (await at.connect(org1).attest(subject, Dismissed)).wait(); // changes verdict, not the attestor list
    expect(await at.attestorsOf(subject)).to.deep.equal([org1.address, org2.address]);
    expect(await at.attestations(subject, org1.address)).to.equal(Dismissed);
    expect(await at.attestations(subject, org2.address)).to.equal(Disputed);
  });

  it("a second org can dispute and the event says so", async () => {
    const { at, org2 } = await deployAll();
    await expect(at.connect(org2).attest(subject, Disputed)).to.emit(at, "Attested");
  });

  it("non-org cannot attest", async () => {
    const { at, rando } = await deployAll();
    await expect(at.connect(rando).attest(subject, Confirmed)).to.be.revertedWithCustomError(at, "NotOrg");
  });
});
