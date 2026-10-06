// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Permissioning: only registered, active organisations may publish (BLOCKCHAIN.md §4.1).
contract OrgRegistry {
    struct Org { string name; bool active; uint256 registeredAt; }

    address public admin;
    mapping(address => Org) public orgs;
    address[] private _orgList;

    event OrgRegistered(address indexed who, string name);
    event OrgDeactivated(address indexed who);

    error NotAdmin();
    error NotRegisteredOrg();
    error AlreadyRegistered();

    constructor() { admin = msg.sender; }

    modifier onlyAdmin() { if (msg.sender != admin) revert NotAdmin(); _; }

    function registerOrg(address who, string calldata name) external onlyAdmin {
        if (orgs[who].registeredAt != 0) revert AlreadyRegistered();
        orgs[who] = Org(name, true, block.timestamp);
        _orgList.push(who);
        emit OrgRegistered(who, name);
    }

    function deactivateOrg(address who) external onlyAdmin {
        if (orgs[who].registeredAt == 0) revert NotRegisteredOrg();
        orgs[who].active = false;
        emit OrgDeactivated(who);
    }

    function isActive(address who) external view returns (bool) {
        return orgs[who].active;
    }

    function listOrgs() external view returns (address[] memory) { return _orgList; }
}
