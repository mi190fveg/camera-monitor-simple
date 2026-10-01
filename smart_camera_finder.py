import cv2
import socket
import ipaddress
import threading
import subprocess
import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QListWidget, QListWidgetItem, QMessageBox,
    QGroupBox, QProgressBar, QSpinBox
)

NETWORK = "192.168.100.0/24"
TIMEOUT = 0.2
DOWNLOADS = str(Path.home() / "Downloads")


class ScannerThread(QThread):
    found_device = pyqtSignal(str, list)
    scan_finished = pyqtSignal(dict)
    status_update = pyqtSignal(str)

    def run(self):
        self.status_update.emit("🔍 Scanning network...")
        devices = defaultdict(list)
        network = ipaddress.ip_network(NETWORK)

        threads = []
        for ip in network.hosts():
            t = threading.Thread(target=self.check_device, args=(ip, devices))
            t.daemon = True
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.scan_finished.emit(dict(devices))
        self.status_update.emit("✅ Scan finished!")

    def check_device(self, ip, devices):
        ip = str(ip)
        open_ports = []

        for port in [80, 554, 8000, 8080, 8554, 443]:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)
            try:
                result = s.connect_ex((ip, port))
                if result == 0:
                    open_ports.append(port)
            except Exception:
                pass
            finally:
                s.close()

        if open_ports:
            devices[ip] = open_ports
            self.found_device.emit(ip, open_ports)


class RTSPTestThread(QThread):
    rtsp_found = pyqtSignal(str)
    rtsp_failed = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, ip):
        super().__init__()
        self.ip = ip

    def run(self):
        rtsp_urls = [
            f"rtsp://admin:admin@{self.ip}:554/stream1",
            f"rtsp://admin:admin@{self.ip}:554/ch0",
            f"rtsp://admin:123456@{self.ip}:554/stream1",
            f"rtsp://admin:123456@{self.ip}:554/ch0",
            f"rtsp://admin:password@{self.ip}:554/stream1",
            f"rtsp://user:user@{self.ip}:554/stream1",
            f"rtsp://admin:admin@{self.ip}:8554/stream1",
        ]

        for url in rtsp_urls:
            self.status_update.emit(f"Testing: {url}")
            cap = cv2.VideoCapture(url)
            if cap.isOpened():
                cap.release()
                self.rtsp_found.emit(url)
                return
            cap.release()

        self.rtsp_failed.emit(f"No RTSP stream found on {self.ip}")


