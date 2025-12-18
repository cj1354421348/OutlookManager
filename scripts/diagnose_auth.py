import json
import asyncio
import httpx
import sys
from pathlib import Path

# Configuration
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
ACCOUNTS_FILE = Path("data/accounts.json")

async def diagnose_accounts():
    if not ACCOUNTS_FILE.exists():
        print(f"❌ File not found: {ACCOUNTS_FILE}")
        return

    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            accounts = json.load(f)
    except Exception as e:
        print(f"❌ Error reading {ACCOUNTS_FILE}: {e}")
        return

    print(f"\n🔍 Diagnosing {len(accounts)} accounts in {ACCOUNTS_FILE}...\n")

    async with httpx.AsyncClient() as client:
        for email, data in accounts.items():
            print(f"--------------------------------------------------")
            print(f"📧 Account: {email}")
            
            refresh_token = data.get("refresh_token")
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")

            if not refresh_token:
                print("   ❌ Missing 'refresh_token'")
                continue
            if not client_id:
                print("   ❌ Missing 'client_id'")
                continue

            # Check Client Secret status
            if client_secret:
                print("   ℹ️  Configured as: Confidential Client (has client_secret)")
            else:
                print("   ℹ️  Configured as: Public Client (no client_secret)")

            # Payload construction
            payload = {
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
            }
            
            if client_secret:
                payload["client_secret"] = client_secret

            print(f"   🔄 Attempting token refresh with Azure...")
            
            try:
                response = await client.post(TOKEN_URL, data=payload)
                
                if response.status_code == 200:
                    print("   ✅ SUCCESS: Token is valid and configuration matches.")
                    token_data = response.json()
                    print(f"      New Access Token starts with: {token_data.get('access_token')[:10]}...")
                else:
                    print(f"   ❌ FAILED (HTTP {response.status_code})")
                    try:
                        error_json = response.json()
                        error = error_json.get("error")
                        error_description = error_json.get("error_description")
                        print(f"      Error Code: {error}")
                        print(f"      Details: {error_description}")
                        
                        # Linus-style analysis
                        if "7000218" in str(error_description):
                            print("\n      💡 ANALYSIS: The request body must contain the following parameter: 'client_assertion' or 'client_secret'.")
                            print("      MEANING: Azure expects a Web App (Confidential Client) but you didn't provide a secret.")
                            print("      FIX: Add 'client_secret' to accounts.json OR change Azure registration to Public Client.")
                        elif "70002" in str(error_description):
                            print("\n      💡 ANALYSIS: Client is not supported for this feature.")
                            print("      MEANING: You are likely mixing Web/Public client settings/tokens.")
                        elif "interaction_required" in str(error) or "invalid_grant" in str(error):
                            print("\n      💡 ANALYSIS: Refresh Token is invalid, expired, or revoked.")
                            print("      MEANING: The token string itself is bad. It doesn't matter what your config is.")
                    except:
                        print(f"      Raw Response: {response.text}")

            except Exception as e:
                print(f"   ❌ EXCEPTION: {e}")

    print(f"\n--------------------------------------------------")
    print("Diagnosis Complete.")

if __name__ == "__main__":
    # Windows loop policy fix
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(diagnose_accounts())
