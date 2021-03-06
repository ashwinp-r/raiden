from eth_utils import encode_hex
from eth_utils.currency import denoms

from raiden.tests.utils.genesis import GENESIS_STUB
from raiden.utils.keys import privatekey_to_address
from raiden.utils.signing import sha3

CLUSTER_NAME = b"raiden"
ETHER = denoms.ether  # pylint: disable=no-member


def generate_accounts(seeds):
    """Create private keys and addresses for all seeds.
    """
    return {
        seed: {
            "privatekey": encode_hex(sha3(seed)),
            "address": encode_hex(privatekey_to_address(sha3(seed))),
        }
        for seed in seeds
    }


def mk_genesis(accounts, initial_alloc=ETHER * 100000000):
    """
    Create a genesis-block dict with allocation for all `accounts`.

    :param accounts: list of account addresses (hex)
    :param initial_alloc: the amount to allocate for the `accounts`
    :return: genesis dict
    """
    genesis = GENESIS_STUB.copy()
    genesis["extraData"] = encode_hex(CLUSTER_NAME)
    genesis["alloc"].update({account: {"balance": str(initial_alloc)} for account in accounts})
    # add the one-privatekey account ("1" * 64) for convenience
    genesis["alloc"]["19e7e376e7c213b7e7e7e46cc70a5dd086daff2a"] = dict(balance=str(initial_alloc))
    return genesis
