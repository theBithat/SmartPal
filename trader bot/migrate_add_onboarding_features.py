#!/usr/bin/env python3
"""
Migration Script: Add Onboarding Features
Adds columns for user onboarding flow and God trading pair management

Changes:
- Add User.onboarding_completed (Boolean, default False)
- Add User.global_risk_settings (JSON)
- Add God.trading_pairs (JSON, stores array like ["BTC/USDT", "ETH/USDT"])

Run: python migrate_add_onboarding_features.py
"""

import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect, Column, Boolean, JSON
from sqlalchemy.orm import sessionmaker


def get_connection_string():
    """Build PostgreSQL connection string from environment"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5433')
    db_name = os.getenv('DB_NAME', 'trading_bot')
    db_user = os.getenv('DB_USER', 'trader')
    db_password = os.getenv('DB_PASSWORD', 'trader_password')
    
    return f"{db_type}://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def column_exists(inspector, table_name, column_name):
    """Check if column exists in table"""
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def run_migration():
    """Run the onboarding features migration"""
    
    print("=" * 70)
    print("🏛️  SmartPal Arena - Onboarding Features Migration")
    print("=" * 70)
    print()
    
    # Connect to database
    connection_string = get_connection_string()
    print(f"📡 Connecting to: {connection_string.split('@')[1]}")
    
    engine = create_engine(connection_string)
    inspector = inspect(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Check if tables exist
        existing_tables = inspector.get_table_names()
        
        if 'users' not in existing_tables:
            print("❌ Error: 'users' table not found. Run migrate_add_arena_tables.py first.")
            return False
        
        if 'gods' not in existing_tables:
            print("❌ Error: 'gods' table not found. Run migrate_add_arena_tables.py first.")
            return False
        
        print("✅ Required tables found: users, gods")
        print()
        
        migrations_applied = []
        migrations_skipped = []
        
        # ====================================================================
        # MIGRATION 1: Add User.onboarding_completed
        # ====================================================================
        
        if not column_exists(inspector, 'users', 'onboarding_completed'):
            print("📝 Adding column: users.onboarding_completed...")
            session.execute(text("""
                ALTER TABLE users 
                ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE
            """))
            session.commit()
            migrations_applied.append("users.onboarding_completed")
            print("   ✅ Added users.onboarding_completed (Boolean, default False)")
        else:
            migrations_skipped.append("users.onboarding_completed (already exists)")
            print("   ⏭️  Skipped: users.onboarding_completed (already exists)")
        
        # ====================================================================
        # MIGRATION 2: Add User.global_risk_settings
        # ====================================================================
        
        if not column_exists(inspector, 'users', 'global_risk_settings'):
            print("📝 Adding column: users.global_risk_settings...")
            session.execute(text("""
                ALTER TABLE users 
                ADD COLUMN global_risk_settings JSON
            """))
            session.commit()
            migrations_applied.append("users.global_risk_settings")
            print("   ✅ Added users.global_risk_settings (JSON)")
        else:
            migrations_skipped.append("users.global_risk_settings (already exists)")
            print("   ⏭️  Skipped: users.global_risk_settings (already exists)")
        
        # ====================================================================
        # MIGRATION 3: Add God.trading_pairs
        # ====================================================================
        
        if not column_exists(inspector, 'gods', 'trading_pairs'):
            print("📝 Adding column: gods.trading_pairs...")
            session.execute(text("""
                ALTER TABLE gods 
                ADD COLUMN trading_pairs JSON
            """))
            session.commit()
            migrations_applied.append("gods.trading_pairs")
            print("   ✅ Added gods.trading_pairs (JSON)")
            
            # Set default trading pairs for existing Gods
            print("   📝 Setting default trading pairs for existing Gods...")
            session.execute(text("""
                UPDATE gods 
                SET trading_pairs = '["BTC/USDT", "ETH/USDT", "BNB/USDT"]'::json
                WHERE trading_pairs IS NULL
            """))
            session.commit()
            print("   ✅ Default pairs set for existing Gods")
        else:
            migrations_skipped.append("gods.trading_pairs (already exists)")
            print("   ⏭️  Skipped: gods.trading_pairs (already exists)")
        
        # ====================================================================
        # SUMMARY
        # ====================================================================
        
        print()
        print("=" * 70)
        print("📊 MIGRATION SUMMARY")
        print("=" * 70)
        
        if migrations_applied:
            print(f"\n✅ Applied {len(migrations_applied)} migration(s):")
            for m in migrations_applied:
                print(f"   - {m}")
        
        if migrations_skipped:
            print(f"\n⏭️  Skipped {len(migrations_skipped)} (already exists):")
            for m in migrations_skipped:
                print(f"   - {m}")
        
        print()
        print("✅ Onboarding features migration completed successfully!")
        print()
        print("Next steps:")
        print("1. Deploy updated templates (onboarding.html, god_control.html)")
        print("2. Update arena_routes.py and arena_api.py")
        print("3. Restart the application")
        print()
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        session.close()


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
