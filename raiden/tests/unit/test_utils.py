import gevent
import pytest
import requests
import responses
from eth_keys.exceptions import BadSignature, ValidationError
from eth_utils import decode_hex, to_canonical_address

from raiden.exceptions import InvalidSignature
from raiden.network.utils import get_http_rtt
from raiden.utils.keys import privatekey_to_publickey
from raiden.utils.signer import LocalSigner, Signer, recover
from raiden.utils.signing import pack_data, sha3


def test_privatekey_to_publickey():
    privkey = sha3(b"secret")
    pubkey = (
        "c283b0507c4ec6903a49fac84a5aead951f3c38b2c72b69da8a70a5bac91e9c"
        "705f70c7554b26e82b90d2d1bbbaf711b10c6c8b807077f4070200a8fb4c6b771"
    )

    assert pubkey == privatekey_to_publickey(privkey).hex()


def test_signer_sign():
    privkey = sha3(b"secret")  # 0x38e959391dD8598aE80d5d6D114a7822A09d313A
    message = b"message"
    # generated with Metamask's web3.personal.sign
    signature = decode_hex(
        "0x1eff8317c59ab169037f5063a5129bb1bab0299fef0b5621d866b07be59e2c0a"
        "6a404e88d3360fb58bd13daf577807c2cf9b6b26d80fc929c52e952769a460981c"
    )

    signer: Signer = LocalSigner(privkey)

    assert signer.sign(message) == signature


def test_recover():
    account = to_canonical_address("0x38e959391dD8598aE80d5d6D114a7822A09d313A")
    message = b"message"
    # generated with Metamask's web3.personal.sign
    signature = decode_hex(
        "0x1eff8317c59ab169037f5063a5129bb1bab0299fef0b5621d866b07be59e2c0a"
        "6a404e88d3360fb58bd13daf577807c2cf9b6b26d80fc929c52e952769a460981c"
    )

    assert recover(data=message, signature=signature) == account


@pytest.mark.parametrize(
    ("signature", "nested_exception"),
    [
        pytest.param(b"\x00" * 65, BadSignature, id="BadSignature"),
        pytest.param(b"bla", ValidationError, id="ValidationError"),
    ],
)
def test_recover_exception(signature, nested_exception):
    with pytest.raises(InvalidSignature) as exc_info:
        recover(b"bla", signature)
    assert isinstance(exc_info.value.__context__, nested_exception)


def test_get_http_rtt_happy(requests_responses):
    """ Ensure get_http_rtt returns the average RTT over the number of samples. """
    delay = iter([0.05, 0.05, 0.1])

    def response(_):
        gevent.sleep(next(delay))
        return 200, {}, ""

    requests_responses.add_callback(responses.GET, "http://url", callback=response)
    requests_responses.add_callback(responses.GET, "http://url", callback=response)
    requests_responses.add_callback(responses.GET, "http://url", callback=response)
    assert round(get_http_rtt(url="http://url", method="get", samples=3), 1) == 0.1


def test_get_http_rtt_ignore_failing(requests_responses):
    """ Ensure get_http_rtt ignores failing servers. """

    # RequestException (e.g. DNS not resolvable, server not reachable)
    requests_responses.add(responses.GET, "http://url1", body=requests.RequestException())
    assert get_http_rtt(url="http://url1", method="get") is None

    # Server misconfigured
    requests_responses.add(responses.GET, "http://url2", status=404)
    assert get_http_rtt(url="http://url2", method="get") is None

    # Internal server error
    requests_responses.add(responses.GET, "http://url3", status=500)
    assert get_http_rtt(url="http://url3", method="get") is None


def test_pack_data():
    assert pack_data(("Test", "string"), (49, "uint32")) == b"Test\x00\x00\x001"

    with pytest.raises(ValueError):
        pack_data((13, "uint256"), ("address"))

    with pytest.raises(TypeError):
        pack_data((256, "uint256"), ("This is not a uint256", "uint256"))
