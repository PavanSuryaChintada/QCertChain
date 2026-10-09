"""Ledger: web3.py client for the permissioned EVM (contracts/BUILD_SPEC.md §8, BLOCKCHAIN.md §7).

Hashes and commitments only. Never called inside a request handler for writes: the anchor worker drains
anchor_queue. Addresses come from contracts/deployments/<net>.json, ABIs from contracts/abi/ — never hardcoded.
On-chain ids: bytes32 = keccak256(uuid string) for campaigns and bundles; kit hash / roots are the 32-byte
SHA-256 values themselves.
"""
from __future__ import annotations

import json
from pathlib import Path

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractCustomError, ContractLogicError

from services.config import ROOT

CONTRACTS = ("OrgRegistry", "CampaignRegistry", "EvidenceAnchor", "Attestation")
VERDICTS = ("confirmed", "dismissed", "disputed")  # Attestation.Verdict enum order


class LedgerError(Exception):
    pass


def b32_id(uuid_str: str) -> bytes:
    return Web3.keccak(text=str(uuid_str))


def b32_hex(h: str) -> bytes:
    h = h.removeprefix("0x")
    if len(h) != 64:
        raise ValueError(f"expected 32-byte hex, got {len(h) // 2} bytes")
    return bytes.fromhex(h)


