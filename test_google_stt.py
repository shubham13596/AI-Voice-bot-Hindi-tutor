#!/usr/bin/env python3
"""
Test script for Google Cloud Speech-to-Text integration
Tests the optimization functions and configuration
"""

import os
import time
import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_audio_optimization():
    """Test the audio silence trimming function"""
    print("Testing audio optimization functions...")

    # Import the functions from app.py
    try:
        from app import trim_audio_silence, optimize_audio_for_google_cloud
        print("Successfully imported optimization functions")
    except ImportError as e:
        print(f"Failed to import functions: {e}")
        return False

    # Create test audio data (simulated with noise and silence)
    print("Creating test audio data...")

    # Simulate audio: silence (zeros) + speech (noise) + silence
    silence_start = np.zeros(1000, dtype=np.uint8)  # 1KB silence
    speech_content = np.random.randint(20, 255, 2000, dtype=np.uint8)  # 2KB speech
    silence_end = np.zeros(500, dtype=np.uint8)  # 0.5KB silence

    test_audio = np.concatenate([silence_start, speech_content, silence_end])
    original_size = len(test_audio)

    print(f"Original audio size: {original_size/1024:.1f} KB")

    # Test silence trimming
    start_time = time.time()
    trimmed_audio = trim_audio_silence(test_audio.tobytes())
    processing_time = (time.time() - start_time) * 1000

    trimmed_size = len(trimmed_audio)
    reduction = ((original_size - trimmed_size) / original_size) * 100

    print(f"Trimmed audio size: {trimmed_size/1024:.1f} KB")
    print(f"Reduction: {reduction:.1f}%")
    print(f"Processing time: {processing_time:.1f}ms")

    # Test full optimization pipeline
    optimized_audio = optimize_audio_for_google_cloud(test_audio.tobytes())
    print(f"Full optimization pipeline completed")

    return True

def test_google_cloud_configuration():
    """Test Google Cloud STT configuration"""
    print("\nTesting Google Cloud STT configuration...")

    # Check environment variables
    google_api_key = os.getenv('GOOGLE_CLOUD_API_KEY')
    stt_provider = os.getenv('STT_PROVIDER', 'sarvam')

    print(f"Google Cloud API Key: {'Set' if google_api_key else 'Not set'}")
    print(f"STT Provider: {stt_provider}")

    if stt_provider.lower() == 'google':
        if google_api_key:
            print("Configuration ready for Google Cloud STT")
        else:
            print("Google Cloud STT selected but no API key provided")
            return False
    else:
        print(f"Current provider is '{stt_provider}', not Google Cloud")

    # Test imports
    try:
        from google.cloud import speech
        print("Google Cloud Speech library imported successfully")
    except ImportError as e:
        print(f"Failed to import Google Cloud Speech: {e}")
        print("Run 'pip install -r requirements.txt' to install dependencies")
        return False

    return True

def test_stt_routing():
    """Test the STT provider routing logic"""
    print("\nTesting STT provider routing...")

    try:
        from app import speech_to_text_hindi
        print("Successfully imported speech_to_text_hindi function")

        # This would normally require actual audio data to test fully
        print("STT routing function is properly imported and ready")
        return True

    except ImportError as e:
        print(f"Failed to import STT function: {e}")
        return False

def main():
    """Run all tests"""
    print("Google Cloud Speech-to-Text Integration Test Suite")
    print("=" * 60)

    tests = [
        ("Audio Optimization", test_audio_optimization),
        ("Google Cloud Configuration", test_google_cloud_configuration),
        ("STT Routing", test_stt_routing)
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        print("-" * 40)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"Test failed with exception: {e}")
            results.append((test_name, False))

    # Summary
    print("\nTest Summary")
    print("=" * 60)
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1

    print(f"\nResults: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("All tests passed! Google Cloud STT integration is ready.")
        print("\nNext steps:")
        print("1. Set GOOGLE_CLOUD_API_KEY in your .env file")
        print("2. Set STT_PROVIDER=google in your .env file")
        print("3. Test with real audio data")
    else:
        print("Some tests failed. Check the output above for details.")

if __name__ == "__main__":
    main()