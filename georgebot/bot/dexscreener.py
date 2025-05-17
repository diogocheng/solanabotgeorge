import requests
import time
import json
from config import DEXSCREENER_API_URL, THRESHOLDS
import logging
import re

logger = logging.getLogger(__name__)

class DexScreenerAPI:
    def __init__(self):
        self.api_url = DEXSCREENER_API_URL
        self.thresholds = THRESHOLDS
        self.cache = {}
        self.cache_time = 0
        self.cache_duration = 300  # 5 minutes cache
        # Track successful response formats
        self.last_successful_endpoint = None

    def get_solana_tokens(self):
        """
        Fetch Solana tokens from DexScreener API
        """
        # Check if cache is valid
        if time.time() - self.cache_time < self.cache_duration and self.cache:
            return self.cache

        try:
            # Try the last successful endpoint first if we have one
            endpoints = []
            if self.last_successful_endpoint:
                endpoints.append(self.last_successful_endpoint)
            
            # Add other potential endpoints
            endpoints.extend([
                f"{self.api_url}/search/trending?chain=solana",
                f"{self.api_url}/tokens/solana",
                f"{self.api_url}/search?q=solana",
                # Try alternative URL structures
                "https://api.dexscreener.com/latest/dex/search/trending?chain=solana",
                "https://api.dexscreener.io/latest/dex/tokens/solana",  # Alternative domain
                "https://api.dexscreener.com/latest/dex/tokens/solana",
                # Try v2 endpoints if they exist
                "https://api.dexscreener.com/v2/dex/tokens/solana",
                "https://api.dexscreener.com/v2/dex/search/trending?chain=solana"
            ])
            
            # Remove duplicates
            endpoints = list(dict.fromkeys(endpoints))
            
            for endpoint in endpoints:
                try:
                    logger.info(f"Trying DexScreener endpoint: {endpoint}")
                    response = requests.get(endpoint, timeout=15)  # Increased timeout
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Handle different API response formats
                        if "pairs" in data and isinstance(data["pairs"], list):
                            logger.info(f"Got {len(data['pairs'])} tokens from endpoint {endpoint}")
                            self.cache = data
                            self.cache_time = time.time()
                            self.last_successful_endpoint = endpoint  # Remember successful endpoint
                            return self.cache
                            
                        # New API format might use different structure
                        elif isinstance(data, list) and len(data) > 0:
                            logger.info(f"Got {len(data)} tokens from endpoint {endpoint} (list format)")
                            self.cache = {"pairs": data}  # Adapt to our expected format
                            self.cache_time = time.time()
                            self.last_successful_endpoint = endpoint  # Remember successful endpoint
                            return self.cache
                            
                        # Another potential format
                        elif "data" in data and isinstance(data["data"], list):
                            logger.info(f"Got {len(data['data'])} tokens from endpoint {endpoint} (data format)")
                            self.cache = {"pairs": data["data"]}  # Adapt to our expected format
                            self.cache_time = time.time()
                            self.last_successful_endpoint = endpoint  # Remember successful endpoint
                            return self.cache
                        else:
                            logger.warning(f"Unexpected response format from {endpoint}: {str(data)[:200]}")
                except Exception as e:
                    logger.warning(f"Error with endpoint {endpoint}: {e}")
                    continue
            
            logger.error(f"All attempts to fetch Solana tokens failed")
            return {"pairs": []}  # Return empty pairs list as fallback
                
        except Exception as e:
            logger.error(f"Exception when fetching tokens: {e}")
            return {"pairs": []}

    def _safe_float_conversion(self, value, default=0.0):
        """Safely convert a value to float, handling various formats"""
        if value is None:
            return default
            
        if isinstance(value, (int, float)):
            return float(value)
            
        if isinstance(value, str):
            # Remove any non-numeric characters except decimal point and minus sign
            value = value.replace("%", "").strip()
            try:
                return float(value)
            except ValueError:
                # Try to extract just the numeric part if conversion fails
                match = re.search(r'-?\d+\.?\d*', value)
                if match:
                    try:
                        return float(match.group(0))
                    except ValueError:
                        return default
        return default

    def _extract_token_data(self, pair):
        """Extract token data from a pair object with better error handling"""
        token_data = {
            "name": "Unknown",
            "symbol": "Unknown",
            "address": "",
            "market_cap": 0,
            "volume_24h": 0,
            "price_change": 0,
            "liquidity": 0,
            "buy_sell_ratio": 1.0,
            "url": "",
            "price_usd": 0
        }
        
        try:
            # Extract base token info - handle different formats
            base_token = pair.get("baseToken", {})
            if not base_token or not isinstance(base_token, dict):
                # Try alternative structures
                if "tokens" in pair and isinstance(pair["tokens"], dict) and "base" in pair["tokens"]:
                    base_token = pair["tokens"]["base"]
                elif "base" in pair:
                    base_token = pair["base"]
            
            # Extract token identifiers
            token_data["name"] = base_token.get("name", "Unknown")
            token_data["symbol"] = base_token.get("symbol", "Unknown")
            token_data["address"] = base_token.get("address", "")
            
            # If no address found, check for other fields
            if not token_data["address"] and "id" in base_token:
                token_data["address"] = base_token["id"]
                
            # If still no address, try to get from pair
            if not token_data["address"]:
                if "baseTokenAddress" in pair:
                    token_data["address"] = pair["baseTokenAddress"]
                elif "pairAddress" in pair:
                    token_data["address"] = pair["pairAddress"]  # Not ideal but better than nothing
            
            # Skip if we couldn't get a valid address
            if not token_data["address"] or len(token_data["address"]) < 10:
                return None
            
            # Get URL
            token_data["url"] = pair.get("url", f"https://dexscreener.com/solana/{token_data['address']}")
            
            # Get market cap - try different fields
            market_cap = self._safe_float_conversion(pair.get("fdv", 0))
            if market_cap == 0:
                market_cap = self._safe_float_conversion(pair.get("marketCap", 0))
                if market_cap == 0 and "market" in pair:
                    market_cap = self._safe_float_conversion(pair["market"].get("cap", 0))
            
            # If still no market cap, try to derive it
            if market_cap == 0:
                # Try to calculate from supply and price
                supply = self._safe_float_conversion(pair.get("supply", 0))
                price_usd = self._safe_float_conversion(pair.get("priceUsd", 0))
                if supply > 0 and price_usd > 0:
                    market_cap = supply * price_usd
                    
                # If still zero, estimate from liquidity
                if market_cap == 0 and "liquidity" in pair:
                    liquidity_usd = 0
                    if isinstance(pair.get("liquidity"), dict):
                        liquidity_usd = self._safe_float_conversion(pair["liquidity"].get("usd", 0))
                    else:
                        liquidity_usd = self._safe_float_conversion(pair["liquidity"])
                    
                    if liquidity_usd > 0:
                        # Rough estimate: Liquidity typically represents ~20% of market cap
                        market_cap = liquidity_usd * 5
            
            token_data["market_cap"] = market_cap
            
            # Get 24h volume
            volume_24h = 0
            if "volume" in pair:
                volume_obj = pair.get("volume", {})
                if isinstance(volume_obj, dict) and "h24" in volume_obj:
                    volume_24h = self._safe_float_conversion(volume_obj.get("h24", 0))
                else:
                    volume_24h = self._safe_float_conversion(volume_obj)
            token_data["volume_24h"] = volume_24h
            
            # Get price change
            price_change = 0
            if "priceChange" in pair:
                price_change_obj = pair.get("priceChange", {})
                if isinstance(price_change_obj, dict) and "h24" in price_change_obj:
                    price_change = self._safe_float_conversion(price_change_obj.get("h24", "0"))
                else:
                    price_change = self._safe_float_conversion(price_change_obj)
            token_data["price_change"] = price_change
            
            # Get liquidity
            liquidity = 0
            if "liquidity" in pair:
                liquidity_obj = pair.get("liquidity", {})
                if isinstance(liquidity_obj, dict) and "usd" in liquidity_obj:
                    liquidity = self._safe_float_conversion(liquidity_obj.get("usd", 0))
                else:
                    liquidity = self._safe_float_conversion(liquidity_obj)
            token_data["liquidity"] = liquidity
            
            # Get buy/sell ratio
            buys = 0
            sells = 0
            if "txns" in pair:
                txns = pair.get("txns", {})
                if isinstance(txns, dict) and "h24" in txns:
                    txns_h24 = txns.get("h24", {})
                    buys = int(self._safe_float_conversion(txns_h24.get("buys", 0)))
                    sells = int(self._safe_float_conversion(txns_h24.get("sells", 0)))
                    
                    # Calculate ratio (avoid division by zero)
                    if sells > 0:
                        token_data["buy_sell_ratio"] = buys / sells
                    elif buys > 0:
                        token_data["buy_sell_ratio"] = float('inf')  # Infinite ratio (all buys)
                    else:
                        token_data["buy_sell_ratio"] = 1.0  # Default when no transactions
            
            # Get price USD
            token_data["price_usd"] = self._safe_float_conversion(pair.get("priceUsd", 0))
            
            return token_data
            
        except Exception as e:
            logger.error(f"Error extracting token data: {str(e)}")
            return None

    def apply_filters(self, tokens_data):
        """
        Apply filters to token data based on thresholds
        """
        if not tokens_data or "pairs" not in tokens_data or not isinstance(tokens_data["pairs"], list):
            logger.warning("No valid pairs data to filter")
            return []

        filtered_tokens = []
        for pair in tokens_data.get("pairs", []):
            try:
                # Use helper method to extract token data
                token_info = self._extract_token_data(pair)
                
                # Skip invalid tokens
                if token_info is None:
                    continue
                
                # Debug log for potential matches
                if token_info["market_cap"] > 0 or token_info["volume_24h"] > 0 or token_info["price_change"] > 0:
                    logger.info(f"Potential token: {token_info['symbol']} - MC: ${token_info['market_cap']:,.2f}, "
                               f"Vol: ${token_info['volume_24h']:,.2f}, Change: {token_info['price_change']}%, "
                               f"Liq: ${token_info['liquidity']:,.2f}, B/S: {token_info['buy_sell_ratio']:.2f}")
                
                # Apply thresholds
                if (token_info["market_cap"] >= self.thresholds["min_market_cap"] and
                    token_info["volume_24h"] >= self.thresholds["min_volume"] and
                    token_info["price_change"] >= self.thresholds["min_price_change"] and
                    token_info["liquidity"] >= self.thresholds["min_liquidity"] and
                    token_info["buy_sell_ratio"] >= self.thresholds["min_buy_sell_ratio"]):
                    
                    logger.info(f"Found matching token: {token_info['symbol']} - MC: ${token_info['market_cap']:,.2f}, "
                               f"Vol: ${token_info['volume_24h']:,.2f}, Change: {token_info['price_change']}%, "
                               f"Liq: ${token_info['liquidity']:,.2f}, B/S: {token_info['buy_sell_ratio']:.2f}")
                    
                    filtered_tokens.append(token_info)
            
            except Exception as e:
                logger.error(f"Error processing token: {e}")
                continue
                
        logger.info(f"Found {len(filtered_tokens)} tokens matching criteria")
        return filtered_tokens

    def get_filtered_tokens(self):
        """
        Get Solana tokens that match our criteria
        """
        tokens_data = self.get_solana_tokens()
        if tokens_data:
            return self.apply_filters(tokens_data)
        return []
        
    def get_token_pair_by_address(self, token_address):
        """
        Get specific token pair information by token address
        """
        try:
            # First try exact token API endpoint
            endpoints = [
                f"{self.api_url}/tokens/{token_address}",
                f"{self.api_url}/search?q={token_address}",
                f"https://api.dexscreener.com/latest/dex/tokens/{token_address}",
                f"https://api.dexscreener.com/latest/dex/search?q={token_address}",
                # Try additional endpoints
                f"https://api.dexscreener.io/latest/dex/tokens/{token_address}",
                f"https://api.dexscreener.com/v2/dex/tokens/{token_address}"
            ]
            
            for endpoint in endpoints:
                try:
                    logger.info(f"Trying to get token by address using: {endpoint}")
                    response = requests.get(endpoint, timeout=15)  # Increased timeout
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Handle the main data format
                        if "pairs" in data and isinstance(data["pairs"], list) and len(data["pairs"]) > 0:
                            # Find the exact token match if possible
                            for pair in data["pairs"]:
                                # Check if this pair is for Solana
                                if "chainId" in pair and pair["chainId"] != "solana":
                                    continue
                                    
                                # Extract and use our helper method for consistent processing
                                token_info = self._extract_token_data(pair)
                                if token_info and token_info["address"].lower() == token_address.lower():
                                    logger.info(f"Found exact token match for {token_address}")
                                    return pair
                            
                            # If no exact match for the specified token, get the most liquid pair
                            solana_pairs = [p for p in data["pairs"] if p.get("chainId") == "solana"]
                            if solana_pairs:
                                # Sort by liquidity if available
                                try:
                                    sorted_pairs = sorted(
                                        solana_pairs,
                                        key=lambda x: float(x.get("liquidity", {}).get("usd", 0)) 
                                        if isinstance(x.get("liquidity"), dict) else 0,
                                        reverse=True
                                    )
                                    logger.info(f"Using most liquid pair for {token_address}")
                                    return sorted_pairs[0]
                                except Exception as e:
                                    logger.warning(f"Error sorting pairs by liquidity: {e}")
                                    # Just return the first Solana pair
                                    return solana_pairs[0]
                            
                            # Fallback to first pair if no Solana pairs specifically identified
                            logger.info(f"No exact Solana match found, using first pair for {token_address}")
                            return data["pairs"][0]
                            
                        # Handle array format response
                        elif isinstance(data, list) and len(data) > 0:
                            valid_pairs = []
                            for pair in data:
                                # Check if this is a Solana token
                                if "chainId" in pair and pair["chainId"] != "solana":
                                    continue
                                    
                                token_info = self._extract_token_data(pair)
                                if token_info:
                                    valid_pairs.append(pair)
                                    if token_info["address"].lower() == token_address.lower():
                                        return pair
                            
                            # If we have valid pairs but no exact match, return the first valid one
                            if valid_pairs:
                                return valid_pairs[0]
                            
                            # No valid Solana pairs found, so use the first item if available
                            if data:
                                return data[0]
                        
                        # Another potential format with data field
                        elif "data" in data:
                            if isinstance(data["data"], list) and len(data["data"]) > 0:
                                valid_data = [p for p in data["data"] if "chainId" not in p or p["chainId"] == "solana"]
                                if valid_data:
                                    return valid_data[0]
                                return data["data"][0]
                            elif isinstance(data["data"], dict):
                                return data["data"]
                    
                except Exception as e:
                    logger.warning(f"Error with endpoint {endpoint}: {e}")
                    continue
            
            logger.warning(f"Could not find token with address: {token_address}")
            return None
        except Exception as e:
            logger.error(f"Error fetching token by address: {e}")
            return None

# For testing
if __name__ == "__main__":
    api = DexScreenerAPI()
    filtered_tokens = api.get_filtered_tokens()
    print(f"Found {len(filtered_tokens)} tokens matching the criteria:")
    for token in filtered_tokens:
        print(f"- {token['name']} ({token['symbol']}): ${token['market_cap']:.2f} market cap, {token['price_change']}% 24h change, Contract: {token['address']}")
