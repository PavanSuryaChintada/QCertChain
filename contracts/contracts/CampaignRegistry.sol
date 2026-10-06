// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IOrgRegistry { function isActive(address) external view returns (bool); }

/// Cross-organisation intelligence: campaign commitments, queryable by kit hash (BLOCKCHAIN.md §4.2).
/// Hashes and commitments only — the IOC list itself never goes on-chain, only its Merkle root.
contract CampaignRegistry {
    struct Campaign {
        bytes32 iocRoot;
        bytes32 kitHash;
        uint16  domainCount;
        uint8   confidence;      // 0-100
        address reporter;
        uint64  timestamp;       // uint64 packs with the address into one slot
    }

    IOrgRegistry public immutable orgRegistry;

    mapping(bytes32 => Campaign) public campaigns;          // campaignId => Campaign
    mapping(bytes32 => bytes32[]) private _byKit;           // kitHash  => campaignIds (unbounded: fine at demo scale)
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
        emit CampaignPublished(campaignId, kitHash, msg.sender, iocRoot, domainCount, confidence);
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
