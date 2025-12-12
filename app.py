"""
Streamlit shipment management system with analytics, filters, audit log,
exports, and mobile optimizations.
"""

from __future__ import annotations

import io
import sqlite3
from datetime import datetime, date
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import matplotlib.pyplot as plt

# Optional camera/QR dependencies
try:  # pragma: no cover - optional deps
    import av  # type: ignore
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    from pyzbar.pyzbar import decode  # type: ignore
    from streamlit_webrtc import WebRtcMode, webrtc_streamer  # type: ignore
except ImportError:  # pragma: no cover - optional deps
    av = cv2 = np = decode = webrtc_streamer = WebRtcMode = None


DB_PATH = "shipment.db"

# Trạng thái hiển thị theo luồng (giữ nguyên giá trị gốc, chỉ đổi giao diện)
STATUS_FLOW = [
    "Đang gửi",
    "Phiếu tạm",
    "Chuyển kho",
    "Đang xử lý",
    "Đã nhận",
    "Nhập kho",
    "Nhập kho xử lý",
    "Gửi NCC",
    "Hoàn thành chuyển SR",
    "Kết thúc",
    "Hư hỏng",
    "Mất",
]

# Mô tả ngắn cho từng trạng thái
STATUS_DESCRIPTIONS = {
    "Đang gửi": "Phiếu đã được tạo và đang chờ xử lý.",
    "Phiếu tạm": "Phiếu đang ở trạng thái nháp/tạm.",
    "Chuyển kho": "Đơn hàng đang trên đường di chuyển giữa các kho.",
    "Đang xử lý": "Đơn hàng đang được phân loại/xử lý tại kho.",
    "Đã nhận": "Kho đã nhận hàng, chờ các bước tiếp theo.",
    "Nhập kho": "Hàng đã nhập kho.",
    "Nhập kho xử lý": "Hàng đang được xử lý trong kho.",
    "Gửi NCC": "Hàng đã gửi đến nhà cung cấp.",
    "Hoàn thành chuyển SR": "Đã hoàn thành chuyển cửa hàng/SR.",
    "Kết thúc": "Đơn hàng đã hoàn tất/giao thành công.",
    "Hư hỏng": "Đơn gặp vấn đề hư hỏng.",
    "Mất": "Đơn hàng thất lạc, cần xử lý.",
}

# Nhãn hiển thị kiểu Shopee (chỉ đổi text trình bày)
STATUS_ALIASES = {
    "Kết thúc": "Đã giao",
    "Đã nhận": "Đã giao",
    "Chuyển kho": "Đang vận chuyển",
    "Đang xử lý": "Đang phân loại",
    "Nhập kho": "Đang nhập kho",
    "Nhập kho xử lý": "Đang nhập kho",
    "Gửi NCC": "Gửi nhà cung cấp",
    "Phiếu tạm": "Chờ xác nhận",
}


st.set_page_config(
    page_title="Quản Lý Giao Nhận",
    page_icon=None,
    layout="wide",
)


