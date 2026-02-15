"""CLI utility to create educators and their custom topics.

Usage:
    python create_educator.py create "greenwood" "Greenwood International School" --hindi "ग्रीनवुड स्कूल" --color "#059669"
    python create_educator.py add-topic "greenwood" "school_trip" "My School Trip" "Talk about our school trip!" --focus "..." --vocab '["चिड़ियाघर","शेर"]' --icon "🚌"
    python create_educator.py list
    python create_educator.py list-topics "greenwood"
"""

import argparse
import json
import sys
import os

# Setup Flask app context for DB access
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app
from models import db, Educator, EducatorTopic


def create_educator(args):
    with app.app_context():
        existing = Educator.query.filter_by(short_code=args.code).first()
        if existing:
            print(f"Error: Educator with code '{args.code}' already exists (id={existing.id})")
            sys.exit(1)

        educator = Educator(
            short_code=args.code.lower().strip(),
            name=args.name,
            display_name_hindi=args.hindi,
            logo_url=args.logo,
            brand_color=args.color or '#4F46E5',
        )
        db.session.add(educator)
        db.session.commit()
        print(f"Created educator: {educator.name} (code: {educator.short_code}, id: {educator.id})")


def add_topic(args):
    with app.app_context():
        educator = Educator.query.filter_by(short_code=args.code).first()
        if not educator:
            print(f"Error: No educator found with code '{args.code}'")
            sys.exit(1)

        existing = EducatorTopic.query.filter_by(
            educator_id=educator.id, topic_key=args.topic_key
        ).first()
        if existing:
            print(f"Error: Topic '{args.topic_key}' already exists for educator '{args.code}'")
            sys.exit(1)

        # Validate vocab JSON if provided
        vocab = None
        if args.vocab:
            try:
                vocab_list = json.loads(args.vocab)
                if not isinstance(vocab_list, list):
                    raise ValueError("Must be a JSON array")
                vocab = args.vocab
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error: Invalid vocab JSON: {e}")
                sys.exit(1)

        # Determine display_order
        max_order = db.session.query(db.func.max(EducatorTopic.display_order)).filter_by(
            educator_id=educator.id
        ).scalar() or 0

        topic = EducatorTopic(
            educator_id=educator.id,
            topic_key=args.topic_key,
            name=args.name,
            name_hindi=args.name_hindi,
            description=args.description,
            icon=args.icon or '📚',
            topic_focus=args.focus,
            key_vocabulary=vocab,
            display_order=max_order + 1,
        )
        db.session.add(topic)
        db.session.commit()
        print(f"Added topic: {topic.name} (key: {topic.full_key})")


def list_educators(args):
    with app.app_context():
        educators = Educator.query.all()
        if not educators:
            print("No educators found.")
            return
        for e in educators:
            status = "active" if e.is_active else "INACTIVE"
            topics_count = EducatorTopic.query.filter_by(educator_id=e.id).count()
            print(f"  [{e.id}] {e.short_code} - {e.name} ({topics_count} topics) [{status}]")


def list_topics(args):
    with app.app_context():
        educator = Educator.query.filter_by(short_code=args.code).first()
        if not educator:
            print(f"Error: No educator found with code '{args.code}'")
            sys.exit(1)

        topics = EducatorTopic.query.filter_by(educator_id=educator.id).order_by(
            EducatorTopic.display_order
        ).all()

        print(f"Topics for {educator.name} ({educator.short_code}):")
        if not topics:
            print("  (none)")
            return
        for t in topics:
            status = "active" if t.is_active else "INACTIVE"
            print(f"  {t.icon} {t.full_key} - {t.name} [{status}]")


def main():
    parser = argparse.ArgumentParser(description="Manage educators and custom topics")
    subparsers = parser.add_subparsers(dest='command', required=True)

    # create
    p_create = subparsers.add_parser('create', help='Create a new educator')
    p_create.add_argument('code', help='Short code (e.g. "greenwood")')
    p_create.add_argument('name', help='Display name (English)')
    p_create.add_argument('--hindi', help='Hindi display name', default=None)
    p_create.add_argument('--logo', help='Logo URL', default=None)
    p_create.add_argument('--color', help='Brand color hex (default: #4F46E5)', default='#4F46E5')
    p_create.set_defaults(func=create_educator)

    # add-topic
    p_topic = subparsers.add_parser('add-topic', help='Add a topic to an educator')
    p_topic.add_argument('code', help='Educator short code')
    p_topic.add_argument('topic_key', help='Topic slug (e.g. "school_trip")')
    p_topic.add_argument('name', help='Topic display name (English)')
    p_topic.add_argument('description', help='Card description text')
    p_topic.add_argument('--focus', required=True, help='Topic focus prompt text')
    p_topic.add_argument('--name-hindi', help='Hindi topic name', default=None)
    p_topic.add_argument('--vocab', help='JSON array of key vocabulary', default=None)
    p_topic.add_argument('--icon', help='Emoji icon (default: 📚)', default='📚')
    p_topic.set_defaults(func=add_topic)

    # list
    p_list = subparsers.add_parser('list', help='List all educators')
    p_list.set_defaults(func=list_educators)

    # list-topics
    p_lt = subparsers.add_parser('list-topics', help='List topics for an educator')
    p_lt.add_argument('code', help='Educator short code')
    p_lt.set_defaults(func=list_topics)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
