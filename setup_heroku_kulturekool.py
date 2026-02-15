"""One-shot script to create KultureKool educator + topics + seed prompts on Heroku.

Usage:
    heroku run --app hindi-voice-tutor -- python setup_heroku_kulturekool.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app
from models import db, Educator, EducatorTopic

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts', 'kulturekool')

TOPICS = [
    {
        'topic_key': 'simple_verbs',
        'name': 'Simple Verbs',
        'name_hindi': 'क्रियाएँ',
        'description': 'Practice using everyday verbs in sentences',
        'icon': '\U0001f3c3',  # 🏃
        'topic_focus': 'Action verbs for daily activities',
        'key_vocabulary': json.dumps(["खाना", "पीना", "सोना", "खेलना", "पढ़ना", "लिखना", "दौड़ना"]),
    },
    {
        'topic_key': 'holi_festival',
        'name': 'Holi - Festival of Colors',
        'name_hindi': 'होली',
        'description': 'Learn about Holi and practice colors!',
        'icon': '\U0001f3a8',  # 🎨
        'topic_focus': 'Holi celebration, colors, and traditions',
        'key_vocabulary': json.dumps(["रंग", "गुलाल", "पिचकारी", "लाल", "नीला", "पीला", "हरा"]),
    },
    {
        'topic_key': 'things_we_wear',
        'name': 'Things We Wear',
        'name_hindi': 'कपड़े',
        'description': 'Talk about clothes and accessories!',
        'icon': '\U0001f455',  # 👕
        'topic_focus': 'Clothing items and getting dressed',
        'key_vocabulary': json.dumps(["जूते", "कमीज़", "चश्मा", "टोपी", "मोज़े"]),
    },
    {
        'topic_key': 'things_in_my_room',
        'name': 'Things in My Room',
        'name_hindi': 'मेरा कमरा',
        'description': "Describe what's in your room!",
        'icon': '\U0001f6cf\ufe0f',  # 🛏️
        'topic_focus': 'Room objects and furniture',
        'key_vocabulary': json.dumps(["कुर्सी", "बिस्तर", "अलमारी", "दरवाज़ा", "खिड़की"]),
    },
]


def load_prompt(topic_key, prompt_type):
    filepath = os.path.join(PROMPTS_DIR, f"{topic_key}_{prompt_type}.txt")
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def main():
    with app.app_context():
        db.create_all()

        # Get or skip educator (should already exist from previous step)
        educator = Educator.query.filter_by(short_code='kulturekool').first()
        if not educator:
            educator = Educator(
                short_code='kulturekool',
                name='KultureKool',
                display_name_hindi='कल्चरकूल',
                brand_color='#4F46E5',
            )
            db.session.add(educator)
            db.session.commit()
            print(f"Created educator: {educator.name} (id: {educator.id})")
        else:
            print(f"Educator exists: {educator.name} (id: {educator.id})")

        # Create topics + seed prompts
        for i, t in enumerate(TOPICS):
            topic = EducatorTopic.query.filter_by(
                educator_id=educator.id, topic_key=t['topic_key']
            ).first()

            if not topic:
                topic = EducatorTopic(
                    educator_id=educator.id,
                    topic_key=t['topic_key'],
                    name=t['name'],
                    name_hindi=t.get('name_hindi'),
                    description=t['description'],
                    icon=t['icon'],
                    topic_focus=t['topic_focus'],
                    key_vocabulary=t['key_vocabulary'],
                    display_order=i + 1,
                )
                db.session.add(topic)
                db.session.commit()
                print(f"  Created topic: {topic.full_key}")
            else:
                print(f"  Topic exists: {topic.full_key}")

            # Seed prompts
            initial = load_prompt(t['topic_key'], 'initial')
            conversation = load_prompt(t['topic_key'], 'conversation')
            updated = []
            if initial:
                topic.prompt_initial = initial
                updated.append('initial')
            if conversation:
                topic.prompt_conversation = conversation
                updated.append('conversation')
            if updated:
                db.session.commit()
                print(f"    Seeded prompts: {', '.join(updated)}")

    print("\nDone! All KultureKool topics are ready.")


if __name__ == '__main__':
    main()