# -------------------- GLOBAL STYLES --------------------
st.markdown(
    """
    <style>
        /* Root Variables */
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #8b5cf6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-card: #1e293b;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --border: #334155;
            --shadow: rgba(0, 0, 0, 0.3);
        }
        
        /* Main Container */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }
        
        /* Typography */
        h1, h2, h3 {
            color: var(--text-primary) !important;
            font-weight: 700 !important;
            margin-bottom: 1rem !important;
        }
        
        h1 {
            font-size: 2.5rem !important;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        /* Cards */
        .card {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid var(--border);
            box-shadow: 0 4px 6px var(--shadow);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 12px var(--shadow);
        }
        
        /* Metrics Cards */
        .metric-card {
            background: linear-gradient(135deg, var(--bg-card), var(--bg-secondary));
            border-radius: 12px;
            padding: 1.25rem;
            text-align: center;
            border: 1px solid var(--border);
            box-shadow: 0 2px 4px var(--shadow);
        }
        
        .metric-card .metric-label {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
            font-weight: 500;
        }
        
        .metric-card .metric-value {
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-primary);
        }
        
        /* Buttons */
        .stButton > button {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: white;
            border: none;
            border-radius: 10px;
            padding: 0.75rem 1.5rem;
            font-weight: 600;
            font-size: 1rem;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px var(--shadow);
            width: 100%;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px var(--shadow);
            background: linear-gradient(135deg, var(--primary-dark), var(--primary));
        }
        
        .stButton > button:active {
            transform: translateY(0);
        }
        
        /* Primary Button */
        button[kind="primary"] {
            background: linear-gradient(135deg, var(--primary), var(--secondary)) !important;
        }
        
        /* Form Inputs */
        .stTextInput > div > div > input,
        .stSelectbox > div > div > select,
        .stTextArea > div > div > textarea {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 0.75rem;
            font-size: 1rem;
            transition: all 0.2s;
        }
        
        .stTextInput > div > div > input:focus,
        .stSelectbox > div > div > select:focus,
        .stTextArea > div > div > textarea:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
            outline: none;
        }
        
        /* Labels */
        label {
            color: var(--text-primary) !important;
            font-weight: 600 !important;
            font-size: 0.95rem !important;
            margin-bottom: 0.5rem !important;
        }
        
        /* Main Background */
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        }
        
        /* Sidebar */
        .css-1d391kg {
            background: var(--bg-primary) !important;
        }
        
        [data-testid="stSidebar"] {
            background: var(--bg-primary) !important;
            border-right: 1px solid var(--border);
        }
        
        [data-testid="stSidebar"] .css-1d391kg {
            background: var(--bg-primary) !important;
        }
        
        /* Main content area */
        .main .block-container {
            background: transparent;
        }
        
        /* Radio Buttons */
        .stRadio > div {
            background: var(--bg-card);
            border-radius: 10px;
            padding: 0.5rem;
            border: 1px solid var(--border);
        }
        
        .stRadio label {
            color: var(--text-primary) !important;
            font-weight: 500 !important;
        }
        
        /* Dataframe */
        .dataframe {
            background: var(--bg-card);
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--border);
        }
        
        /* Success/Error Messages */
        .stSuccess {
            background: rgba(16, 185, 129, 0.1);
            border-left: 4px solid var(--success);
            border-radius: 8px;
            padding: 1rem;
        }
        
        .stError {
            background: rgba(239, 68, 68, 0.1);
            border-left: 4px solid var(--danger);
            border-radius: 8px;
            padding: 1rem;
        }
        
        .stWarning {
            background: rgba(245, 158, 11, 0.1);
            border-left: 4px solid var(--warning);
            border-radius: 8px;
            padding: 1rem;
        }
        
        .stInfo {
            background: rgba(99, 102, 241, 0.1);
            border-left: 4px solid var(--primary);
            border-radius: 8px;
            padding: 1rem;
        }
        
        /* Divider */
        hr {
            border-color: var(--border);
            margin: 2rem 0;
        }
        
        /* Mobile Responsive */
        @media (max-width: 768px) {
            .main .block-container {
                padding: 1rem;
            }
            
            h1 {
                font-size: 1.75rem !important;
            }
            
            .metric-card {
                margin-bottom: 1rem;
            }
            
            .metric-card .metric-value {
                font-size: 1.5rem;
            }
            
            .stButton > button {
                padding: 1rem;
                font-size: 1rem;
            }
            
            [data-testid="column"] {
                margin-bottom: 1rem;
            }
            
            .card {
                padding: 1rem;
            }
        }
        
        /* Custom Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: var(--bg-secondary);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: var(--border);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--primary);
        }
        
        /* Camera Container */
        .camera-container {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 1.5rem;
            margin: 1rem 0;
            border: 1px solid var(--border);
            box-shadow: 0 4px 6px var(--shadow);
        }
        
        /* Modal/Popup Overlay */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 9999;
            animation: fadeIn 0.3s ease-out;
        }
        
        .modal-content {
            background: var(--bg-card);
            border-radius: 20px;
            padding: 2rem;
            max-width: 90%;
            max-height: 90vh;
            width: 600px;
            border: 1px solid var(--border);
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            position: relative;
            animation: slideUp 0.3s ease-out;
            overflow-y: auto;
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border);
        }
        
        .modal-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
            margin: 0;
        }
        
        .modal-close-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0.5rem;
            border-radius: 50%;
            transition: all 0.2s;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .modal-close-btn:hover {
            background: var(--bg-secondary);
            color: var(--text-primary);
        }
        
        .camera-wrapper {
            width: 100%;
            min-height: 400px;
            background: #000;
            border-radius: 12px;
            overflow: hidden;
            position: relative;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(50px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        /* Hide modal when not shown */
        .modal-hidden {
            display: none !important;
        }
        
        /* Status Badges */
        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.875rem;
            font-weight: 600;
        }
        
        .status-pending {
            background: rgba(245, 158, 11, 0.2);
            color: var(--warning);
        }
        
        .status-received {
            background: rgba(16, 185, 129, 0.2);
            color: var(--success);
        }
        
        .status-error {
            background: rgba(239, 68, 68, 0.2);
            color: var(--danger);
        }

        /* Shopee-style status card + timeline (UI only, không đổi trạng thái gốc) */
        .shopee-status-card {
            background: linear-gradient(120deg, rgba(99,102,241,0.15), rgba(139,92,246,0.08));
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1rem 1.25rem;
            margin: 0.5rem 0 1rem 0;
            box-shadow: 0 8px 16px rgba(0,0,0,0.15);
        }
        .shopee-status-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text-primary);
            margin: 0;
        }
        .shopee-status-desc {
            color: var(--text-secondary);
            margin: 0.35rem 0 0 0;
            font-size: 0.95rem;
        }
        .status-timeline {
            display: flex;
            gap: 0.75rem;
            align-items: flex-start;
            margin: 1rem 0 1.5rem 0;
        }
        .timeline-step {
            position: relative;
            flex: 1;
            text-align: center;
            min-width: 80px;
        }
        .timeline-step .step-dot {
            width: 18px;
            height: 18px;
            border-radius: 50%;
            margin: 0 auto;
            border: 3px solid var(--border);
            background: var(--bg-card);
            z-index: 2;
        }
        .timeline-step.done .step-dot {
            background: var(--success);
            border-color: var(--success);
        }
        .timeline-step.current .step-dot {
            background: var(--primary);
            border-color: var(--primary);
            box-shadow: 0 0 0 6px rgba(99,102,241,0.15);
        }
        .timeline-step.upcoming .step-dot {
            background: var(--bg-secondary);
            border-color: var(--border);
        }
        .timeline-step .step-connector {
            position: absolute;
            top: 8px;
            left: 50%;
            width: 100%;
            height: 3px;
            background: var(--border);
            z-index: 1;
        }
        .timeline-step.done .step-connector {
            background: linear-gradient(90deg, var(--success) 0%, var(--success) 60%, var(--border) 100%);
        }
        .timeline-step.current .step-connector {
            background: linear-gradient(90deg, var(--primary) 0%, var(--border) 100%);
        }
        .timeline-step:last-child .step-connector {
            display: none;
        }
        .timeline-step .step-label {
            margin-top: 0.5rem;
            color: var(--text-primary);
            font-weight: 600;
            font-size: 0.95rem;
        }
        .timeline-step .step-sub {
            color: var(--text-secondary);
            font-size: 0.82rem;
            margin-top: 0.15rem;
        }
        
        /* Form Container */
        .form-container {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 2rem;
            border: 1px solid var(--border);
            box-shadow: 0 4px 6px var(--shadow);
        }
        
        /* Animation */
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .card, .form-container, .metric-card {
            animation: fadeIn 0.3s ease-out;
        }
        
        /* Ẩn HOÀN TOÀN tất cả button trong webrtc container */
        div[data-testid="stWebRTC"] button,
        div[data-testid="stWebRTC"] button[title="Start"],
        div[data-testid="stWebRTC"] button[title="Stop"],
        div[data-testid="stWebRTC"] * button,
        /* Ẩn button MUI (Material-UI) */
        div[data-testid="stWebRTC"] .MuiButton-root,
        div[data-testid="stWebRTC"] .MuiButtonBase-root,
        div[data-testid="stWebRTC"] button.MuiButton-contained,
        div[data-testid="stWebRTC"] button:contains("Start"),
        div[data-testid="stWebRTC"] button:contains("Stop"),
        /* Ẩn container MUI chứa button */
        div[data-testid="stWebRTC"] .MuiBox-root {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            width: 0 !important;
            height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
            position: absolute !important;
            left: -9999px !important;
            pointer-events: none !important;
            overflow: hidden !important;
        }
        
        /* Ẩn SELECT DEVICE và các control khác */
        div[data-testid="stWebRTC"] select,
        div[data-testid="stWebRTC"] label,
        div[data-testid="stWebRTC"] .stSelectbox {
            display: none !important;
        }
        
        /* Styling cho camera box vuông */
        #camera-box-send {
            position: relative;
            display: block;
        }
        
        /* Đảm bảo webrtc container hiển thị */
        #camera-box-send div[data-testid="stWebRTC"] {
            width: 100% !important;
            height: 100% !important;
            min-height: 500px !important;
            display: block !important;
            position: relative !important;
            background: #000 !important;
        }
        
        /* Đảm bảo video element hiển thị và fit vào box */
        #camera-box-send div[data-testid="stWebRTC"] video {
            width: 100% !important;
            height: 100% !important;
            min-height: 500px !important;
            max-height: 500px !important;
            object-fit: cover !important;
            border-radius: 8px !important;
            background: #000 !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            position: relative !important;
        }
        
        /* Đảm bảo tất cả video trong camera box hiển thị */
        #camera-box-send video {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            width: 100% !important;
            height: 100% !important;
            object-fit: cover !important;
        }
        
        /* Đảm bảo camera container fit vào box vuông */
        #camera-box-send div[data-testid="stWebRTC"] > div {
            width: 100% !important;
            height: 100% !important;
            min-height: 500px !important;
            display: block !important;
            position: relative !important;
        }
    </style>
    <script>
        // Xóa hoàn toàn các button START/STOP (bao gồm MUI buttons)
        function removeStartStopButtons() {
            const webrtcContainers = document.querySelectorAll('div[data-testid="stWebRTC"]');
            webrtcContainers.forEach(container => {
                // Tìm và xóa tất cả button (bao gồm MUI)
                const buttons = container.querySelectorAll('button');
                buttons.forEach(btn => {
                    const text = (btn.textContent || btn.innerText || '').trim().toUpperCase();
                    const title = (btn.getAttribute('title') || '').toLowerCase();
                    const hasMuiClass = btn.classList.contains('MuiButton-root') || 
                                       btn.classList.contains('MuiButtonBase-root');
                    
                    // Xóa nút START, STOP, hoặc bất kỳ button MUI nào
                    if (title === 'start' || title === 'stop' || 
                        text === 'START' || text === 'STOP' || 
                        text.includes('START') || text.includes('STOP') ||
                        hasMuiClass) {
                        // Xóa button và cả parent container nếu là MUI Box
                        const parent = btn.parentNode;
                        if (parent && parent.classList && parent.classList.contains('MuiBox-root')) {
                            // Xóa cả MuiBox-root container
                            if (parent.parentNode) {
                                parent.parentNode.removeChild(parent);
                            }
                        } else {
                            // Chỉ xóa button
                            if (btn.parentNode) {
                                btn.parentNode.removeChild(btn);
                            }
                        }
                    }
                });
                
                // Xóa tất cả MuiBox-root containers (có thể chứa button START/STOP)
                const muiBoxes = container.querySelectorAll('.MuiBox-root');
                muiBoxes.forEach(box => {
                    const buttons = box.querySelectorAll('button');
                    let shouldRemove = false;
                    buttons.forEach(btn => {
                        const text = (btn.textContent || btn.innerText || '').trim().toUpperCase();
                        const hasMuiClass = btn.classList.contains('MuiButton-root') || 
                                           btn.classList.contains('MuiButtonBase-root');
                        // Xóa nếu là START/STOP hoặc là button MUI
                        if (text === 'START' || text === 'STOP' || 
                            text.includes('START') || text.includes('STOP') ||
                            hasMuiClass) {
                            shouldRemove = true;
                        }
                    });
                    if (shouldRemove && box.parentNode) {
                        box.parentNode.removeChild(box);
                    }
                });
                
                // Xóa tất cả button MUI không nằm trong MuiBox-root
                const muiButtons = container.querySelectorAll('.MuiButton-root, .MuiButtonBase-root');
                muiButtons.forEach(btn => {
                    const text = (btn.textContent || btn.innerText || '').trim().toUpperCase();
                    if (text === 'START' || text === 'STOP' || 
                        text.includes('START') || text.includes('STOP')) {
                        const parent = btn.parentNode;
                        if (parent && parent.classList && parent.classList.contains('MuiBox-root')) {
                            if (parent.parentNode) {
                                parent.parentNode.removeChild(parent);
                            }
                        } else if (btn.parentNode) {
                            btn.parentNode.removeChild(btn);
                        }
                    }
                });
                
                // Xóa SELECT DEVICE
                const selects = container.querySelectorAll('select');
                selects.forEach(sel => {
                    if (sel.parentNode) {
                        sel.parentNode.removeChild(sel);
                    }
                });
                
                // Xóa label liên quan
                const labels = container.querySelectorAll('label');
                labels.forEach(label => {
                    const text = (label.textContent || '').toUpperCase();
                    if (text.includes('DEVICE') || text.includes('SELECT')) {
                        if (label.parentNode) {
                            label.parentNode.removeChild(label);
                        }
                    }
                });
            });
        }
        
        // Tự động start camera ngay khi được render
        function autoStartCamera() {
            const webrtcContainers = document.querySelectorAll('div[data-testid="stWebRTC"]');
            webrtcContainers.forEach(container => {
                // Kiểm tra xem đã start chưa
                if (container.dataset.autoStarted === 'true') {
                    // Vẫn xóa button để đảm bảo
                    removeStartStopButtons();
                    return;
                }
                
                // Tìm tất cả button (bao gồm MUI)
                const buttons = container.querySelectorAll('button');
                let startButton = null;
                let startButtonParent = null;
                
                buttons.forEach(btn => {
                    const text = (btn.textContent || btn.innerText || '').trim().toUpperCase();
                    const title = (btn.getAttribute('title') || '').toLowerCase();
                    const hasMuiClass = btn.classList.contains('MuiButton-root') || 
                                       btn.classList.contains('MuiButtonBase-root');
                    
                    // Tìm nút START (có thể là MUI hoặc button thường)
                    if (title === 'start' || text === 'START' || text.includes('START')) {
                        startButton = btn;
                        // Nếu button nằm trong MuiBox-root, lưu parent để xóa sau
                        if (btn.parentNode && btn.parentNode.classList && 
                            btn.parentNode.classList.contains('MuiBox-root')) {
                            startButtonParent = btn.parentNode;
                        }
                    }
                });
                
                // Tự động click START ngay lập tức
                if (startButton) {
                    try {
                        // Click START
                        startButton.click();
                        container.dataset.autoStarted = 'true';
                        
                        // Xóa button và parent container sau khi click
                        setTimeout(() => {
                            // Xóa cả MuiBox-root container nếu có
                            if (startButtonParent && startButtonParent.parentNode) {
                                startButtonParent.parentNode.removeChild(startButtonParent);
                            } else if (startButton.parentNode) {
                                // Hoặc chỉ xóa button
                                startButton.parentNode.removeChild(startButton);
                            }
                            
                            // Xóa tất cả button còn lại (bao gồm STOP)
                            container.querySelectorAll('button').forEach(b => {
                                const text = (b.textContent || b.innerText || '').trim().toUpperCase();
                                if (text === 'STOP' || text.includes('STOP')) {
                                    const parent = b.parentNode;
                                    if (parent && parent.classList && parent.classList.contains('MuiBox-root')) {
                                        if (parent.parentNode) {
                                            parent.parentNode.removeChild(parent);
                                        }
                                    } else if (b.parentNode) {
                                        b.parentNode.removeChild(b);
                                    }
                                }
                            });
                            
                            // Xóa tất cả MuiBox-root containers
                            container.querySelectorAll('.MuiBox-root').forEach(box => {
                                const buttons = box.querySelectorAll('button');
                                buttons.forEach(btn => {
                                    const text = (btn.textContent || btn.innerText || '').trim().toUpperCase();
                                    if (text === 'START' || text === 'STOP') {
                                        if (box.parentNode) {
                                            box.parentNode.removeChild(box);
                                        }
                                    }
                                });
                            });
                        }, 100);
                    } catch(e) {
                        console.log('Auto-start error:', e);
                    }
                } else {
                    // Nếu không tìm thấy button START, kiểm tra xem camera đã chạy chưa
                    const video = container.querySelector('video');
                    if (video) {
                        // Đảm bảo video hiển thị
                        video.style.display = 'block';
                        video.style.visibility = 'visible';
                        video.style.opacity = '1';
                        video.style.width = '100%';
                        video.style.height = '100%';
                        video.style.objectFit = 'cover';
                        
                        if (video.paused) {
                            video.play().catch(() => {});
                        }
                        container.dataset.autoStarted = 'true';
                    } else {
                        // Nếu chưa có video, thử tìm lại button START sau một chút
                        setTimeout(() => {
                            const retryButtons = container.querySelectorAll('button');
                            retryButtons.forEach(btn => {
                                const text = (btn.textContent || btn.innerText || '').trim().toUpperCase();
                                const title = (btn.getAttribute('title') || '').toLowerCase();
                                if (title === 'start' || text === 'START' || text.includes('START')) {
                                    btn.click();
                                    container.dataset.autoStarted = 'true';
                                }
                            });
                        }, 500);
                    }
                }
                
                // Đảm bảo video hiển thị nếu đã có
                const video = container.querySelector('video');
                if (video) {
                    video.style.display = 'block';
                    video.style.visibility = 'visible';
                    video.style.opacity = '1';
                }
                
                // Luôn xóa button để đảm bảo
                removeStartStopButtons();
            });
        }
        
        // Chạy ngay khi DOM ready
        function initAutoStart() {
            autoStartCamera();
            removeStartStopButtons();
            // Chạy lại nhiều lần để đảm bảo
            setTimeout(() => { autoStartCamera(); removeStartStopButtons(); }, 100);
            setTimeout(() => { autoStartCamera(); removeStartStopButtons(); }, 300);
            setTimeout(() => { autoStartCamera(); removeStartStopButtons(); }, 500);
            setTimeout(() => { autoStartCamera(); removeStartStopButtons(); }, 1000);
        }
        
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initAutoStart);
        } else {
            initAutoStart();
        }
        
        // Observer để tự động start và xóa button khi có element mới
        const observer = new MutationObserver(function(mutations) {
            let hasWebRTC = false;
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) {
                        if (node.getAttribute && node.getAttribute('data-testid') === 'stWebRTC') {
                            hasWebRTC = true;
                        } else if (node.querySelector) {
                            const webrtc = node.querySelector('div[data-testid="stWebRTC"]');
                            if (webrtc) hasWebRTC = true;
                        }
                    }
                });
            });
            if (hasWebRTC) {
                // Chạy ngay
                autoStartCamera();
                removeStartStopButtons();
                // Chạy lại sau một chút
                setTimeout(() => { autoStartCamera(); removeStartStopButtons(); }, 100);
                setTimeout(() => { autoStartCamera(); removeStartStopButtons(); }, 300);
            }
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        // Đảm bảo video luôn hiển thị
        function ensureVideoVisible() {
            // Tìm tất cả video trong webrtc containers
            const videos = document.querySelectorAll('div[data-testid="stWebRTC"] video');
            videos.forEach(video => {
                if (video) {
                    // Force hiển thị video
                    video.style.display = 'block';
                    video.style.visibility = 'visible';
                    video.style.opacity = '1';
                    video.style.width = '100%';
                    video.style.height = '100%';
                    video.style.minHeight = '500px';
                    video.style.maxHeight = '500px';
                    video.style.objectFit = 'cover';
                    video.style.background = '#000';
                    video.style.position = 'relative';
                    video.style.zIndex = '1';
                    
                    // Đảm bảo video play
                    if (video.paused && video.readyState >= 2) {
                        video.play().catch(() => {});
                    }
                }
            });
            
            // Đặc biệt cho camera-box-send
            const cameraBox = document.getElementById('camera-box-send');
            if (cameraBox) {
                const boxVideos = cameraBox.querySelectorAll('video');
                boxVideos.forEach(video => {
                    if (video) {
                        video.style.display = 'block';
                        video.style.visibility = 'visible';
                        video.style.opacity = '1';
                        video.style.width = '100%';
                        video.style.height = '100%';
                        video.style.minHeight = '500px';
                        video.style.objectFit = 'cover';
                        video.style.background = '#000';
                    }
                });
            }
        }
        
        // Observer riêng để phát hiện khi video được tạo
        const videoObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) {
                        // Nếu là video element
                        if (node.tagName === 'VIDEO') {
                            ensureVideoVisible();
                            // Force play video
                            setTimeout(() => {
                                if (node.paused) {
                                    node.play().catch(() => {});
                                }
                            }, 100);
                        }
                        // Nếu chứa video
                        if (node.querySelectorAll) {
                            const videos = node.querySelectorAll('video');
                            if (videos.length > 0) {
                                ensureVideoVisible();
                            }
                        }
                    }
                });
            });
        });
        
        videoObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        // Chạy lại mỗi 200ms để xóa button và đảm bảo video hiển thị
        setInterval(() => {
            removeStartStopButtons();
            autoStartCamera();
            ensureVideoVisible();
        }, 200);
    </script>
    """,
    unsafe_allow_html=True,
)


