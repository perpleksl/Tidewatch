"""Which chains Tidewatch covers, and how other providers name them (PRD 3.2 universe).

Tidewatch's chain names follow Birdeye's API chain parameters (docs.birdeye.so "Data
coverage", checked 19 Oct 2026), except `avalanche`, which Birdeye's docs spell `avalance`;
the Birdeye adapter maps it when it is built.

The covered universe is: the EVM chains Birdeye supports, Solana, and PoW coins listed on
SafeTrade (native coins, checked per coin). Sui is on Birdeye but isn't EVM or Solana, so it
is outside the universe.
"""

#: CoinGecko asset-platform ID -> Tidewatch chain name, for every chain in the universe.
COINGECKO_PLATFORMS: dict[str, str] = {
    "ethereum": "ethereum",
    "binance-smart-chain": "bsc",
    "arbitrum-one": "arbitrum",
    "optimistic-ethereum": "optimism",
    "polygon-pos": "polygon",
    "avalanche": "avalanche",
    "base": "base",
    "zksync": "zksync",
    "solana": "solana",
}

#: Native coins whose chain already has a Tidewatch name (CoinGecko coin ID -> chain name).
#: Any other native coin uses its CoinGecko ID as the chain name.
KNOWN_NATIVE_CHAINS: dict[str, str] = {
    "pearl-2": "pearl",
}


def native_chain_name(coingecko_id: str) -> str:
    return KNOWN_NATIVE_CHAINS.get(coingecko_id, coingecko_id)


#: Tidewatch chain name -> GoPlus chain ID for its EVM token-security endpoint (PER-23).
#: Solana uses GoPlus's separate Solana endpoint.
GOPLUS_EVM_CHAIN_IDS: dict[str, str] = {
    "ethereum": "1",
    "bsc": "56",
    "arbitrum": "42161",
    "optimism": "10",
    "polygon": "137",
    "avalanche": "43114",
    "base": "8453",
    "zksync": "324",
}

#: DefiLlama chain prefix (in a protocol's "chain:address") -> Tidewatch chain name (PER-21).
#: A bare "0x…" address with no prefix is on Ethereum.
DEFILLAMA_CHAINS: dict[str, str] = {
    "ethereum": "ethereum",
    "bsc": "bsc",
    "binance": "bsc",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon",
    "avax": "avalanche",
    "avalanche": "avalanche",
    "base": "base",
    "era": "zksync",
    "zksync": "zksync",
    "solana": "solana",
}
