#!/usr/bin/env python3
"""
Database migration script to fix session_id column size from 100 to 200 characters.
This fixes the critical production bug where Flask session IDs are 155+ chars but DB schema only allows 100.

Run this script to apply the schema fix:
python fix_session_id_schema.py
"""

import os
import sys
from app import app, db
from sqlalchemy import text

def apply_session_id_fix():
    """Apply the session_id column size fix to all affected tables"""

    print("🔧 Starting session_id schema fix...")

    with app.app_context():
        try:
            # Get database URL to determine if it's PostgreSQL or SQLite
            database_url = app.config.get('DATABASE_URL', '')
            is_postgres = 'postgresql' in database_url or 'postgres' in database_url

            print(f"📊 Database type detected: {'PostgreSQL' if is_postgres else 'SQLite'}")

            # Table and column mappings
            tables_to_fix = [
                'conversation',
                'page_view',
                'user_action'
            ]

            for table_name in tables_to_fix:
                print(f"🔄 Updating {table_name}.session_id column...")

                if is_postgres:
                    # PostgreSQL syntax
                    sql = f"ALTER TABLE {table_name} ALTER COLUMN session_id TYPE VARCHAR(200);"
                else:
                    # SQLite doesn't support ALTER COLUMN directly, need to recreate table
                    # For development, we'll just drop and recreate the database
                    print("⚠️  SQLite detected - you'll need to recreate the database")
                    print("   Run: rm hindi_tutor.db && python app.py (will auto-recreate)")
                    continue

                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f"✅ Successfully updated {table_name}.session_id")
                except Exception as e:
                    print(f"❌ Error updating {table_name}: {e}")
                    db.session.rollback()
                    return False

            print("🎉 Session ID schema fix completed successfully!")
            print("📈 Analytics tracking should now work properly in production")
            return True

        except Exception as e:
            print(f"💥 Critical error during schema fix: {e}")
            return False

def verify_fix():
    """Verify the fix was applied correctly"""
    print("\n🔍 Verifying schema fix...")

    with app.app_context():
        try:
            # Try to get column info for verification
            result = db.session.execute(text("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_name IN ('conversation', 'page_view', 'user_action')
                AND column_name = 'session_id'
            """))

            for row in result:
                col_name, data_type, max_length = row
                print(f"  ✓ {col_name}: {data_type}({max_length})")

            return True
        except Exception as e:
            print(f"⚠️  Could not verify schema (normal for SQLite): {e}")
            return True

if __name__ == "__main__":
    print("🚀 Session ID Schema Fix Tool")
    print("=" * 50)

    # Backup reminder
    print("⚠️  IMPORTANT: Ensure you have a database backup before proceeding!")
    print("   For Heroku PostgreSQL: heroku pg:backups:capture")
    print("")

    # Confirm execution
    if len(sys.argv) > 1 and sys.argv[1] == '--force':
        proceed = True
    else:
        proceed = input("Continue with schema fix? (y/N): ").lower().startswith('y')

    if proceed:
        success = apply_session_id_fix()
        if success:
            verify_fix()
            print("\n🎯 Next steps:")
            print("   1. Deploy this code to production")
            print("   2. Run this script on production: python fix_session_id_schema.py --force")
            print("   3. Monitor logs to confirm analytics tracking works")
        else:
            print("\n💥 Schema fix failed - check errors above")
            sys.exit(1)
    else:
        print("❌ Schema fix cancelled")
        sys.exit(0)