# -------------------- DATABASE HELPERS --------------------
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ShipmentDetails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qr_code TEXT UNIQUE,
            imei TEXT,
            device_name TEXT,
            capacity TEXT,
            supplier TEXT,
            status TEXT DEFAULT 'Đang gửi',
            sent_time TEXT DEFAULT CURRENT_TIMESTAMP,
            received_time TEXT,
            notes TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS AuditLog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER,
            action TEXT,
            old_value TEXT,
            new_value TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            user_action TEXT,
            FOREIGN KEY (shipment_id) REFERENCES ShipmentDetails(id)
        )
        """
    )
    conn.commit()
    conn.close()


def clear_caches() -> None:
    get_all_shipments.clear()
    get_suppliers.clear()
    get_daily_statistics.clear()
    get_supplier_statistics.clear()
    get_processing_time.clear()


def log_action(
    shipment_id: int, action: str, old_value: Optional[str], new_value: Optional[str], user: str
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO AuditLog (shipment_id, action, old_value, new_value, user_action)
        VALUES (?, ?, ?, ?, ?)
        """,
        (shipment_id, action, old_value, new_value, user),
    )
    conn.commit()
    conn.close()


def insert_shipment(
    qr_code: str,
    imei: str,
    device_name: str,
    capacity: str,
    supplier: str,
    notes: str,
    user: str = "user",
) -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO ShipmentDetails
            (qr_code, imei, device_name, capacity, supplier, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (qr_code.strip(), imei.strip(), device_name.strip(), capacity.strip(), supplier, notes),
        )
        shipment_id = cur.lastrowid
        conn.commit()
        log_action(shipment_id, "Tạo phiếu", None, "Đang gửi", user)
        clear_caches()
        return True, "Phiếu lưu thành công"
    except sqlite3.IntegrityError:
        return False, "QR code đã tồn tại"
    finally:
        conn.close()


