import requests
import json
from solana_verify import SolanaVerifier

# Test tokens - real Solana token addresses for testing
TEST_TOKENS = {
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "SOL": "So11111111111111111111111111111111111111112",    # Wrapped SOL
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263" # BONK token
}

def test_solana_rpc_api():
    """
    Test the Solana RPC API connection and token verification functions
    """
    print("Testing Solana RPC API...")
    
    # Initialize the verifier
    verifier = SolanaVerifier()
    
    # Test the connection by getting the current block height
    try:
        # Simple RPC call to check connection
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBlockHeight",
            "params": []
        }
        response = requests.post(verifier.rpc_url, headers=verifier.headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if "result" in result:
                block_height = result["result"]
                print(f"✅ Connected to Solana RPC - Current block height: {block_height}")
            else:
                print(f"❌ Invalid response from Solana RPC: {result}")
                return False
        else:
            print(f"❌ Failed to connect to Solana RPC: {response.status_code}")
            return False
            
        # Test token validations
        print("\nTesting token verification:")
        for name, address in TEST_TOKENS.items():
            print(f"\nVerifying {name} token ({address}):")
            
            # Check if token is valid
            is_valid = verifier.is_valid_token(address)
            print(f"Is valid token: {'✅ Yes' if is_valid else '❌ No'}")
            
            # Get token info
            if is_valid:
                token_info = verifier.get_token_info(address)
                print(f"Token info: {json.dumps(token_info, indent=2)}")
        
        return True
    except Exception as e:
        print(f"❌ Error testing Solana RPC API: {e}")
        return False

if __name__ == "__main__":
    success = test_solana_rpc_api()
    
    if success:
        print("\n✅ Solana RPC API test completed successfully!")
    else:
        print("\n❌ Solana RPC API test failed!") 