class Ledger:
    def __init__(self, rpc: str, deploy_path: Path, abi_dir: Path, org_keys: dict[str, str], timeout_s: float = 5,
                 admin_key: str = "", key_loader=None):
        self.w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": timeout_s}))
        self.deploy = json.loads(Path(deploy_path).read_text(encoding="utf-8"))
        self.c = {}
        self._errors: dict[str, str] = {}
        for name in CONTRACTS:
            abi = json.loads((Path(abi_dir) / f"{name}.json").read_text(encoding="utf-8"))
            self.c[name] = self.w3.eth.contract(address=self.deploy[name], abi=abi)
            for e in abi:
                if e.get("type") == "error":
                    sig = f"{e['name']}({','.join(i['type'] for i in e['inputs'])})"
                    self._errors[Web3.keccak(text=sig)[:4].hex().removeprefix("0x")] = e["name"]
        self.accounts = {k: Account.from_key(v) for k, v in org_keys.items() if v}
        # organisations created by the super admin keep their (sealed) key in the database: loaded on first use
        self._key_loader = key_loader
        self.admin = Account.from_key(admin_key) if admin_key else None
        self._names: dict[str, str] = {}

    @classmethod
    def from_settings(cls, s, key_loader=None) -> "Ledger":
        return cls(s.chain_rpc, ROOT / "contracts/deployments/localhost.json", ROOT / "contracts/abi",
                   {"org1": s.org_private_key, "org2": s.org2_private_key},
                   admin_key=getattr(s, "chain_admin_private_key", ""), key_loader=key_loader or _database_key)

    def account(self, org: str):
        """The signing account of an organisation: org1/org2 from settings, any other from its sealed key."""
        acct = self.accounts.get(org)
        if acct is None and self._key_loader is not None:
            try:
                key = self._key_loader(org)
            except Exception:  # noqa: BLE001 - a database blip: report "no key", the queue retries
                key = None
            if key:
                acct = self.accounts[org] = Account.from_key(key)
        return acct

    # ---- plumbing --------------------------------------------------------------------------------
    def available(self) -> bool:
        try:
            return self.w3.is_connected() and self.w3.eth.chain_id == self.deploy["chainId"]
        except Exception:
            return False

    def _decode(self, exc: Exception) -> str:
        text = str(exc)
        for sel, name in self._errors.items():
            if sel in text:
                return name
        return text

    def _send(self, fn, as_org: str) -> str:
        acct = self.account(as_org)
        if acct is None:
            raise LedgerError(f"no private key configured for {as_org}")
        return self._send_from(acct, fn)

    def _send_from(self, acct, fn=None, value_to: str | None = None, value_wei: int = 0) -> str:
        base = {"from": acct.address, "chainId": self.deploy["chainId"],
                "nonce": self.w3.eth.get_transaction_count(acct.address, "pending")}
        if fn is None:  # a plain transfer (funding a new organisation's account)
            tx = {**base, "to": value_to, "value": value_wei, "gas": 21000, "gasPrice": self.w3.eth.gas_price}
        else:
            try:
                tx = fn.build_transaction(base)
            except (ContractCustomError, ContractLogicError) as e:
                raise LedgerError(f"reverted: {self._decode(e)}") from e
        signed = acct.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        rcpt = self.w3.eth.wait_for_transaction_receipt(h, timeout=30)
        if rcpt.status != 1:
            raise LedgerError(f"transaction {h.hex()} reverted")
        return "0x" + h.hex().removeprefix("0x")

    def org_name(self, address: str) -> str:
        if address not in self._names:
            self._names[address] = self.c["OrgRegistry"].functions.orgs(address).call()[0] or address
        return self._names[address]

    def _ts(self, block_number: int) -> int:
        return self.w3.eth.get_block(block_number).timestamp

    # ---- organisations (the chain admin; spec 2026-10-09 §7) ---------------------------------------
    def is_registered(self, address: str) -> bool:
        return bool(self.c["OrgRegistry"].functions.isActive(Web3.to_checksum_address(address)).call())

    def register_org(self, address: str, name: str, fund_wei: int = 10**18) -> None:
        """Fund a new organisation's account for gas and register it. Idempotent: an active account is left alone."""
        if self.admin is None:
            raise LedgerError("no chain admin key (CHAIN_ADMIN_PRIVATE_KEY)")
        address = Web3.to_checksum_address(address)
        if self.w3.eth.get_balance(address) < fund_wei // 2:
            self._send_from(self.admin, value_to=address, value_wei=fund_wei)
        if not self.is_registered(address):
            self._send_from(self.admin, self.c["OrgRegistry"].functions.registerOrg(address, name))
        self._names.pop(address, None)

    # ---- writes (called by the anchor worker only) -----------------------------------------------
    def publish_campaign(self, campaign_id: str, ioc_root_hex: str, kit_hash_hex: str, domain_count: int,
                         confidence: int, as_org: str = "org1") -> str:
        fn = self.c["CampaignRegistry"].functions.publishCampaign(
            b32_id(campaign_id), b32_hex(ioc_root_hex), b32_hex(kit_hash_hex),
            min(int(domain_count), 65535), max(0, min(int(confidence), 100)))
        return self._send(fn, as_org)

    def corroborate(self, chain_campaign_id_hex: str, as_org: str) -> str:
        """By CHAIN id (from find_by_kit): the corroborating org never holds the reporter's local campaign id."""
        return self._send(self.c["CampaignRegistry"].functions.corroborate(b32_hex(chain_campaign_id_hex)), as_org)

    def anchor_evidence(self, bundle_id: str, root_hex: str, campaign_id: str | None, as_org: str = "org1") -> str:
        fn = self.c["EvidenceAnchor"].functions.anchor(
            b32_id(bundle_id), b32_hex(root_hex), b32_id(campaign_id) if campaign_id else b"\x00" * 32)
        return self._send(fn, as_org)

    def attest(self, subject_hash_hex: str, verdict: str, as_org: str) -> str:
        return self._send(self.c["Attestation"].functions.attest(b32_hex(subject_hash_hex), VERDICTS.index(verdict)),
                          as_org)

    # ---- reads -----------------------------------------------------------------------------------
    def verify_anchor(self, bundle_id: str, root_hex: str) -> bool:
        return bool(self.c["EvidenceAnchor"].functions.verify(b32_id(bundle_id), b32_hex(root_hex)).call())

    def find_by_kit(self, kit_hash_hex: str) -> list[dict]:
        """THE INHERITANCE QUERY: every campaign any org published for this kit, with provenance."""
        cr = self.c["CampaignRegistry"]
        out = []
        for cid in cr.functions.findByKit(b32_hex(kit_hash_hex)).call():
            ioc_root, kit, count, conf, reporter, ts = cr.functions.campaigns(cid).call()
            pub = cr.events.CampaignPublished().get_logs(from_block=0, argument_filters={"campaignId": cid})
            cor = cr.events.Corroborated().get_logs(from_block=0, argument_filters={"campaignId": cid})
            out.append({
                "chain_campaign_id": "0x" + cid.hex(), "ioc_root": ioc_root.hex(), "kit_hash": kit.hex(),
                "domain_count": count, "confidence": conf,
                "reporter": {"address": reporter, "name": self.org_name(reporter)},
                "published_at": ts, "tx_hash": "0x" + pub[0].transactionHash.hex().removeprefix("0x") if pub else None,
                "corroborations": [{"address": ev.args.org, "name": self.org_name(ev.args.org),
                                    "at": self._ts(ev.blockNumber)} for ev in cor],
            })
        return out

    def attestations(self, subject_hash_hex: str) -> dict[str, str]:
        at = self.c["Attestation"]
        s = b32_hex(subject_hash_hex)
        return {self.org_name(a): VERDICTS[at.functions.attestations(s, a).call()]
                for a in at.functions.attestorsOf(s).call()}


def _database_key(slug: str) -> str | None:
    """An organisation's chain key from the database (sealed). Its own short connection: the ledger is shared."""
    from services.api import platform
    from services.api.db import engine
    with engine().connect() as c:
        return platform.chain_key(c, slug)
