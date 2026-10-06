// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IOrgRegistry3 { function isActive(address) external view returns (bool); }

/// Org verdicts on a subject (campaign / domain hash), including DISPUTED (BLOCKCHAIN.md §4.4).
/// A system that only accumulates accusations with no dissent mechanism is a censorship tool.
contract Attestation {
    enum Verdict { Confirmed, Dismissed, Disputed }

    IOrgRegistry3 public immutable orgRegistry;
    mapping(bytes32 => mapping(address => Verdict)) public attestations;
    mapping(bytes32 => address[]) private _attestors;
    // FIX vs contracts/BUILD_SPEC.md §5 (accepted by the owner 2026-10-06): the spec pushed an attestor only
    // when `attestations[s][sender] == Confirmed && _attestors[s].length == 0`. Confirmed is the enum's zero
    // value, so that recorded only the very first caller and never anyone after. Track first attestation
    // per org explicitly instead.
    mapping(bytes32 => mapping(address => bool)) private _hasAttested;

    event Attested(bytes32 indexed subjectHash, address indexed org, Verdict verdict, uint64 timestamp);

    error NotOrg();

    constructor(address registry) { orgRegistry = IOrgRegistry3(registry); }

    modifier onlyOrg() { if (!orgRegistry.isActive(msg.sender)) revert NotOrg(); _; }

    function attest(bytes32 subjectHash, Verdict v) external onlyOrg {
        if (!_hasAttested[subjectHash][msg.sender]) {
            _hasAttested[subjectHash][msg.sender] = true;
            _attestors[subjectHash].push(msg.sender);
        }
        attestations[subjectHash][msg.sender] = v;
        emit Attested(subjectHash, msg.sender, v, uint64(block.timestamp));
    }

    function attestorsOf(bytes32 subjectHash) external view returns (address[] memory) {
        return _attestors[subjectHash];
    }
}
