import os
import base64
import logging
import concurrent.futures
from datetime import datetime

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)

# Configuration from environment
AWS_S3_BUCKET = os.environ.get('AWS_S3_BUCKET', '')
AWS_S3_REGION = os.environ.get('AWS_S3_REGION', 'ap-south-1')
ENABLE_AUDIO_STORAGE = os.environ.get('ENABLE_AUDIO_STORAGE', 'false').lower() == 'true'

# Lazy-initialized S3 client
_s3_client = None

# Background executor for async uploads
_upload_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def get_s3_client():
    """Get or create a lazy-initialized boto3 S3 client with retry config."""
    global _s3_client
    if _s3_client is None:
        boto_config = BotoConfig(
            region_name=AWS_S3_REGION,
            retries={'max_attempts': 3, 'mode': 'standard'}
        )
        _s3_client = boto3.client('s3', config=boto_config)
    return _s3_client


def generate_s3_key(user_id, conversation_id, turn_index, role, audio_format='webm'):
    """Generate an S3 object key for an audio file.

    Returns a key like: audio/2026/02/42/187/001_user.webm
    """
    now = datetime.utcnow()
    return (
        f"audio/{now.year}/{now.month:02d}/"
        f"{user_id}/{conversation_id}/"
        f"{turn_index:03d}_{role}.{audio_format}"
    )


def upload_audio_bytes(audio_bytes, s3_key, content_type='audio/webm'):
    """Upload raw audio bytes to S3. Returns the s3_key on success."""
    client = get_s3_client()
    client.put_object(
        Bucket=AWS_S3_BUCKET,
        Key=s3_key,
        Body=audio_bytes,
        ContentType=content_type,
    )
    logger.info(f"S3 upload complete: {s3_key} ({len(audio_bytes)} bytes)")
    return s3_key


def upload_base64_audio(base64_string, s3_key, content_type='audio/webm'):
    """Decode base64 audio and upload to S3. Ready for Phase 2 TTS uploads."""
    audio_bytes = base64.b64decode(base64_string)
    return upload_audio_bytes(audio_bytes, s3_key, content_type)


def generate_presigned_url(s3_key, expiration=3600):
    """Generate a presigned URL for audio playback (default 1 hour)."""
    client = get_s3_client()
    url = client.generate_presigned_url(
        'get_object',
        Params={'Bucket': AWS_S3_BUCKET, 'Key': s3_key},
        ExpiresIn=expiration,
    )
    return url


def upload_audio_async(app, audio_bytes, user_id, conversation_id, turn_index,
                       role='user', audio_format='webm', content_type='audio/webm'):
    """Submit an audio upload to the background thread pool.

    Creates a ConversationAudio DB record with status tracking:
    pending -> uploaded / failed.
    """
    if not ENABLE_AUDIO_STORAGE:
        return

    s3_key = generate_s3_key(user_id, conversation_id, turn_index, role, audio_format)
    file_size = len(audio_bytes)

    # Create pending DB record inside app context
    from models import db, ConversationAudio
    with app.app_context():
        record = ConversationAudio(
            conversation_id=conversation_id,
            turn_index=turn_index,
            role=role,
            s3_key=s3_key,
            audio_format=audio_format,
            file_size_bytes=file_size,
            upload_status='pending',
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id

    def _do_upload():
        with app.app_context():
            try:
                upload_audio_bytes(audio_bytes, s3_key, content_type)
                rec = ConversationAudio.query.get(record_id)
                if rec:
                    rec.upload_status = 'uploaded'
                    db.session.commit()
                logger.info(f"Background upload succeeded: {s3_key}")
            except Exception as e:
                logger.error(f"Background upload failed for {s3_key}: {e}")
                try:
                    rec = ConversationAudio.query.get(record_id)
                    if rec:
                        rec.upload_status = 'failed'
                        db.session.commit()
                except Exception:
                    logger.error("Failed to update upload_status to 'failed'")

    _upload_executor.submit(_do_upload)
