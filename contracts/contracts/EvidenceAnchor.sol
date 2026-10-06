// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IOrgRegistry2 { function isActive(address) external view returns (bool); }

/// Chain of custody: an evidence bundle's Merkle root, anchored once, immutable (BLOCKCHAIN.md §4.3).
contract EvidenceAnchor {
    struct Anchor {
        bytes32 bundleRoot;
        bytes32 campaignId;
        address collector;
        uint64  timestamp;
    }

    IOrgRegistry2 public immutable orgRegistry;
    mapping(bytes32 => Anchor) public anchors;   // bundleId => Anchor

    event EvidenceAnchored(
        bytes32 indexed bundleId, bytes32 indexed campaignId,
        address indexed collector, bytes32 bundleRoot
    );

    error NotOrg();
    error AlreadyAnchored();

    constructor(address registry) { orgRegistry = IOrgRegistry2(registry); }

    modifier onlyOrg() { if (!orgRegistry.isActive(msg.sender)) revert NotOrg(); _; }

    /// AlreadyAnchored is the whole point: an anchor is immutable once written, which is what makes
    /// its timestamp mean something in an inquiry.
    function anchor(bytes32 bundleId, bytes32 bundleRoot, bytes32 campaignId) external onlyOrg {
        if (anchors[bundleId].timestamp != 0) revert AlreadyAnchored();
        anchors[bundleId] = Anchor(bundleRoot, campaignId, msg.sender, uint64(block.timestamp));
        emit EvidenceAnchored(bundleId, campaignId, msg.sender, bundleRoot);
    }

    function verify(bytes32 bundleId, bytes32 claimedRoot) external view returns (bool) {
        return anchors[bundleId].bundleRoot == claimedRoot
            && anchors[bundleId].timestamp != 0;
    }
}
