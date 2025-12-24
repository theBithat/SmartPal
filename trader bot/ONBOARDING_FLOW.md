# Arena Onboarding Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     NEW USER REGISTRATION                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    /arena/register (form)
                              │
                              ▼
                POST /api/arena/auth/register
                    (creates user record)
                              │
                              ▼
                  Auto-login (JWT tokens)
                 onboarding_completed = false
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ONBOARDING WIZARD START                       │
│                    /arena/onboarding                            │
└─────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┴─────────────────┐
            │                                   │
            ▼                                   ▼
    ┌──────────────┐                  ┌──────────────┐
    │   STEP 1     │                  │  Skip Option │
    │   Welcome    │                  │  (disabled)  │
    │   Sparta     │                  └──────────────┘
    │   Benefits   │
    └──────────────┘
            │
            ▼
    ┌──────────────┐
    │   STEP 2     │
    │ God Selection│
    │  (Required)  │
    ├──────────────┤
    │ Zeus      ⚡ │
    │ Athena    🦉 │
    │ Poseidon  🌊 │
    │ Ares      ⚔️ │
    │ Hephaestus🔥 │
    └──────────────┘
            │
            ▼
    ┌──────────────┐
    │   STEP 3     │
    │Trading Pairs │
    │  (Min 1)     │
    ├──────────────┤
    │ ☑ BTC/USDT   │
    │ ☑ ETH/USDT   │
    │ ☐ SOL/USDT   │
    │ ...18 more   │
    ├──────────────┤
    │ [Top 10]     │
    │ [Majors]     │
    │ [All] [Clear]│
    └──────────────┘
            │
            ▼
    ┌──────────────┐
    │   STEP 4     │
    │   Settings   │
    ├──────────────┤
    │ Paper: ON 🔒 │
    │ Capital: $1k │
    │ Leverage: 50x│
    │ ChatGPT: ON  │
    └──────────────┘
            │
            ▼
    [Complete Onboarding]
            │
            ▼
POST /api/arena/onboarding/complete
    ┌─────────────────────────┐
    │ 1. Mark onboarding done │
    │ 2. Create God from      │
    │    preset               │
    │ 3. Create Regime        │
    │ 4. Add 2 Strategists    │
    │ 5. Assign trading pairs │
    │ 6. Save risk settings   │
    └─────────────────────────┘
            │
            ▼
    Success → Redirect
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GOD CONTROL DASHBOARD                         │
│                    /arena/god-control                           │
└─────────────────────────────────────────────────────────────────┘
            │
    ┌───────┴───────┐
    │               │
    ▼               ▼
┌──────────┐  ┌──────────────────────────┐
│ Gods     │  │ Regime & Strategists     │
│ List     │  │ Matrix                   │
├──────────┤  ├──────────────────────────┤
│ Zeus⚡   │  │ Regime: Trend Following  │
│ ACTIVE   │  │ ┌──────────┬──────────┐  │
│ $1000    │  │ │Strategist│Strategist│  │
│ +$50 PnL │  │ │   1      │    2     │  │
│ 2 pos.   │  │ │ Win: 5   │ Win: 3   │  │
└──────────┘  │ │ Loss: 2  │ Loss: 1  │  │
              │ └──────────┴──────────┘  │
              └──────────────────────────┘
                      │
                      ▼
              ┌──────────────┐
              │ Quick Stats  │
              ├──────────────┤
              │ Capital: $1k │
              │ P&L: +$50    │
              │ Positions: 2 │
              │ Win Rate: 72%│
              ├──────────────┤
              │ [Start God]  │
              │ [Positions]  │
              │ [Report]     │
              │ [🛑 STOP]    │
              └──────────────┘


═══════════════════════════════════════════════════════════════════
                    EXISTING USER LOGIN FLOW
═══════════════════════════════════════════════════════════════════

        /arena/login
             │
             ▼
   POST /api/arena/auth/login
             │
             ▼
    onboarding_completed = true?
             │
      ┌──────┴──────┐
      │             │
     YES            NO
      │             │
      ▼             ▼
/arena/god-control  /arena/onboarding
  (Dashboard)       (Wizard)


═══════════════════════════════════════════════════════════════════
                    API ENDPOINT FLOW
═══════════════════════════════════════════════════════════════════

Dashboard Mount:
    │
    ├─ GET /api/arena/gods/status
    │   └─ Returns: [{id, name, avatar, status, capital, pnl, 
    │                 positions_count, trading_pairs}]
    │
    ├─ GET /api/arena/gods/{god_id}/regimes
    │   └─ Returns: [{id, name, is_active, strategists[]}]
    │
    └─ Auto-refresh every 30s

User Actions:
    │
    ├─ POST /api/arena/gods/{god_id}/status
    │   └─ Body: {status: 'active'|'paused'|'inactive'}
    │
    ├─ POST /api/arena/gods/emergency-stop
    │   └─ Pauses all Gods + closes positions
    │
    └─ GET /api/arena/user/profile
        └─ Returns tier limits


═══════════════════════════════════════════════════════════════════
                    DATABASE UPDATES
═══════════════════════════════════════════════════════════════════

users table:
    │
    ├─ onboarding_completed: BOOLEAN (default: false)
    ├─ global_risk_settings: JSON
    │   └─ {leverage, chatgpt_validation, paper_trading}
    └─ updated_at: TIMESTAMP

gods table:
    │
    └─ trading_pairs: JSON
        └─ ["BTC/USDT", "ETH/USDT", ...]

New records created on onboarding:
    │
    ├─ gods: 1 record (from preset)
    ├─ regimes: 1 record (default)
    └─ strategists: 2 records (Sparta limit)
