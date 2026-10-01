import socket
import ipaddress
import threading
from collections import defaultdict

# استخدم نفس نطاق شبكتك
NETWORK = "192.168.100.0/24"
TIMEOUT = 0.3
RESULTS = defaultdict(list)
LOCK = threading.Lock()

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
    
    print("\n" + "="*60)
    print("📊 Scan Results:")
    print("="*60)
    
    if not RESULTS:
        print("❌ No devices found!")
        return None
    
    print(f"Found {len(RESULTS)} device(s):\n")
    
    for idx, (ip, ports) in enumerate(sorted(RESULTS.items()), 1):
        print(f"{idx}. IP: {ip}")
        print(f"   Open Ports: {ports}")
        
        # تخمين نوع الجهاز
        if 554 in ports or 8554 in ports:
            print(f"   Likely: 🎥 Camera (RTSP port)")
        if 80 in ports or 8080 in ports:
            print(f"   Likely: 🌐 Web Server")
        print()
    
    return RESULTS

if __name__ == "__main__":
    results = scan_network()
    
    if results:
        print("\n" + "="*60)
        print("Next steps:")
        print("="*60)
        print("\nFor each device, try:")
        print("1. http://IP (or http://IP:8080)")
        print("2. rtsp://admin:admin@IP:554/stream1")
        print("3. rtsp://admin:123456@IP:554/stream1")
        print("\nRun: python test_rtsp.py <IP>")
        print("="*60)
