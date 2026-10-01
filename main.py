from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from typing import Optional

import cv2
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
    QGroupBox,
)


SETTINGS_FILE = "camera_list.json"


@dataclass
class CameraConfig:
    name: str
    url: str


class CameraStreamThread(threading.Thread):
    def __init__(self, url: str, callback):
        super().__init__(daemon=True)
        self.url = url
        self.callback = callback
        self.stop_event = threading.Event()
        self.cap = None

    def run(self):
        self.cap = cv2.VideoCapture(self.url)
        if not self.cap.isOpened():
            self.callback({"error": "فشل فتح الكاميرا. تأكد من عنوان RTSP صحيح."})
            return

        while not self.stop_event.is_set():
            ret, frame = self.cap.read()
            if not ret:
                self.callback({"error": "تم فقد الاتصال بالكاميرا."})
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            self.callback({"image": qimg})
            time.sleep(0.033)

        if self.cap:
            self.cap.release()

    def stop(self):
        self.stop_event.set()


class CameraMonitorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Camera Monitor Simple")
        self.resize(1100, 700)

        self.cameras: list[CameraConfig] = []
        self.current_stream: Optional[CameraStreamThread] = None

        self.setup_ui()
        self.load_cameras()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        top_box = QGroupBox("إضافة كاميرا")
        top_layout = QHBoxLayout(top_box)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("اسم الكاميرا")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("rtsp://admin:password@192.168.1.10:554/stream1")

        add_btn = QPushButton("إضافة")
        add_btn.clicked.connect(self.add_camera)

        top_layout.addWidget(self.name_input)
        top_layout.addWidget(self.url_input)
        top_layout.addWidget(add_btn)

        main_layout.addWidget(top_box)

        content_layout = QHBoxLayout()

        left_box = QGroupBox("قائمة الكاميرات")
        left_layout = QVBoxLayout(left_box)

        self.camera_list = QListWidget()
        self.camera_list.itemClicked.connect(self.select_camera)
        left_layout.addWidget(self.camera_list)

        remove_btn = QPushButton("حذف الكاميرا")
        remove_btn.clicked.connect(self.remove_selected_camera)
        left_layout.addWidget(remove_btn)

        content_layout.addWidget(left_box)

        right_box = QGroupBox("العرض المباشر")
        right_layout = QVBoxLayout(right_box)

        self.video_label = QLabel("لا توجد كاميرا مفتوحة")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #111; color: #fff; min-height: 500px;")
        right_layout.addWidget(self.video_label)

        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumHeight(150)
        self.status_box.setPlainText("جاهز\nملاحظة: يعمل فقط إذا كانت الكاميرا توفر RTSP أو ONVIF مباشرة.")
        right_layout.addWidget(self.status_box)

        open_btn = QPushButton("فتح الكاميرا")
        open_btn.clicked.connect(self.open_selected_camera)
        right_layout.addWidget(open_btn)

        stop_btn = QPushButton("إيقاف")
        stop_btn.clicked.connect(self.stop_stream)
        right_layout.addWidget(stop_btn)

        content_layout.addWidget(right_box)
        main_layout.addLayout(content_layout)

        self.setLayout(main_layout)

    def add_camera(self):
        name = self.name_input.text().strip()
        url = self.url_input.text().strip()

        if not name or not url:
            QMessageBox.warning(self, "تحذير", "أدخل اسم الكاميرا ورابط RTSP.")
            return

        self.cameras.append(CameraConfig(name=name, url=url))
        self.save_cameras()
        self.refresh_camera_list()
        self.name_input.clear()
        self.url_input.clear()

    def save_cameras(self):
        payload = [asdict(item) for item in self.cameras]
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load_cameras(self):
        if not os.path.exists(SETTINGS_FILE):
            default = [
                CameraConfig("Camera 1", "rtsp://admin:password@192.168.1.10:554/stream1"),
            ]
            self.cameras = default
            self.save_cameras()
        else:
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self.cameras = [CameraConfig(**item) for item in raw]
            except Exception:
                self.cameras = []

        self.refresh_camera_list()

    def refresh_camera_list(self):
        self.camera_list.clear()
        for camera in self.cameras:
            item = QListWidgetItem(f"{camera.name} - {camera.url}")
            self.camera_list.addItem(item)

    def select_camera(self, item):
        self.status_box.append("تم اختيار: " + item.text())

    def get_selected_camera(self):
        current_row = self.camera_list.currentRow()
        if current_row < 0:
            return None
        return self.cameras[current_row]

    def open_selected_camera(self):
        camera = self.get_selected_camera()
        if not camera:
            QMessageBox.warning(self, "تحذير", "اختر كاميرا أولاً.")
            return

        self.status_box.append(f"فتح: {camera.name} -> {camera.url}")
        self.stop_stream()

        def on_frame(data):
            if "error" in data:
                self.status_box.append(data["error"])
                self.video_label.setText(data["error"])
                return

            if "image" in data:
                image = data["image"]
                pixmap = QPixmap.fromImage(image)
                self.video_label.setPixmap(pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio))

        self.current_stream = CameraStreamThread(camera.url, on_frame)
        self.current_stream.start()

    def stop_stream(self):
        if self.current_stream:
            self.current_stream.stop()
            self.current_stream = None
        self.video_label.setText("لا توجد كاميرا مفتوحة")
        self.video_label.setPixmap(QPixmap())

    def remove_selected_camera(self):
        row = self.camera_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تحذير", "اختر كاميرا للحذف.")
            return

        del self.cameras[row]
        self.save_cameras()
        self.refresh_camera_list()


if __name__ == "__main__":
    app = QApplication([])
    window = CameraMonitorApp()
    window.show()
    app.exec_()
