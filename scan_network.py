import socket
import ipaddress
import threading
import subprocess
import sys
import os
from collections import defaultdict
from datetime import datetime

# استخدم نفس نطاق شبكتك
NETWORK = "192.168.100.0/24"
TIMEOUT = 0.2
RESULTS = defaultdict(list)
LOCK = threading.Lock()
OUTPUT_FILE = "camera_scan_results.txt"

def check_port(ip, port):
    """فحص إذا المنفذ مفتوح"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        result = s.connect_ex((ip, port))
        return result == 0
    except:
        return False
    finally:
        s.close()

def scan_device(ip):
    """فحص جهاز واحد"""
    ip = str(ip)
    open_ports = []
    
    # فحص المنافذ الشائعة للكاميرات
    common_ports = [80, 554, 8000, 8080, 8554, 443, 8443]
    
    for port in common_ports:
        if check_port(ip, port):
            open_ports.append(port)
    
    if open_ports:
        with LOCK:
            RESULTS[ip] = open_ports
            print(f"✅ Found device: {ip} | Open ports: {open_ports}")

def scan_network():
    """فحص الشبكة كاملة"""
    print(f"🔍 Scanning network: {NETWORK}")
    print("Please wait...\n")
    
    network = ipaddress.ip_network(NETWORK)
    threads = []
    
    for ip in network.hosts():
        t = threading.Thread(target=scan_device, args=(ip,))
        t.daemon = True
        threads.append(t)
        t.start()
    
    # انتظر انتهاء جميع threads
    for t in threads:
        t.join()
    
    return RESULTS

def save_results_to_file(results):
    """حفظ النتائج إلى ملف"""
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write(f"📊 Network Scan Results\n")
        f.write(f"Network: {NETWORK}\n")
        f.write(f"Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*70 + "\n\n")
        
        if not results:
            f.write("❌ No devices found!\n")
            return
        
        f.write(f"Found {len(results)} device(s):\n\n")
        
        for idx, (ip, ports) in enumerate(sorted(results.items()), 1):
            f.write(f"{idx}. IP Address: {ip}\n")
            f.write(f"   Open Ports: {', '.join(map(str, ports))}\n")
            
            # تخمين نوع الجهاز
            device_type = []
            if 554 in ports or 8554 in ports:
                device_type.append("🎥 Camera (RTSP)")
            if 80 in ports or 8080 in ports:
                device_type.append("🌐 Web Server")
            if 443 in ports or 8443 in ports:
                device_type.append("🔒 HTTPS Server")
            
            if device_type:
                f.write(f"   Type: {', '.join(device_type)}\n")
            f.write("\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("Next Steps:\n")
        f.write("="*70 + "\n")
        f.write("1. For web cameras:\n")
        f.write("   - Try: http://IP or http://IP:8080 in browser\n\n")
        f.write("2. For RTSP cameras:\n")
        f.write("   - Run: python test_rtsp.py <IP>\n")
        f.write("   - Example: python test_rtsp.py 192.168.100.50\n\n")
        f.write("3. Common RTSP URLs to try:\n")
        f.write("   - rtsp://admin:admin@IP:554/stream1\n")
        f.write("   - rtsp://admin:123456@IP:554/stream1\n")
        f.write("   - rtsp://admin:admin@IP:554/ch0\n")
        f.write("="*70 + "\n")

def open_file_in_explorer():
    """فتح الملف في explorer"""
    try:
        if sys.platform == 'win32':
            os.startfile(OUTPUT_FILE)
        elif sys.platform == 'darwin':  # macOS
            subprocess.run(['open', OUTPUT_FILE])
        else:  # Linux
            subprocess.run(['xdg-open', OUTPUT_FILE])
        return True
    except Exception as e:
        print(f"❌ Error opening file: {e}")
        return False

def main():
    print("\n" + "="*70)
    print("🎥 CAMERA NETWORK SCANNER")
    print("="*70 + "\n")
    
    # اختبر الاتصال بالشبكة أولاً
    try:
        socket.gethostbyname(socket.gethostname())
    except Exception as e:
        print(f"❌ Network error: {e}")
        return
    
    # فحص الشبكة
    results = scan_network()
    
    # حفظ النتائج
    print("\n" + "="*70)
    print("💾 Saving results to file...")
    print("="*70)
    save_results_to_file(results)
    print(f"✅ Results saved to: {OUTPUT_FILE}\n")
    
    # فتح الملف
    print("📂 Opening file...")
    if open_file_in_explorer():
        print(f"✅ File opened: {OUTPUT_FILE}")
    else:
        print(f"⚠️ You can open it manually: {OUTPUT_FILE}")
    
    print("\n" + "="*70)
    print("✨ Scan completed!")
    print("="*70)

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
