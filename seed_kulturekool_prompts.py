"""Seed KultureKool topics with full prompts from prompt files.

Usage:
    python seed_kulturekool_prompts.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app
from models import db, Educator, EducatorTopic

EDUCATOR_CODE = 'kulturekool'
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts', 'kulturekool')

TOPICS = [
    'simple_verbs',
    'holi_festival',
    'things_we_wear',
    'things_in_my_room',
]


def load_prompt(topic_key, prompt_type):
    """Load a prompt file. prompt_type: 'initial' or 'conversation'."""
    filename = f"{topic_key}_{prompt_type}.txt"
    filepath = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  Warning: {filename} not found, skipping")
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def main():
    with app.app_context():
        db.create_all()

        educator = Educator.query.filter_by(short_code=EDUCATOR_CODE).first()
        if not educator:
            print(f"Error: Educator '{EDUCATOR_CODE}' not found. Create it first:")
            print(f'  python create_educator.py create "{EDUCATOR_CODE}" "KultureKool" --hindi "कल्चरकूल"')
            sys.exit(1)

        for topic_key in TOPICS:
            topic = EducatorTopic.query.filter_by(
                educator_id=educator.id, topic_key=topic_key
            ).first()
            if not topic:
                print(f"  Skipping {topic_key}: topic not found for educator '{EDUCATOR_CODE}'")
                continue

            initial = load_prompt(topic_key, 'initial')
            conversation = load_prompt(topic_key, 'conversation')

            updated = []
            if initial:
                topic.prompt_initial = initial
                updated.append('initial')
            if conversation:
                topic.prompt_conversation = conversation
                updated.append('conversation')

            if updated:
                db.session.commit()
                print(f"  Seeded {topic.full_key}: {', '.join(updated)}")
            else:
                print(f"  {topic.full_key}: no prompt files found")

    print("Done!")


if __name__ == '__main__':
    main()
