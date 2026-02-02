"""
One-time migration script to convert existing English child names to Hindi transliteration.
Run with: python migrate_child_names_to_hindi.py
On Heroku: heroku run python migrate_child_names_to_hindi.py --app your-app-name
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User

# Exact mappings from the provided data
# Keys are lowercase for case-insensitive matching
NAME_MAPPINGS = {
    'vihaan': 'विहान',
    'abir': 'अबीर',
    'shreya': 'श्रेया',
    'manas': 'मानस',
    'chakshu': 'चक्षु',
    'trial': 'ट्रायल',
    'vee': 'वी',
    'adi': 'आदि',
    'micha': 'मिशा',
    'tanya': 'तान्या',
    'simon': 'साइमन',
    'bob': 'बॉब',
    'issa': 'ईसा',
    'z': 'ज़ी',
    'tyler': 'टाइलर',
    'daniel': 'डैनियल',
    'neha': 'नेहा',
    'ridhi': 'रिद्धि',
    'arhaan': 'अरहान',
    'lucas': 'ल्यूकस',
    'v': 'वी',
    'roanik': 'रोनिक',
}


def is_already_hindi(text):
    """Check if text is already in Devanagari script"""
    if not text:
        return False
    # Devanagari Unicode range: U+0900 to U+097F
    for char in text:
        if '\u0900' <= char <= '\u097F':
            return True
    return False


def migrate_child_names(dry_run=True):
    """
    Migrate existing English child names to Hindi transliteration.

    Args:
        dry_run: If True, only print what would be changed without committing.
    """
    print(f"\n{'='*60}")
    print(f"Child Name Migration to Hindi")
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE (changes will be committed)'}")
    print(f"{'='*60}\n")

    with app.app_context():
        # Get all users with a child_name set
        users = User.query.filter(User.child_name.isnot(None)).all()

        print(f"Found {len(users)} users with child_name set\n")

        migrated = []
        skipped_already_hindi = []
        skipped_no_mapping = []

        for user in users:
            current_name = user.child_name.strip()

            # Skip if already in Hindi
            if is_already_hindi(current_name):
                skipped_already_hindi.append({
                    'id': user.id,
                    'email': user.email,
                    'name': current_name
                })
                continue

            # Look up the Hindi translation (case-insensitive)
            hindi_name = NAME_MAPPINGS.get(current_name.lower())

            if hindi_name:
                migrated.append({
                    'id': user.id,
                    'email': user.email,
                    'old_name': current_name,
                    'new_name': hindi_name
                })

                if not dry_run:
                    user.child_name = hindi_name
            else:
                skipped_no_mapping.append({
                    'id': user.id,
                    'email': user.email,
                    'name': current_name
                })

        # Print results
        if migrated:
            print("WILL MIGRATE:" if dry_run else "MIGRATED:")
            print("-" * 50)
            for item in migrated:
                print(f"  User {item['id']} ({item['email']})")
                print(f"    '{item['old_name']}' → '{item['new_name']}'")
            print()

        if skipped_already_hindi:
            print("SKIPPED (already in Hindi):")
            print("-" * 50)
            for item in skipped_already_hindi:
                print(f"  User {item['id']}: {item['name']}")
            print()

        if skipped_no_mapping:
            print("SKIPPED (no mapping found - needs manual review):")
            print("-" * 50)
            for item in skipped_no_mapping:
                print(f"  User {item['id']} ({item['email']}): '{item['name']}'")
            print()

        # Commit if not dry run
        if not dry_run and migrated:
            db.session.commit()
            print("Changes committed to database.")

        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"  Total users with child_name: {len(users)}")
        print(f"  {'Will migrate' if dry_run else 'Migrated'}: {len(migrated)}")
        print(f"  Skipped (already Hindi): {len(skipped_already_hindi)}")
        print(f"  Skipped (no mapping): {len(skipped_no_mapping)}")

        if dry_run and migrated:
            print(f"\nTo apply these changes, run:")
            print(f"  python migrate_child_names_to_hindi.py --live")


if __name__ == '__main__':
    # Check for --live flag
    live_mode = '--live' in sys.argv or '--force' in sys.argv

    migrate_child_names(dry_run=not live_mode)
