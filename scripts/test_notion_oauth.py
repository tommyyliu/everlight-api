#!/usr/bin/env python3
"""
Phase 1 Test Script: Inspect Notion OAuth Response
This script helps understand what data Notion actually returns during OAuth.
"""
import os
import httpx
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_oauth_exchange(auth_code: str):
    """
    Test OAuth token exchange and log the full response.

    Usage:
    1. Go through Notion OAuth flow manually to get an auth code
    2. Run: python scripts/test_notion_oauth.py
    3. Paste the code when prompted
    """
    client_id = os.getenv("NOTION_CLIENT_ID")
    client_secret = os.getenv("NOTION_CLIENT_SECRET")
    redirect_uri = os.getenv("NOTION_REDIRECT_URI")

    print("=" * 60)
    print("NOTION OAUTH RESPONSE TEST")
    print("=" * 60)
    print(f"\nClient ID: {client_id[:10]}...")
    print(f"Redirect URI: {redirect_uri}\n")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/oauth/token",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": redirect_uri,
            },
            auth=(client_id, client_secret)
        )

        print(f"Status Code: {response.status_code}\n")

        if response.status_code == 200:
            data = response.json()

            print("=" * 60)
            print("FULL OAUTH RESPONSE:")
            print("=" * 60)
            print(json.dumps(data, indent=2))
            print("\n")

            print("=" * 60)
            print("KEY FIELDS FOR REFACTOR:")
            print("=" * 60)
            print(f"✓ access_token: {data.get('access_token', 'MISSING')[:20]}...")
            print(f"✓ bot_id: {data.get('bot_id', 'MISSING')}")
            print(f"✓ workspace_id: {data.get('workspace_id', 'MISSING')}")
            print(f"✓ workspace_name: {data.get('workspace_name', 'MISSING')}")
            print(f"✓ owner: {json.dumps(data.get('owner', 'MISSING'), indent=2)}")

            # Check if we have person_id in owner
            owner = data.get('owner', {})
            if isinstance(owner, dict):
                if 'workspace' in owner:
                    print("\n⚠️  Workspace-level integration (no person_id)")
                elif 'user' in owner:
                    print(f"\n✓ User-level integration - person_id: {owner.get('user', {}).get('id', 'MISSING')}")

            print("\n" + "=" * 60)
            print("FIELDS PRESENT IN RESPONSE:")
            print("=" * 60)
            for key in data.keys():
                print(f"  - {key}")

        else:
            print("ERROR:")
            print(response.text)


def generate_oauth_url():
    """Generate the OAuth URL for manual testing."""
    client_id = os.getenv("NOTION_CLIENT_ID")
    redirect_uri = os.getenv("NOTION_REDIRECT_URI")

    oauth_url = (
        f"https://api.notion.com/v1/oauth/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&owner=user"
        f"&redirect_uri={redirect_uri}"
    )

    print("\n" + "=" * 60)
    print("NOTION OAUTH URL (Copy and paste in browser):")
    print("=" * 60)
    print(oauth_url)
    print("\n")


if __name__ == "__main__":
    import sys

    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║  NOTION OAUTH PHASE 1 TEST SCRIPT                        ║")
    print("╚" + "=" * 58 + "╝")
    print("\n")

    if len(sys.argv) > 1:
        # Code provided as argument
        code = sys.argv[1]
        import asyncio
        asyncio.run(test_oauth_exchange(code))
    else:
        # Interactive mode
        generate_oauth_url()
        print("Instructions:")
        print("1. Copy the URL above and paste it in your browser")
        print("2. Complete the Notion OAuth flow")
        print("3. Copy the 'code' parameter from the redirect URL")
        print("4. Run: python scripts/test_notion_oauth.py <code>")
        print("\nOr press Ctrl+C to exit and run with code as argument\n")