class PortForwardingThread(QThread):
    status_update = pyqtSignal(str)
    success = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, ip, external_port, internal_port, action):
        super().__init__()
        self.ip = ip
        self.external_port = external_port
        self.internal_port = internal_port
        self.action = action

    def run(self):
        try:
            if self.action == "add":
                self.status_update.emit(f"Adding port forward: {self.external_port} -> {self.ip}:{self.internal_port}")
                result = subprocess.run(
                    [
                        "netsh", "interface", "portproxy", "add", "v4tov4",
                        f"listenport={self.external_port}",
                        f"connectaddress={self.ip}",
                        f"connectport={self.internal_port}"
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    self.success.emit(f"✅ Port forward added: {self.external_port} -> {self.ip}:{self.internal_port}")
                else:
                    self.failed.emit(f"Error: {result.stderr.strip() or result.stdout.strip()}")
            elif self.action == "remove":
                self.status_update.emit(f"Removing port forward: {self.external_port}")
                result = subprocess.run(
                    [
                        "netsh", "interface", "portproxy", "delete", "v4tov4",
                        f"listenport={self.external_port}"
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    self.success.emit(f"✅ Port forward removed: {self.external_port}")
                else:
                    self.failed.emit(f"Error: {result.stderr.strip() or result.stdout.strip()}")
        except Exception as e:
            self.failed.emit(f"Error: {str(e)}")


class CameraApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎥 Smart Camera Finder")
        self.resize(1200, 780)
        self.setStyleSheet("background-color: #1c1c1c; color: white;")
        self.devices = {}
        self.selected_ip = None
        self.current_rtsp_url = None

        self.setup_ui()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)

        left_box = QGroupBox("🔍 Network Scan")
        left_layout = QVBoxLayout(left_box)

        self.scan_btn = QPushButton("Start Scan")
        self.scan_btn.clicked.connect(self.start_scan)
        self.scan_btn.setStyleSheet("background-color: #0078d4; color: white; padding: 10px;")
        left_layout.addWidget(self.scan_btn)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #6ee7b7; font-weight: bold;")
        left_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        left_layout.addWidget(self.progress_bar)

        self.device_list = QListWidget()
        self.device_list.itemClicked.connect(self.on_device_selected)
        left_layout.addWidget(QLabel("Devices Found:"))
        left_layout.addWidget(self.device_list)

        main_layout.addWidget(left_box, 1)

        middle_box = QGroupBox("📹 Camera Test")
        middle_layout = QVBoxLayout(middle_box)

        self.test_btn = QPushButton("Test RTSP")
        self.test_btn.clicked.connect(self.test_rtsp)
        self.test_btn.setStyleSheet("background-color: #0f9d58; color: white; padding: 10px;")
        middle_layout.addWidget(self.test_btn)

        self.rtsp_url_label = QLabel("No camera found")
        self.rtsp_url_label.setStyleSheet("background-color: #2d2d2d; padding: 8px; border-radius: 6px;")
        middle_layout.addWidget(self.rtsp_url_label)

        self.open_btn = QPushButton("Open Camera")
        self.open_btn.clicked.connect(self.open_camera)
        self.open_btn.setStyleSheet("background-color: #8b5cf6; color: white; padding: 10px;")
        middle_layout.addWidget(self.open_btn)

        self.video_label = QLabel("No video")
        self.video_label.setAlignment(__import__('PyQt5.QtCore').Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #000; min-height: 300px; border: 1px solid #444;")
        middle_layout.addWidget(self.video_label)

        main_layout.addWidget(middle_box, 2)

        right_box = QGroupBox("🌐 Port Forwarding")
        right_layout = QVBoxLayout(right_box)

        right_layout.addWidget(QLabel("External Port:"))
        self.ext_port = QSpinBox()
        self.ext_port.setRange(1, 65535)
        self.ext_port.setValue(8554)
        right_layout.addWidget(self.ext_port)

        right_layout.addWidget(QLabel("Internal Port:"))
        self.int_port = QSpinBox()
        self.int_port.setRange(1, 65535)
        self.int_port.setValue(554)
        right_layout.addWidget(self.int_port)

        self.add_pf_btn = QPushButton("Add Port Forward")
        self.add_pf_btn.clicked.connect(self.add_port_forward)
        self.add_pf_btn.setStyleSheet("background-color: #10b981; color: white; padding: 8px;")
        right_layout.addWidget(self.add_pf_btn)

        self.pf_list = QListWidget()
        right_layout.addWidget(self.pf_list)

        self.remove_pf_btn = QPushButton("Remove Selected")
        self.remove_pf_btn.clicked.connect(self.remove_port_forward)
        self.remove_pf_btn.setStyleSheet("background-color: #ef4444; color: white; padding: 8px;")
        right_layout.addWidget(self.remove_pf_btn)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: #151515; color: #b7f7d0;")
        self.log_area.setMaximumHeight(180)
        right_layout.addWidget(QLabel("Log:"))
        right_layout.addWidget(self.log_area)

        main_layout.addWidget(right_box, 1)
        self.setLayout(main_layout)

    def log(self, msg):
        self.log_area.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def start_scan(self):
        self.scan_btn.setEnabled(False)
        self.device_list.clear()
        self.devices.clear()
        self.log("Scanning network...")

        self.scanner = ScannerThread()
        self.scanner.found_device.connect(self.on_device_found)
        self.scanner.scan_finished.connect(self.on_scan_done)
        self.scanner.status_update.connect(self.status_label.setText)
        self.scanner.start()

    def on_device_found(self, ip, ports):
        self.devices[ip] = ports
        self.device_list.addItem(f"{ip} | Ports: {ports}")
        self.log(f"Found device: {ip} | {ports}")

    def on_scan_done(self, devices):
        self.scan_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.log(f"Scan complete. Found {len(devices)} device(s).")

    def on_device_selected(self, item):
        self.selected_ip = item.text().split(" |")[0]
        self.log(f"Selected device: {self.selected_ip}")

    def test_rtsp(self):
        if not self.selected_ip:
            QMessageBox.warning(self, "Warning", "Select a device first.")
            return

        self.test_btn.setEnabled(False)
        self.log(f"Testing RTSP on {self.selected_ip}...")
        self.rtsp_thread = RTSPTestThread(self.selected_ip)
        self.rtsp_thread.rtsp_found.connect(self.on_rtsp_found)
        self.rtsp_thread.rtsp_failed.connect(self.on_rtsp_failed)
        self.rtsp_thread.status_update.connect(self.log)
        self.rtsp_thread.start()

    def on_rtsp_found(self, url):
        self.current_rtsp_url = url
        self.rtsp_url_label.setText(url)
        self.log(f"RTSP stream detected: {url}")
        self.test_btn.setEnabled(True)
        QMessageBox.information(self, "Success", f"Camera Found!\n{url}")

    def on_rtsp_failed(self, msg):
        self.test_btn.setEnabled(True)
        self.log(msg)
        QMessageBox.warning(self, "Failed", msg)

    def open_camera(self):
        if not self.current_rtsp_url:
            QMessageBox.warning(self, "Warning", "No RTSP URL available yet.")
            return

        cap = cv2.VideoCapture(self.current_rtsp_url)
        if not cap.isOpened():
            QMessageBox.warning(self, "Error", "Cannot open the camera stream.")
            self.log("Cannot open the camera stream.")
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                self.log("Stream disconnected.")
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img)
            self.video_label.setPixmap(pixmap.scaled(self.video_label.size(), __import__('PyQt5.QtCore').Qt.KeepAspectRatio))

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        self.log("Camera stream closed.")

    def add_port_forward(self):
        if not self.selected_ip:
            QMessageBox.warning(self, "Warning", "Select a device first.")
            return

        ext_port = self.ext_port.value()
        int_port = self.int_port.value()

        self.pf_thread = PortForwardingThread(self.selected_ip, ext_port, int_port, "add")
        self.pf_thread.success.connect(self.on_pf_success)
        self.pf_thread.failed.connect(self.on_pf_failed)
        self.pf_thread.status_update.connect(self.log)
        self.pf_thread.start()

    def on_pf_success(self, msg):
        self.log(msg)
        self.pf_list.addItem(msg)
        QMessageBox.information(self, "Success", msg)

    def on_pf_failed(self, msg):
        self.log(msg)
        QMessageBox.warning(self, "Error", msg)

    def remove_port_forward(self):
        item = self.pf_list.currentItem()
        if item is None:
            QMessageBox.warning(self, "Warning", "Select a port forward entry first.")
            return

        text = item.text()
        if "->" in text:
            ext_port = text.split("->")[0].split(":")[-1].strip()
            try:
                port = int(ext_port)
            except ValueError:
                QMessageBox.warning(self, "Warning", "Could not parse port number.")
                return

            self.remove_thread = PortForwardingThread(None, port, None, "remove")
            self.remove_thread.success.connect(self.on_pf_removed)
            self.remove_thread.failed.connect(self.on_pf_failed)
            self.remove_thread.start()

    def on_pf_removed(self, msg):
        self.log(msg)
        for i in range(self.pf_list.count()):
            if self.pf_list.item(i).text().startswith(msg.split(':')[0]):
                self.pf_list.takeItem(i)
                break
        QMessageBox.information(self, "Success", msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CameraApp()
    window.show()
    sys.exit(app.exec_())
