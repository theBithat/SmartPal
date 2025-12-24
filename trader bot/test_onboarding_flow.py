#!/usr/bin/env python3
"""
Test script to verify Arena onboarding flow
Tests the complete user journey from registration to God creation
"""

import requests
import json
from datetime import datetime
import sys

# Server configuration - use localhost if available
if len(sys.argv) > 1 and sys.argv[1] == '--local':
    BASE_URL = "http://localhost:9000"
else:
    BASE_URL = "http://66.94.110.211:9000"
    
ARENA_API = f"{BASE_URL}/api/arena"

def test_registration():
    """Test user registration"""
    print("\n" + "="*70)
    print("TEST 1: User Registration")
    print("="*70)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_user = {
        "username": f"testuser_{timestamp}",
        "email": f"test_{timestamp}@arena.test",
        "password": "TestPass123!",
        "tier": "sparta"
    }
    
    response = requests.post(f"{ARENA_API}/auth/register", json=test_user)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 201:
        data = response.json()
        # Add email and password to response for later use
        data['email'] = test_user['email']
        data['password'] = test_user['password']
        print(f"✅ User created: {data.get('username', test_user['username'])}")
        print(f"   User ID: {data.get('user_id', 'N/A')}")
        print(f"   Email: {test_user['email']}")
        print(f"   Access Token: {data.get('access_token')[:20]}...")
        return data
    else:
        print(f"❌ Registration failed: {response.text}")
        return None

def test_login(email, password):
    """Test user login"""
    print("\n" + "="*70)
    print("TEST 2: User Login")
    print("="*70)
    
    response = requests.post(f"{ARENA_API}/auth/login", json={
        "email": email,
        "password": password
    })
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Login successful")
        print(f"   Onboarding completed: {data.get('onboarding_completed')}")
        print(f"   Access Token: {data.get('access_token')[:20]}...")
        return data
    else:
        print(f"❌ Login failed: {response.text}")
        return None

def test_onboarding_complete(access_token):
    """Test onboarding completion"""
    print("\n" + "="*70)
    print("TEST 3: Complete Onboarding")
    print("="*70)
    
    onboarding_data = {
        "god_preset": "zeus",
        "trading_pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        "initial_capital": 1000,
        "leverage": 50,
        "paper_trading": True,
        "chatgpt_validation": True
    }
    
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post(
        f"{ARENA_API}/onboarding/complete",
        json=onboarding_data,
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 201:
        data = response.json()
        print(f"✅ Onboarding completed")
        print(f"   God ID: {data.get('god_id')}")
        print(f"   Message: {data.get('message')}")
        return data.get('god_id')
    else:
        print(f"❌ Onboarding failed: {response.text}")
        return None

def test_gods_status(access_token):
    """Test getting Gods status"""
    print("\n" + "="*70)
    print("TEST 4: Get Gods Status")
    print("="*70)
    
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{ARENA_API}/gods/status", headers=headers)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        gods = data.get('gods', [])
        print(f"✅ Gods retrieved: {len(gods)}")
        
        for god in gods:
            print(f"\n   God: {god['name']}")
            print(f"   Avatar: {god['avatar']}")
            print(f"   Status: {god['status']}")
            print(f"   Capital: ${god['capital_balance']}")
            print(f"   Trading Pairs: {', '.join(god['trading_pairs'])}")
            print(f"   Paper Trading: {god['is_paper_trading']}")
            print(f"   Leverage: {god['leverage']}x")
        
        return gods
    else:
        print(f"❌ Failed to get Gods: {response.text}")
        return None

def test_god_regimes(access_token, god_id):
    """Test getting God's regimes"""
    print("\n" + "="*70)
    print("TEST 5: Get God Regimes")
    print("="*70)
    
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"{ARENA_API}/gods/{god_id}/regimes",
        headers=headers
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        regimes = data.get('regimes', [])
        print(f"✅ Regimes retrieved: {len(regimes)}")
        
        for regime in regimes:
            print(f"\n   Regime: {regime['name']}")
            print(f"   Active: {regime['is_active']}")
            print(f"   Strategists: {len(regime['strategists'])}")
            
            for strat in regime['strategists']:
                print(f"      - {strat['avatar']} {strat['name']} ({strat['risk_level']})")
        
        return regimes
    else:
        print(f"❌ Failed to get regimes: {response.text}")
        return None

def run_full_test():
    """Run complete onboarding flow test"""
    print("\n" + "="*70)
    print("🏛️  SMARTPAL ARENA - ONBOARDING FLOW TEST")
    print("="*70)
    print(f"Server: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: Registration
    reg_data = test_registration()
    if not reg_data:
        print("\n❌ Test suite failed at registration")
        return False
    
    access_token = reg_data.get('access_token')
    test_email = reg_data.get('email')
    test_password = reg_data.get('password')
    
    # Test 2: Login (verify onboarding_completed is false)
    login_data = test_login(test_email, test_password)
    if not login_data:
        print("\n❌ Test suite failed at login")
        return False
    
    if login_data.get('onboarding_completed') != False:
        print(f"\n⚠️  Warning: onboarding_completed should be False, got {login_data.get('onboarding_completed')}")
    
    # Test 3: Complete onboarding
    god_id = test_onboarding_complete(access_token)
    if not god_id:
        print("\n❌ Test suite failed at onboarding completion")
        return False
    
    # Test 4: Get Gods status
    gods = test_gods_status(access_token)
    if not gods or len(gods) == 0:
        print("\n❌ Test suite failed: No Gods created")
        return False
    
    # Test 5: Get God regimes
    regimes = test_god_regimes(access_token, god_id)
    if not regimes or len(regimes) == 0:
        print("\n❌ Test suite failed: No regimes created")
        return False
    
    # Verify Sparta tier limits
    if len(gods) > 1:
        print(f"\n⚠️  Warning: Sparta tier should have 1 God, found {len(gods)}")
    
    if len(regimes) > 1:
        print(f"\n⚠️  Warning: Sparta tier should have 1 Regime, found {len(regimes)}")
    
    strategist_count = sum(len(r['strategists']) for r in regimes)
    if strategist_count != 2:
        print(f"\n⚠️  Warning: Sparta tier should have 2 Strategists, found {strategist_count}")
    
    # Final summary
    print("\n" + "="*70)
    print("✅ ALL TESTS PASSED!")
    print("="*70)
    print(f"   Gods created: {len(gods)}")
    print(f"   Regimes created: {len(regimes)}")
    print(f"   Strategists created: {strategist_count}")
    print(f"   Test user: {test_email}")
    print("="*70)
    
    return True

if __name__ == "__main__":
    try:
        success = run_full_test()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test suite crashed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
