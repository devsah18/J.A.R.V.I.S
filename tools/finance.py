"""Finance and Cryptocurrency tool.

Provides real-time prices for cryptocurrencies (Bitcoin, Ethereum, Solana, etc.)
via CoinGecko and live currency exchange rates (USD, INR, EUR, GBP, etc.)
via Open Exchange Rate API without needing an API key.
"""

from __future__ import annotations

import logging
from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

# Common crypto aliases to CoinGecko IDs
_CRYPTO_ALIASES = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "xrp": "ripple",
    "ripple": "ripple",
    "ada": "cardano",
    "cardano": "cardano",
    "bnb": "binancecoin",
}

_COMMON_CURRENCIES = {
    "usd", "inr", "eur", "gbp", "jpy", "cad", "aud", "chf", "cny", "aed"
}


class FinanceTool(Tool):
    name = "finance"
    description = "Get real-time cryptocurrency prices (e.g. Bitcoin, Ethereum) and currency exchange rates (e.g. USD to INR, EUR to USD)."
    risk = Risk.LOW
    params = (
        ParamSpec("asset", "Cryptocurrency name/symbol (e.g. 'bitcoin', 'ETH') or currency pair (e.g. 'USD to INR', 'EUR')"),
        ParamSpec("vs_currency", "Comparison currency, defaults to 'USD' or 'INR'", required=False),
    )

    def run(self, asset: str = "", vs_currency: str = "usd", **kwargs) -> ToolResult:
        asset = (asset or "").strip().lower()
        if not asset:
            return ToolResult.failure("Please specify a crypto asset (e.g. 'bitcoin') or currency pair (e.g. 'USD to INR').")

        if requests is None:
            return ToolResult.failure("The requests library is required for finance queries.")

        vs_curr = (vs_currency or "usd").strip().lower()

        # Check if asset matches a cryptocurrency
        crypto_id = _CRYPTO_ALIASES.get(asset)
        if crypto_id:
            try:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd,inr,eur"
                resp = requests.get(url, timeout=6, headers={"User-Agent": "VARSHA/1.0"})
                data = resp.json()
                prices = data.get(crypto_id, {})
                usd_price = prices.get("usd")
                inr_price = prices.get("inr")

                if usd_price is not None:
                    name_cap = crypto_id.capitalize()
                    inr_str = f", or {inr_price:,.2f} INR" if inr_price else ""
                    msg = f"{name_cap} is currently trading at ${usd_price:,.2f} USD{inr_str}."
                    return ToolResult.success(msg, asset=crypto_id, usd=usd_price, inr=inr_price)
            except Exception as e:
                logger.warning("CoinGecko error: %s", e)

        # Check for currency conversion (e.g. "usd to inr", "eur to gbp", "inr")
        words = asset.replace("to", " ").replace("/", " ").split()
        base_curr = words[0].upper() if words else "USD"
        target_curr = words[1].upper() if len(words) > 1 else vs_curr.upper()

        if base_curr.lower() in _COMMON_CURRENCIES or target_curr.lower() in _COMMON_CURRENCIES:
            try:
                url = f"https://open.er-api.com/v6/latest/{base_curr}"
                resp = requests.get(url, timeout=6, headers={"User-Agent": "VARSHA/1.0"})
                data = resp.json()

                if data.get("result") == "success":
                    rates = data.get("rates", {})
                    rate = rates.get(target_curr)
                    if rate:
                        msg = f"1 {base_curr} is currently {rate:.2f} {target_curr}."
                        return ToolResult.success(msg, base=base_curr, target=target_curr, rate=rate)
            except Exception as e:
                logger.warning("Exchange rate error: %s", e)

        return ToolResult.failure(f"Could not find financial data for '{asset}'. You can ask for Bitcoin, Ethereum, or currency pairs like USD to INR.")

