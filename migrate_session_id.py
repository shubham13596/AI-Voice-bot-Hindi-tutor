#!/usr/bin/env python3
"""
Simple database migration script to fix session_id column size.
Auto-runs without confirmation - suitable for Heroku deployment.
"""

import os
from app import app, db
from sqlalchemy import text

def main():
    print("🔧 Applying session_id schema fix...")

    with app.app_context():
        try:
            # Check if we're on Heroku by looking for DATABASE_URL
            database_url = os.environ.get('DATABASE_URL', '')

            if not database_url or 'postgresql' not in database_url:
                print("❌ This script is designed for PostgreSQL (Heroku production)")
                print("   For SQLite development, delete hindi_tutor.db and restart the app")
                return False

            print("📊 PostgreSQL detected - applying schema fixes...")

            # Fix all tables with session_id columns
            tables = ['conversation', 'page_view', 'user_action']

            for table_name in tables:
                print(f"🔄 Updating {table_name}.session_id...")

                sql = f"ALTER TABLE {table_name} ALTER COLUMN session_id TYPE VARCHAR(200);"
                db.session.execute(text(sql))
                db.session.commit()

                print(f"✅ {table_name}.session_id updated successfully")

            print("🎉 All session_id columns updated to VARCHAR(200)")
            print("📈 Analytics tracking should now work properly!")
            return True

        except Exception as e:
            print(f"💥 Error during schema migration: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)