def update_shipment_status(qr_code: str, new_status: str, user: str = "user") -> Tuple[bool, str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, status FROM ShipmentDetails WHERE qr_code = ?", (qr_code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "Không tìm thấy phiếu"

    shipment_id = row["id"]
    old_status = row["status"]
    received_time = datetime.now().isoformat() if new_status == "Đã nhận" else None

    cur.execute(
        """
        UPDATE ShipmentDetails
        SET status = ?, received_time = COALESCE(?, received_time)
        WHERE id = ?
        """,
        (new_status, received_time, shipment_id),
    )
    conn.commit()
    conn.close()

    log_action(shipment_id, "Cập nhật trạng thái", old_status, new_status, user)
    clear_caches()
    return True, "Cập nhật thành công"


@st.cache_data(ttl=300)
def get_all_shipments() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM ShipmentDetails ORDER BY sent_time DESC", conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_suppliers() -> List[str]:
    conn = get_connection()
    df = pd.read_sql("SELECT DISTINCT supplier FROM ShipmentDetails ORDER BY supplier", conn)
    conn.close()
    suppliers = df["supplier"].dropna().tolist()
    return suppliers


@st.cache_data(ttl=300)
def get_daily_statistics() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        """
        SELECT DATE(sent_time) as date,
               COUNT(*) as total,
               SUM(CASE WHEN status = 'Đã nhận' THEN 1 ELSE 0 END) as received
        FROM ShipmentDetails
        GROUP BY DATE(sent_time)
        ORDER BY date DESC
        LIMIT 30
        """,
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_supplier_statistics() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        """
        SELECT supplier,
               COUNT(*) as total,
               SUM(CASE WHEN status = 'Đã nhận' THEN 1 ELSE 0 END) as received
        FROM ShipmentDetails
        GROUP BY supplier
        """,
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_processing_time() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        """
        SELECT 
            supplier,
            AVG(CAST((julianday(COALESCE(received_time, sent_time)) - julianday(sent_time)) * 24 * 60 AS FLOAT)) as avg_minutes
        FROM ShipmentDetails
        WHERE status = 'Đã nhận'
        GROUP BY supplier
        """,
        conn,
    )
    conn.close()
    return df


