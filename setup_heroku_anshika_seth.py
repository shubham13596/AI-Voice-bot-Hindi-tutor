"""One-shot script to create Anshika Seth educator on Heroku.

No custom topics — users with this educator code see the default built-in topics.

Usage:
    heroku run --app hindi-voice-tutor -- python setup_heroku_anshika_seth.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app
from models import db, Educator


def main():
    with app.app_context():
        db.create_all()

        educator = Educator.query.filter_by(short_code='anshika_seth').first()
        if not educator:
            educator = Educator(
                short_code='anshika_seth',
                name='Anshika Seth',
                brand_color='#4F46E5',
            )
            db.session.add(educator)
            db.session.commit()
            print(f"Created educator: {educator.name} (code: {educator.short_code}, id: {educator.id})")
        else:
            print(f"Educator already exists: {educator.name} (code: {educator.short_code}, id: {educator.id})")

    print("\nDone! Anshika Seth educator is ready.")
    print("Users can sign up with educator code: anshika_seth")


if __name__ == '__main__':
    main()
