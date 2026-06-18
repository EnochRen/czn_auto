#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# controller.py - Windows输入模拟模块

import time
import ctypes
from ctypes import wintypes
from typing import Tuple, List

user32 = ctypes.windll.user32

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000


class InputSimulator:
    def __init__(self, backend: str = "sendinput", target_hwnd: int = 0):
        self.backend = backend
        self._hwnd = target_hwnd
        self.keep_mouse = False
        if backend in ("postmessage", "sendmessage") and not target_hwnd:
            self._find_window()

    def _find_window(self):
        import json
        from pathlib import Path
        cfg_path = Path(__file__).parent / "config.json"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            title = cfg.get("game", {}).get("window_title", "卡厄思梦境")
            self._hwnd = user32.FindWindowW(None, title)
            if self._hwnd:
                import logging
                logging.getLogger(__name__).info(f"已找到窗口 HWND={self._hwnd}")

    def _sendmessage_click(self, x: int, y: int):
        old_pos = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(old_pos))
        user32.SetCursorPos(x, y)
        time.sleep(0.01)
        lparam = (y << 16) | (x & 0xFFFF)
        user32.SendMessageW(self._hwnd, WM_LBUTTONDOWN, 1, lparam)
        time.sleep(0.02)
        user32.SendMessageW(self._hwnd, WM_LBUTTONUP, 0, lparam)
        user32.SetCursorPos(old_pos.x, old_pos.y)

    def move_mouse_abs(self, x: int, y: int, screen_w: int = 1920, screen_h: int = 1080):
        abs_x = int(x * 65535 / screen_w)
        abs_y = int(y * 65535 / screen_h)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = abs_x
        inp.union.mi.dy = abs_y
        inp.union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
        inp.union.mi.time = 0
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def click_at(self, x: int, y: int, screen_w: int = 1920, screen_h: int = 1080):
        if self.backend == "sendmessage":
            self._sendmessage_click(x, y)
            return
        old_pos = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(old_pos))
        self.move_mouse_abs(x, y, screen_w, screen_h)
        time.sleep(0.03)
        down = INPUT()
        down.type = INPUT_MOUSE
        down.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
        user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(down))
        time.sleep(0.02)
        up = INPUT()
        up.type = INPUT_MOUSE
        up.union.mi.dwFlags = MOUSEEVENTF_LEFTUP
        user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(up))
        if not self.keep_mouse:
            user32.SetCursorPos(old_pos.x, old_pos.y)

    def click_config(self, key: str, res: Tuple[int, int], config):
        pts = config.click_points.get(key)
        if not pts:
            return
        x, y = pts
        cx = int(x * res[0] / config.base_res[0])
        cy = int(y * res[1] / config.base_res[1])
        self.click_at(cx, cy, res[0], res[1])

    def click_coord(self, x: int, y: int, res: Tuple[int, int]):
        self.click_at(x, y, res[0], res[1])

    def click_region_center(self, region: List[int], res: Tuple[int, int]):
        x, y, w, h = region
        self.click_at(x + w // 2, y + h // 2, res[0], res[1])