def search_shipments(
    keyword: str,
    status: Optional[str],
    supplier: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
) -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT * FROM ShipmentDetails WHERE 1=1"
    params: List[str] = []

    if keyword:
        query += " AND (qr_code LIKE ? OR imei LIKE ? OR device_name LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    if status:
        query += " AND status = ?"
        params.append(status)

    if supplier:
        query += " AND supplier = ?"
        params.append(supplier)

    if date_from:
        query += " AND DATE(sent_time) >= ?"
        params.append(date_from)

    if date_to:
        query += " AND DATE(sent_time) <= ?"
        params.append(date_to)

    query += " ORDER BY sent_time DESC"

    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


def get_statistics() -> Tuple[int, int, int, int]:
    df = get_all_shipments()
    total = len(df)
    pending = len(df[df["status"] == "Đang gửi"])
    received = len(df[df["status"] == "Đã nhận"])
    error = total - pending - received
    return total, pending, received, error


def get_shipment_by_qr(qr_code: str) -> Optional[pd.Series]:
    df = get_all_shipments()
    match = df[df["qr_code"] == qr_code]
    if match.empty:
        return None
    return match.iloc[0]


def get_shipment_history(shipment_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        """
        SELECT action, old_value, new_value, timestamp, user_action
        FROM AuditLog
        WHERE shipment_id = ?
        ORDER BY timestamp DESC
        """,
        conn,
        params=[shipment_id],
    )
    conn.close()
    return df


def show_shipment_timeline(shipment_id: int) -> None:
    history = get_shipment_history(shipment_id)
    if history.empty:
        st.info("Chưa có lịch sử thay đổi.")
        return
    st.markdown("#### Lịch Sử Thay Đổi")
    for idx, row in history.iterrows():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f"**{row['action']}**")
        st.markdown(f"🕐 {row['timestamp']}")
        if row["old_value"]:
            st.markdown(f"**Thay đổi:** `{row['old_value']}` → `{row['new_value']}`")
        st.markdown(f"👤 Người thực hiện: {row['user_action']}")
        st.markdown('</div>', unsafe_allow_html=True)


# -------------------- EXPORT HELPERS --------------------
def generate_pdf_report(
    shipments_df: pd.DataFrame,
    supplier: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> io.BytesIO:
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4)
    elements: List = []

    styles = getSampleStyleSheet()
    title = Paragraph(
        f"<b>BÁO CÁO GIAO NHẬN - {datetime.now().strftime('%d/%m/%Y')}</b>", styles["Title"]
    )
    elements.append(title)
    elements.append(Spacer(1, 0.3 * inch))

    if supplier or date_from or date_to:
        filter_text = "Bộ lọc: "
        parts = []
        if supplier:
            parts.append(f"NCC={supplier}")
        if date_from:
            parts.append(f"Từ {date_from}")
        if date_to:
            parts.append(f"Đến {date_to}")
        filter_text += ", ".join(parts)
        elements.append(Paragraph(filter_text, styles["Normal"]))
        elements.append(Spacer(1, 0.2 * inch))

    table_data = [
        ["STT", "Mã QR", "IMEI", "Máy", "NCC", "Trạng Thái", "Gửi Lúc", "Nhận Lúc"]
    ]
    for idx, row in shipments_df.reset_index(drop=True).iterrows():
        table_data.append(
            [
                str(idx + 1),
                row.get("qr_code", "")[:10],
                (row.get("imei", "") or "")[-6:],
                (row.get("device_name", "") or "")[:15],
                row.get("supplier", "") or "",
                row.get("status", "") or "",
                (row.get("sent_time", "") or "")[:16],
                (row.get("received_time", "") or "")[:16] or "-",
            ]
        )

    table = Table(table_data, colWidths=[0.6 * inch] * 8)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#667eea")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    elements.append(table)
    pdf.build(elements)
    buffer.seek(0)
    return buffer


def generate_excel_report(shipments_df: pd.DataFrame) -> io.BytesIO:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        shipments_df.to_excel(writer, sheet_name="Phiếu Gửi", index=False)
        stats_data = {
            "Chỉ Số": ["Tổng Phiếu", "Đang Gửi", "Đã Nhận", "Lỗi/Khác"],
            "Số Lượng": [
                len(shipments_df),
                len(shipments_df[shipments_df["status"] == "Đang gửi"]),
                len(shipments_df[shipments_df["status"] == "Đã nhận"]),
                len(
                    shipments_df[
                        ~shipments_df["status"].isin(["Đang gửi", "Đã nhận"])
                    ]
                ),
            ],
        }
        stats_df = pd.DataFrame(stats_data)
        stats_df.to_excel(writer, sheet_name="Thống Kê", index=False)
    output.seek(0)
    return output


