"""测试 TTS 修复"""
import sys
import time

# 添加 src 到路径
sys.path.insert(0, 'e:/qoder/Translate-Copilot/src')

from utils.tts import get_tts, TTSState

def test_tts():
    tts = get_tts()
    
    print(f"Backend: {tts._backend}")
    print(f"Available: {tts.is_available()}")
    print(f"Initial state: {tts.get_state()}")
    
    # 测试1: 开始朗读
    print("\n--- Test 1: Start speaking ---")
    result = tts.speak("Hello, this is a test.")
    print(f"speak() returned: {result}")
    print(f"is_speaking: {tts.is_speaking()}")
    
    # 等待一会儿让朗读开始
    time.sleep(0.5)
    print(f"After 0.5s, is_speaking: {tts.is_speaking()}")
    
    # 等待完成
    print("Waiting for completion...")
    timeout = 10
    start = time.time()
    while tts.is_speaking() and (time.time() - start) < timeout:
        time.sleep(0.1)
    
    if tts.is_speaking():
        print("ERROR: Timeout! State still SPEAKING")
    else:
        print(f"Completed! State: {tts.get_state()}")
    
    # 测试2: 再次朗读
    print("\n--- Test 2: Speak again after completion ---")
    result = tts.speak("Second test message.")
    print(f"speak() returned: {result}")
    print(f"is_speaking: {tts.is_speaking()}")
    
    # 等待完成
    timeout = 10
    start = time.time()
    while tts.is_speaking() and (time.time() - start) < timeout:
        time.sleep(0.1)
    
    print(f"Final state: {tts.get_state()}")
    
    # 测试3: 朗读中途停止
    print("\n--- Test 3: Stop while speaking ---")
    result = tts.speak("This is a longer message that should be stopped in the middle of speaking.")
    print(f"speak() returned: {result}")
    time.sleep(0.5)
    print(f"is_speaking before stop: {tts.is_speaking()}")
    
    if tts.is_speaking():
        print("Calling stop()...")
        tts.stop()
        time.sleep(0.3)
        print(f"is_speaking after stop: {tts.is_speaking()}")
    
    # 测试4: 停止后再次朗读
    print("\n--- Test 4: Speak after stop ---")
    result = tts.speak("This should work after stopping.")
    print(f"speak() returned: {result}")
    print(f"is_speaking: {tts.is_speaking()}")
    
    timeout = 10
    start = time.time()
    while tts.is_speaking() and (time.time() - start) < timeout:
        time.sleep(0.1)
    
    print(f"Final state: {tts.get_state()}")
    
    print("\n=== All tests completed ===")

if __name__ == "__main__":
    test_tts()