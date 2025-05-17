from dexscreener import DexScreenerAPI
import json

# Test token addresses to specifically check
TEST_TOKENS = {
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
}

def test_dexscreener_api():
    """Test DexScreener API functionality"""
    print("Testing DexScreener API...")
    
    try:
        # Initialize the API
        api = DexScreenerAPI()
        
        # Test getting Solana tokens without filters
        print("\nTesting getting all Solana tokens...")
        tokens_data = api.get_solana_tokens()
        
        if tokens_data is None:
            print("❌ Failed to fetch Solana tokens")
            return False
            
        # Check if we got pairs
        pairs_count = len(tokens_data.get("pairs", []))
        print(f"✅ Successfully fetched {pairs_count} token pairs from DexScreener")
        
        # Test filtering tokens based on criteria
        print("\nTesting token filtering...")
        filtered_tokens = api.get_filtered_tokens()
        print(f"✅ Found {len(filtered_tokens)} tokens matching the criteria")
        
        # Display the first 3 tokens that passed the filters
        if filtered_tokens:
            print("\nSample filtered tokens:")
            for i, token in enumerate(filtered_tokens[:3]):
                print(f"\nToken {i+1}:")
                print(f"  Name: {token['name']} ({token['symbol']})")
                print(f"  Address: {token['address']}")
                print(f"  Market Cap: ${token['market_cap']:,.2f}")
                print(f"  24h Volume: ${token['volume_24h']:,.2f}")
                print(f"  Price Change: {token['price_change']:+.2f}%")
                print(f"  Liquidity: ${token['liquidity']:,.2f}")
                print(f"  Buy/Sell Ratio: {token['buy_sell_ratio']:.2f}")
        
        # Test specific token lookup
        print("\nTesting specific token lookup...")
        for name, address in TEST_TOKENS.items():
            print(f"\nLooking up {name} ({address}):")
            pair_data = api.get_token_pair_by_address(address)
            
            if pair_data:
                token_name = pair_data.get("baseToken", {}).get("name", "Unknown")
                token_symbol = pair_data.get("baseToken", {}).get("symbol", "Unknown")
                token_price = pair_data.get("priceUsd", "0")
                
                print(f"✅ Found token: {token_name} ({token_symbol})")
                print(f"  Price: ${token_price}")
                print(f"  URL: {pair_data.get('url', 'N/A')}")
            else:
                print(f"❌ Could not find pair data for {name}")
        
        return True
    except Exception as e:
        print(f"❌ Error testing DexScreener API: {e}")
        return False

if __name__ == "__main__":
    success = test_dexscreener_api()
    
    if success:
        print("\n✅ DexScreener API test completed successfully!")
    else:
        print("\n❌ DexScreener API test failed!") 