# -------------------- UI HELPERS --------------------
def show_header() -> None:
    st.markdown(
        """
        <div style="margin-bottom: 2rem;">
            <h1>Hệ Thống Quản Lý Giao Nhận</h1>
            <p style="color: var(--text-secondary); font-size: 1.1rem; margin-top: -0.5rem;">
                Quét QR, quản lý phiếu, thống kê và xuất báo cáo
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_statistics() -> None:
    total, pending, received, error = get_statistics()
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Tổng Phiếu</div>
                <div class="metric-value">{total}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Đang Gửi</div>
                <div class="metric-value" style="color: var(--warning);">{pending}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Đã Nhận</div>
                <div class="metric-value" style="color: var(--success);">{received}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">Khác</div>
                <div class="metric-value" style="color: var(--danger);">{error}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def get_status_display(status: str) -> Tuple[str, str]:
    """Trả về (nhãn hiển thị kiểu Shopee, mô tả) cho trạng thái."""
    display = STATUS_ALIASES.get(status, status)
    desc = STATUS_DESCRIPTIONS.get(status, "Đơn hàng đang được xử lý.")
    return display, desc


def build_status_steps(history_statuses: List[str], current_status: str) -> List[str]:
    """Tạo danh sách step theo flow, chỉ cho những trạng thái đã xuất hiện + hiện tại."""
    seen = set()
    steps: List[str] = []
    target_statuses = history_statuses + [current_status]
    for status in STATUS_FLOW:
        if status in target_statuses and status not in seen:
            steps.append(status)
            seen.add(status)
    if not steps:
        steps.append(current_status or "Đang gửi")
    return steps


def render_shopee_status_card(current_status: str) -> None:
    label, desc = get_status_display(current_status)
    st.markdown(
        f"""
        <div class="shopee-status-card">
            <p class="shopee-status-title">{label}</p>
            <p class="shopee-status-desc">{desc}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_timeline(history_statuses: List[str], current_status: str) -> None:
    steps = build_status_steps(history_statuses, current_status)
    try:
        active_idx = steps.index(current_status)
    except ValueError:
        active_idx = len(steps) - 1

    timeline_html = '<div class="status-timeline">'
    for idx, status in enumerate(steps):
        state_class = "current" if idx == active_idx else "done" if idx < active_idx else "upcoming"
        label, desc = get_status_display(status)
        connector = '<div class="step-connector"></div>' if idx < len(steps) - 1 else ""
        timeline_html += f"""
            <div class="timeline-step {state_class}">
                <div class="step-dot"></div>
                {connector}
                <div class="step-label">{label}</div>
                <div class="step-sub">{desc}</div>
            </div>
        """
    timeline_html += "</div>"
    st.markdown(timeline_html, unsafe_allow_html=True)


def render_recent_shipments(limit: int = 10) -> None:
    df = get_all_shipments().head(limit)
    if df.empty:
        st.info("Chưa có phiếu nào. Hãy tạo mới ở tab Quét QR.")
        return
    st.dataframe(df[["qr_code", "imei", "device_name", "supplier", "status", "sent_time"]])


# -------------------- PAGES --------------------
def page_home():
    show_header()
    show_statistics()
    st.markdown("### Phiếu gần đây")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    render_recent_shipments()
    st.markdown('</div>', unsafe_allow_html=True)


def page_send():
    # Initialize session state
    if "qr_send_value" not in st.session_state:
        st.session_state["qr_send_value"] = ""
    if "imei_send_value" not in st.session_state:
        st.session_state["imei_send_value"] = ""
    if "device_name_send_value" not in st.session_state:
        st.session_state["device_name_send_value"] = ""
    if "capacity_send_value" not in st.session_state:
        st.session_state["capacity_send_value"] = ""

    st.markdown("### Quét QR Gửi")
    
    # Camera box luôn hiển thị ở đầu trang
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("#### 📷 Quét QR Code")
    
    # Kiểm tra dependencies
    if any(dep is None for dep in [av, cv2, np, decode, webrtc_streamer, WebRtcMode]):
        st.error("⚠️ Camera không khả dụng!")
        st.warning("Cần cài đặt các thư viện sau:")
        st.code("pip install streamlit-webrtc opencv-python-headless pyzbar av", language="bash")
    else:
        # Thông báo hướng dẫn
        st.info("📷 Camera sẵn sàng. Đưa QR code vào khung hình để quét tự động.")
        
        # Box vuông để hiển thị camera - dùng container của Streamlit
        with st.container():
            st.markdown(
                """
                <div style="
                    width: 100%;
                    max-width: 500px;
                    min-height: 500px;
                    aspect-ratio: 1;
                    margin: 1.5rem auto;
                    background: #000;
                    border: 3px solid var(--primary);
                    border-radius: 12px;
                    overflow: visible;
                    box-shadow: 0 8px 32px rgba(99, 102, 241, 0.3);
                    position: relative;
                " id="camera-box-send">
                """,
                unsafe_allow_html=True,
            )
            
            # Render camera trực tiếp - luôn hiển thị
            qr_code_cam = qrcode_scanner("qr-camera-send", show=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Hướng dẫn sử dụng
        st.markdown(
            """
            <div style="background: rgba(99, 102, 241, 0.1); border-radius: 8px; padding: 0.75rem; margin-top: 1rem; text-align: center; color: var(--text-secondary); font-size: 0.9rem;">
                📷 Đưa QR code vào khung hình camera ở trên để quét tự động
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        # Xử lý khi quét thành công
        if qr_code_cam:
            # Parse QR code và điền thông tin
            parsed = parse_qr_code(qr_code_cam)
            st.session_state["qr_send_value"] = parsed["qr_code"]
            st.session_state["imei_send_value"] = parsed["imei"]
            st.session_state["device_name_send_value"] = parsed["device_name"]
            st.session_state["capacity_send_value"] = parsed["capacity"]
            st.success("✅ Quét thành công! Thông tin đã được điền vào form bên dưới.")
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")

    # Form với card design
    st.markdown('<div class="form-container">', unsafe_allow_html=True)
    with st.form("send_form"):
        st.markdown("#### Thông tin phiếu gửi")
        
        col1, col2 = st.columns(2)
        with col1:
            qr_code = st.text_input(
                "Mã QR *",
                value=st.session_state["qr_send_value"],
                help="Quét hoặc nhập mã QR",
                key="qr_code_send_input",
                placeholder="Nhập hoặc quét mã QR",
            )
        with col2:
            imei = st.text_input(
                "IMEI",
                value=st.session_state["imei_send_value"],
                key="imei_send_input",
                placeholder="Nhập IMEI",
            )
        
        col3, col4 = st.columns(2)
        with col3:
            device_name = st.text_input(
                "Tên máy",
                value=st.session_state["device_name_send_value"],
                key="device_name_send_input",
                placeholder="Ví dụ: iPhone 15 Pro Max",
            )
        with col4:
            capacity = st.text_input(
                "Dung lượng",
                value=st.session_state["capacity_send_value"],
                key="capacity_send_input",
                placeholder="Ví dụ: 128GB",
            )
        
        supplier = st.text_input(
            "Nhà cung cấp",
            placeholder="Nhập tên nhà cung cấp",
        )
        notes = st.text_area(
            "Ghi chú",
            height=100,
            placeholder="Nhập ghi chú nếu có...",
        )
        
        submitted = st.form_submit_button("💾 LƯU PHIẾU", use_container_width=True)
        if submitted:
            if not qr_code:
                st.error("⚠️ Vui lòng nhập mã QR.")
            else:
                success, msg = insert_shipment(qr_code, imei, device_name, capacity, supplier, notes)
                if success:
                    st.success(msg)
                    # Reset form sau khi lưu thành công
                    st.session_state["qr_send_value"] = ""
                    st.session_state["imei_send_value"] = ""
                    st.session_state["device_name_send_value"] = ""
                    st.session_state["capacity_send_value"] = ""
                    st.rerun()
                else:
                    st.warning(msg)
    st.markdown('</div>', unsafe_allow_html=True)


def page_receive():
    # Initialize session state
    if "show_camera_receive" not in st.session_state:
        st.session_state["show_camera_receive"] = False
    if "qr_recv_value" not in st.session_state:
        st.session_state["qr_recv_value"] = ""

    # Hiển thị camera ở đầu trang nếu được bật
    if st.session_state["show_camera_receive"]:
        st.markdown("---")
        st.markdown("## 📷 Quét QR Code")
        
        # Kiểm tra dependencies
        if any(dep is None for dep in [av, cv2, np, decode, webrtc_streamer, WebRtcMode]):
            st.error("⚠️ Camera không khả dụng!")
            st.warning("Cần cài đặt các thư viện sau:")
            st.code("pip install streamlit-webrtc opencv-python-headless pyzbar av", language="bash")
            if st.button("✕ Đóng", key="close_camera_error_receive"):
                st.session_state["show_camera_receive"] = False
                st.rerun()
            return
        
        # Thông báo hướng dẫn
        st.info("📷 Camera đang khởi động... Vui lòng cho phép trình duyệt truy cập camera khi được hỏi.")
        
        # Render camera
        qr_code_cam = qrcode_scanner("qr-camera-receive", show=True)
        
        # Nút đóng camera
        col_close1, col_close2 = st.columns([3, 1])
        with col_close2:
            if st.button("✕ Đóng Camera", key="close_camera_receive", use_container_width=True):
                st.session_state["show_camera_receive"] = False
                st.rerun()
        
        # Hướng dẫn sử dụng
        st.markdown(
            """
            <div style="background: rgba(99, 102, 241, 0.1); border-radius: 8px; padding: 1rem; margin: 1rem 0; text-align: center; color: var(--text-secondary);">
                📷 Đưa QR code vào khung hình camera ở trên để quét tự động
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        # Xử lý khi quét thành công
        if qr_code_cam:
            st.session_state["qr_recv_value"] = qr_code_cam
            st.session_state["show_camera_receive"] = False
            st.success("✅ Quét thành công!")
            st.rerun()
        
        st.markdown("---")
        return  # Dừng render phần còn lại khi đang hiển thị camera
    
    st.markdown("### Tiếp Nhận Hàng")
    
    # Nút Quét
    col1, col2 = st.columns([1, 4])
    with col1:
        scan_btn = st.button("📷 Quét QR", key="scan_button_receive", use_container_width=True)
        if scan_btn:
            st.session_state["show_camera_receive"] = True
            st.rerun()

    st.markdown('<div class="form-container">', unsafe_allow_html=True)
    qr_code = st.text_input(
        "Mã QR để cập nhật",
        value=st.session_state["qr_recv_value"],
        key="qr_code_receive_input",
        placeholder="Quét hoặc nhập mã QR",
    )
    
    if qr_code:
        shipment = get_shipment_by_qr(qr_code)
        if shipment is None:
            st.error("❌ Không tìm thấy phiếu với mã QR này.")
        else:
            st.markdown("#### Thông tin phiếu")
            st.markdown('<div class="card">', unsafe_allow_html=True)
            
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.write(f"**Mã QR:** {shipment['qr_code']}")
                st.write(f"**IMEI:** {shipment['imei']}")
                st.write(f"**Tên máy:** {shipment['device_name']}")
            with col_info2:
                st.write(f"**Dung lượng:** {shipment['capacity']}")
                st.write(f"**Nhà cung cấp:** {shipment['supplier']}")
                status_color = {
                    "Đang gửi": "status-pending",
                    "Đã nhận": "status-received",
                    "Hư hỏng": "status-error"
                }.get(shipment['status'], "")
                st.markdown(
                    f"**Trạng thái:** <span class='status-badge {status_color}'>{shipment['status']}</span>",
                    unsafe_allow_html=True
                )
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            new_status = st.selectbox("Trạng thái mới", ["Đang gửi", "Đã nhận", "Hư hỏng"])
            
            if st.button("🔄 CẬP NHẬT", use_container_width=True):
                success, msg = update_shipment_status(qr_code, new_status)
                if success:
                    st.success(msg)
                    st.session_state["qr_recv_value"] = ""
                    st.rerun()
                else:
                    st.error(msg)
    st.markdown('</div>', unsafe_allow_html=True)


def page_tracking():
    st.markdown("### Lộ Trình & Lịch Sử Trạng Thái")
    shipments = get_all_shipments()

    if shipments.empty:
        st.info("Chưa có phiếu nào để theo dõi.")
        return

    qr_options = ["Chọn mã QR..."] + shipments["qr_code"].tolist()
    selected_qr = st.selectbox("Chọn mã QR để xem lộ trình", qr_options)
    if selected_qr == "Chọn mã QR...":
        return

    shipment_row = shipments[shipments["qr_code"] == selected_qr]
    if shipment_row.empty:
        st.warning("Không tìm thấy phiếu tương ứng.")
        return

    shipment = shipment_row.iloc[0]
    current_status = shipment.get("status", "Đang gửi")

    st.markdown(
        f"**Trạng thái hiện tại:** <span class='status-badge status-pending'>{current_status}</span>",
        unsafe_allow_html=True,
    )
    render_shopee_status_card(current_status)

    history_df = get_shipment_history(int(shipment["id"]))
    history_statuses = [
        row["new_value"]
        for _, row in history_df.iterrows()
        if isinstance(row.get("new_value"), str) and row["new_value"]
    ]
    render_status_timeline(history_statuses, current_status)

    st.markdown("#### Cập nhật gần nhất")
    if history_df.empty:
        st.info("Chưa có lịch sử thay đổi.")
    else:
        display_history = history_df.rename(
            columns={
                "timestamp": "Thời gian",
                "action": "Hành động",
                "new_value": "Trạng thái mới",
                "old_value": "Trạng thái cũ",
                "user_action": "Người thực hiện",
            }
        )
        st.dataframe(display_history, use_container_width=True)


def page_dashboard():
    st.markdown("### Dashboard Phân Tích")
    
    # Filters trong card
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("#### Bộ lọc")
    col1, col2, col3 = st.columns(3)
    with col1:
        keyword = st.text_input("🔍 Tìm kiếm", placeholder="QR/IMEI/Tên máy")
    with col2:
        filter_status = st.selectbox("📊 Trạng thái", ["Tất cả", "Đang gửi", "Đã nhận", "Hư hỏng"])
    with col3:
        supplier_options = ["Tất cả"] + get_suppliers()
        filter_supplier = st.selectbox("🏢 Nhà cung cấp", supplier_options)

    col4, col5 = st.columns(2)
    with col4:
        date_from = st.date_input("📅 Từ ngày", value=None)
    with col5:
        date_to = st.date_input("📅 Đến ngày", value=None)
    st.markdown('</div>', unsafe_allow_html=True)

    status = None if filter_status == "Tất cả" else filter_status
    supplier = None if filter_supplier == "Tất cả" else filter_supplier
    from_str = date_from.isoformat() if isinstance(date_from, date) else None
    to_str = date_to.isoformat() if isinstance(date_to, date) else None

    results = search_shipments(keyword, status, supplier, from_str, to_str)
    if len(results) > 200:
        st.info(f"📊 Có {len(results)} phiếu. Hiển thị 200 phiếu gần nhất.")
        results = results.head(200)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("#### Danh sách phiếu")
    st.dataframe(results, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.divider()
    
    # Thống kê theo NCC
    st.markdown("#### Thống Kê Theo Nhà Cung Cấp")
    supplier_stats = get_supplier_statistics()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.dataframe(supplier_stats, use_container_width=True)
    with col2:
        if not supplier_stats.empty:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.pie(
                supplier_stats["total"],
                labels=supplier_stats["supplier"],
                autopct="%1.1f%%",
                startangle=90,
            )
            ax.set_title("Phân bố theo NCC", fontsize=14, fontweight="bold")
            st.pyplot(fig)
        else:
            st.info("Chưa có dữ liệu NCC.")
    st.markdown('</div>', unsafe_allow_html=True)

    # Thống kê theo ngày
    st.markdown("#### Thống Kê Theo Ngày")
    daily_stats = get_daily_statistics()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if not daily_stats.empty:
        st.line_chart(daily_stats.set_index("date")[["total", "received"]])
    else:
        st.info("Chưa có dữ liệu ngày.")
    st.markdown('</div>', unsafe_allow_html=True)

    # Thời gian xử lý
    st.markdown("#### Thời Gian Xử Lý Trung Bình (phút)")
    processing = get_processing_time()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.dataframe(processing, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.divider()
    
    # Xuất báo cáo
    st.markdown("### Xuất Báo Cáo")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    colx, coly, colz = st.columns(3)
    with colx:
        pdf_buffer = generate_pdf_report(results, supplier=supplier, date_from=from_str, date_to=to_str)
        st.download_button(
            "📄 Tải PDF",
            data=pdf_buffer,
            file_name=f"report_{datetime.now().strftime('%d%m%Y_%H%M%S')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with coly:
        excel_buffer = generate_excel_report(results)
        st.download_button(
            "📊 Tải Excel",
            data=excel_buffer,
            file_name=f"report_{datetime.now().strftime('%d%m%Y_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with colz:
        csv_data = results.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📋 Tải CSV",
            data=csv_data,
            file_name=f"report_{datetime.now().strftime('%d%m%Y_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # Lịch sử phiếu
    st.divider()
    st.markdown("### Lịch Sử Phiếu")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    qr_for_history = st.selectbox(
        "Chọn phiếu để xem timeline",
        options=["Chọn..."] + results["qr_code"].tolist() if not results.empty else ["Chọn..."],
    )
    if qr_for_history != "Chọn...":
        shipment = get_shipment_by_qr(qr_for_history)
        if shipment is not None:
            show_shipment_timeline(int(shipment["id"]))
    st.markdown('</div>', unsafe_allow_html=True)


# -------------------- QR SCANNER --------------------
def parse_qr_code(qr_text: str) -> dict:
    """Parse QR code format: YCSC001234,124109200901,iPhone 15 Pro Max,128"""
    parts = [p.strip() for p in qr_text.split(",") if p.strip()]
    result = {"qr_code": "", "imei": "", "device_name": "", "capacity": ""}
    if len(parts) >= 1:
        result["qr_code"] = parts[0]
    if len(parts) >= 2:
        result["imei"] = parts[1]
    if len(parts) >= 3:
        result["device_name"] = parts[2]
    if len(parts) >= 4:
        result["capacity"] = parts[3]
    return result


def render_camera_modal(show: bool, key: str, title: str = "Quét QR Code") -> Optional[str]:
    """Render camera in a prominent container."""
    if not show:
        return None
    
    # Kiểm tra dependencies trước
    if any(dep is None for dep in [av, cv2, np, decode, webrtc_streamer, WebRtcMode]):
        st.error("⚠️ Camera không khả dụng. Cần cài thêm các thư viện:")
        st.code("pip install streamlit-webrtc opencv-python-headless pyzbar av", language="bash")
        return None
    
    # Render title và container đẹp
    st.markdown(f"## {title}")
    st.info("📷 Đang khởi động camera... Vui lòng cho phép trình duyệt truy cập camera khi được hỏi.")
    
    # Container cho camera
    with st.container():
        st.markdown(
            """
            <div style="background: #000; border-radius: 16px; padding: 1rem; margin: 1rem 0; min-height: 400px; display: flex; align-items: center; justify-content: center; border: 2px solid var(--primary);">
            """,
            unsafe_allow_html=True,
        )
        
        # Render camera trực tiếp
        qr_code = qrcode_scanner(key, show=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Hướng dẫn
    st.markdown(
        """
        <div style="margin-top: 1rem; text-align: center; color: var(--text-secondary); font-size: 0.9rem; padding: 1rem; background: rgba(99, 102, 241, 0.1); border-radius: 8px;">
            📷 Đưa QR code vào khung hình camera ở trên để quét tự động
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    return qr_code


def qrcode_scanner(key: str, show: bool = True) -> Optional[str]:
    """Use camera to scan QR; returns decoded string or None."""
    if not show:
        return None
    
    if any(dep is None for dep in [av, cv2, np, decode, webrtc_streamer, WebRtcMode]):
        return None

    result_holder = {"code": None}

    def video_frame_callback(frame):
        try:
            img = frame.to_ndarray(format="bgr24")
            # Decode QR codes từ frame
            decoded_objects = decode(img)
            for qrobj in decoded_objects:
                result_holder["code"] = qrobj.data.decode("utf-8")
                # Vẽ khung xanh quanh QR code đã quét được
                pts = np.array([[p.x, p.y] for p in qrobj.polygon], dtype=np.int32)
                cv2.polylines(img, [pts], True, (0, 255, 0), 3)
                # Vẽ text "QR Code Detected"
                cv2.putText(img, "QR Code Detected!", (pts[0][0], pts[0][1] - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        except Exception as e:
            pass
        return av.VideoFrame.from_ndarray(img, format="bgr24")

    # Render camera - Streamlit webrtc sẽ tự render UI
    try:
        webrtc_streamer(
            key=key,
            mode=WebRtcMode.SENDONLY,
            media_stream_constraints={"video": True, "audio": False},
            video_frame_callback=video_frame_callback,
            rtc_configuration={
                "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
            },
        )
    except Exception as e:
        st.error(f"Lỗi khởi động camera: {str(e)}")
        return None
    
    # Trả về QR code nếu đã quét được
    return result_holder["code"]


# -------------------- MAIN --------------------
def main():
    init_database()
    
    # Sidebar với styling đẹp
    with st.sidebar:
        st.markdown(
            """
            <div style="padding: 1rem 0; border-bottom: 1px solid var(--border); margin-bottom: 1rem;">
                <h2 style="margin: 0; color: var(--text-primary);">Menu</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        page = st.radio(
            "Chọn chức năng:",
            [
                "🏠 Trang Chủ",
                "📱 Quét QR Gửi",
                "📥 Tiếp Nhận Hàng",
                "🚚 Lộ Trình",
                "📊 Dashboard",
            ],
            label_visibility="collapsed",
        )
        
        st.markdown("---")
        st.markdown(
            """
            <div style="padding: 1rem 0; font-size: 0.875rem; color: var(--text-secondary); text-align: center;">
                Hệ Thống Quản Lý<br>Giao Nhận
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    # Route to pages
    if "Trang Chủ" in page or "🏠" in page:
        page_home()
    elif "Quét QR Gửi" in page or "📱" in page:
        page_send()
    elif "Tiếp Nhận Hàng" in page or "📥" in page:
        page_receive()
    elif "Lộ Trình" in page or "🚚" in page:
        page_tracking()
    elif "Dashboard" in page or "📊" in page:
        page_dashboard()


if __name__ == "__main__":
    main()

