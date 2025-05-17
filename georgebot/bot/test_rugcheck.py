from rugcheck import RugCheckAPI
import json

# Test tokens - real Solana token addresses for testing
TEST_TOKENS = {
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC - Likely safe
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", # BONK - Meme token
    # Add a potentially risky token if you know one
}

def test_rugcheck_api():
    """Test RugCheck API functionality"""
    print("Testing RugCheck API...")
    
    try:
        # Initialize the API
        api = RugCheckAPI()
        
        # Test the RugCheck API for each token
        for name, address in TEST_TOKENS.items():
            print(f"\nChecking {name} token ({address}):")
            
            # Get raw safety data
            safety_data = api.get_token_safety(address)
            if safety_data:
                print(f"✅ Retrieved safety data for {name}")
                print(f"Safety data sample: {str(safety_data)[:200]}..." if len(str(safety_data)) > 200 else safety_data)
            else:
                print(f"❌ Could not retrieve safety data for {name}")
                # Continue testing even if one token fails
                continue
                
            # Get safety score
            safety_score = api.get_safety_score(address)
            print(f"Safety score: {safety_score}/100")
            
            # Check if token is considered safe
            is_safe = api.is_safe_token(address)
            print(f"Token considered safe: {'✅ Yes' if is_safe else '❌ No'}")
            
            # Test different threshold
            is_safe_lower = api.is_safe_token(address, min_score=50)
            print(f"Token safe with 50% threshold: {'✅ Yes' if is_safe_lower else '❌ No'}")
        
        # Test caching mechanism
        print("\nTesting cache functionality...")
        # Get data for a token again (should be from cache)
        start_time = __import__('time').time()
        
        test_token = list(TEST_TOKENS.values())[0]
        cached_data = api.get_token_safety(test_token)
        
        end_time = __import__('time').time()
        elapsed = end_time - start_time
        
        if cached_data and elapsed < 0.1:
            print(f"✅ Cache appears to be working (retrieval took {elapsed:.4f} seconds)")
        else:
            print(f"⚠️ Cache might not be working as expected (retrieval took {elapsed:.4f} seconds)")
        
        return True
    except Exception as e:
        print(f"❌ Error testing RugCheck API: {e}")
        return False

if __name__ == "__main__":
    success = test_rugcheck_api()
    
    if success:
        print("\n✅ RugCheck API test completed!")
        print("Note: If you received error responses from the RugCheck API, please verify your API key and endpoint.")
    else:
        print("\n❌ RugCheck API test failed!") 