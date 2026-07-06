#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
msg_send 测试命令可视化查询工具 (GUI v3)

功能：
  1. 自动扫描代码库：Warning / Chime / All Signals 三个告警模块
  2. 仪表盘模块：速度表 / 能量续航 / 档位 / 车门车身 / 胎压 / 充电 / 温度时间
  3. 手动输入信号 ID 生成命令；支持在 Warning/Chime 标签手动新增自定义条目
  4. 自定义条目持久化（tools/custom_entries.json）
  5. 实时搜索过滤 + 一键复制
"""

import os
import re
import sys
import json
import argparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ─────────────────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
CUSTOM_ENTRIES_FILE = os.path.join(SCRIPT_DIR, "custom_entries.json")

PATHS = {
    "signal_defs_cluster":   "framework/cluster_api/clusterapi_tsdl/src/SignalDefs.h",
    "signal_defs_chime":     "framework/chime_player/chime_tsdl/src/SignalDefs.h",
    "warning_table":         "framework/cluster_api/control/Warning/WarningTable.cpp",
    "warning_service":       "framework/cluster_api/control/Warning/WarningService.cpp",
    "chime_signal_service":  "framework/chime_player/src/ChimeSignalService.cpp",
    "chime_listener":        "framework/chime_player/chime_tsdl/src/ChimeMcuComListener.cpp",
    "signal_defs_cluster2":  "framework2/cluster_api/clusterapi_tsdl/src/SignalDefs.h",
    "signal_defs_chime2":    "framework2/chime_player/chime_tsdl/src/SignalDefs.h",
    "warning_table2":        "framework2/cluster_api/control/Warning/WarningTable.cpp",
    "warning_service2":      "framework2/cluster_api/control/Warning/WarningService.cpp",
    "chime_listener2":       "framework2/cluster_api/clusterapi_tsdl/src/ClusterApiMcuComListener.cpp",
}


def abs_path(repo_root: str, key: str) -> str:
    return os.path.join(repo_root, PATHS[key])


def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 解析器
# ─────────────────────────────────────────────────────────────────────────────

def parse_signal_defs(*paths) -> dict:
    """解析 SignalDefs.h，返回 {signal_name: int_id}（TX_SIG_ 和 RX_SIG_ 均支持）"""
    result = {}
    pattern = re.compile(
        r'\b(?:TX_SIG_|RX_SIG_)(\w+)\s*=\s*(0[xX][0-9A-Fa-f]+)',
        re.MULTILINE
    )
    for path in paths:
        text = read_file(path)
        for m in pattern.finditer(text):
            name   = m.group(1)
            sig_id = int(m.group(2), 16)
            result[name] = sig_id
    return result


def parse_warning_table(*paths) -> dict:
    """解析 WarningTable.cpp，返回 {WARN_ID_xxx: {desc, disp_id, disp_state}}"""
    result = {}
    block_pat = re.compile(
        r'//([^\n]+)\n\s*\{\s*WarnID::(\w+)\s*,\s*(\d+)\s*,\s*(\d+)',
        re.MULTILINE
    )
    for path in paths:
        text = read_file(path)
        for m in block_pat.finditer(text):
            result[m.group(2)] = {
                "desc":       m.group(1).strip(),
                "disp_id":    int(m.group(3)),
                "disp_state": int(m.group(4)),
            }
    return result


def _parse_int_token(s: str) -> int:
    return int(s, 16) if s.startswith(("0x", "0X")) else int(s)


def parse_warning_service(*paths) -> list:
    """
    解析 WarningService.cpp，每个 process 函数的 showState 条件 → WARN_ID。
    支持单函数多 WARN_ID 情形。
    """
    entries = []
    func_pat = re.compile(
        r'void\s+\w+::process(\w+)\s*\([^)]*\)\s*\{(.*?)(?=\nvoid\s+\w+::|$)',
        re.DOTALL
    )
    trigger_pat = re.compile(
        r'(?:const\s+uint8_t\s+)?showState\s*=\s*[\s(]*'
        r'm(\w+)\s*(==|>=|<=)\s*(0[xX][0-9A-Fa-f]+|\d+)'
    )
    active_pat = re.compile(
        r'(?:const\s+bool\s+)?active\s*=\s*[\s(]*'
        r'm(\w+)\s*(==|>=|<=)\s*(0[xX][0-9A-Fa-f]+|\d+)'
    )
    warn_id_assign_pat = re.compile(r'(WARN_ID_\w+)')

    for path in paths:
        text = read_file(path)
        for m in func_pat.finditer(text):
            body  = m.group(2)
            lines = body.split('\n')

            warn_positions = []
            for i, line in enumerate(lines):
                for wm in warn_id_assign_pat.finditer(line):
                    warn_positions.append((i, wm.group(1)))

            if not warn_positions:
                continue

            show_positions = []
            for i, line in enumerate(lines):
                tm = trigger_pat.search(line)
                if not tm:
                    tm = active_pat.search(line)
                if tm:
                    show_positions.append((i, tm.group(1), tm.group(2),
                                           _parse_int_token(tm.group(3))))

            if not show_positions:
                continue

            warn_groups: dict = {}
            for si, sv, op, val in show_positions:
                closest_warn = None
                closest_dist = 9999
                for wi, wid in warn_positions:
                    if wi >= si and (wi - si) < closest_dist:
                        closest_dist = wi - si
                        closest_warn = wid
                if closest_warn is None:
                    closest_warn = warn_positions[0][1]
                if closest_warn not in warn_groups:
                    warn_groups[closest_warn] = []
                key = (sv, val)
                if key not in [(x[0], x[2]) for x in warn_groups[closest_warn]]:
                    warn_groups[closest_warn].append((sv, op, val))

            for warn_id, trig_list in warn_groups.items():
                if not trig_list:
                    continue
                first_val = trig_list[0][2]
                entries.append({
                    "warn_id_enum": warn_id,
                    "signal_var":   trig_list[0][0],
                    "triggers":     trig_list,
                    "reset_val":    0 if first_val != 0 else 1,
                })

    return entries


def _fuzzy_sig_lookup(sig_map: dict, var_name: str):
    """模糊匹配 WarningService 变量名 vs SignalDefs 枚举名（忽略大小写和下划线）"""
    if var_name in sig_map:
        return sig_map[var_name]
    var_lower = var_name.lower()
    for k, v in sig_map.items():
        if k.lower() == var_lower:
            return v
    var_stripped = var_name.replace("_", "").lower()
    for k, v in sig_map.items():
        if k.replace("_", "").lower() == var_stripped:
            return v
    for k, v in sig_map.items():
        k_s = k.replace("_", "").lower()
        if var_stripped in k_s or k_s in var_stripped:
            return v
    return None


def build_warning_data(repo_root: str, sig_map: dict) -> list:
    warn_props = parse_warning_table(
        abs_path(repo_root, "warning_table"),
        abs_path(repo_root, "warning_table2"),
    )
    svc_entries = parse_warning_service(
        abs_path(repo_root, "warning_service"),
        abs_path(repo_root, "warning_service2"),
    )

    results = []
    seen = set()
    for svc in svc_entries:
        warn_enum = svc["warn_id_enum"]
        if warn_enum in seen:
            continue
        seen.add(warn_enum)

        props  = warn_props.get(warn_enum, {})
        sig_id = _fuzzy_sig_lookup(sig_map, svc["signal_var"])
        if sig_id is None:
            continue

        triggers_out = [(val, f"m{sv} {op} 0x{val:X}")
                        for sv, op, val in svc["triggers"]]
        results.append({
            "module":     "Warning",
            "desc":       props.get("desc", warn_enum),
            "disp_id":    props.get("disp_id", 0),
            "disp_state": props.get("disp_state", 0),
            "signal":     svc["signal_var"],
            "sig_id":     sig_id,
            "triggers":   triggers_out,
            "reset":      svc["reset_val"],
            "note":       "",
            "user_added": False,
        })
    return results


def build_chime_data(repo_root: str, sig_map: dict) -> list:
    chime_sig_map = parse_signal_defs(
        abs_path(repo_root, "signal_defs_chime"),
        abs_path(repo_root, "signal_defs_chime2"),
    )
    chime_sig_map.update(sig_map)  # merge cluster signals too

    chime_data = read_file(abs_path(repo_root, "chime_signal_service"))

    func_pat = re.compile(
        r'void\s+\w+::process(\w+Chime)\s*\([^)]*\)\s*\{(.*?)(?=\nvoid\s+\w+::|$)',
        re.DOTALL
    )
    trigger_pat = re.compile(
        r'm(\w+)\s*(==|>=|<=)\s*(0[xX][0-9A-Fa-f]+|\d+)'
    )
    chime_id_pat = re.compile(r'CHIME_AUDIO_ID_(\w+)')

    results = []
    for m in func_pat.finditer(chime_data):
        func_name = m.group(1)
        body      = m.group(2)

        chime_ids = list(dict.fromkeys(chime_id_pat.findall(body)))
        triggers  = []
        seen_vals = set()
        sig_var   = None
        for tm in trigger_pat.finditer(body):
            sv  = tm.group(1)
            op  = tm.group(2)
            val = int(tm.group(3), 16) if tm.group(3).startswith(("0x","0X")) else int(tm.group(3))
            if sv in ("UsgModeSts", "CarModeSts", "PwrLv"):
                continue
            if sig_var is None:
                sig_var = sv
            key = (sv, val)
            if key not in seen_vals:
                seen_vals.add(key)
                triggers.append((sv, op, val))

        if not sig_var or not triggers:
            continue

        sig_id = _fuzzy_sig_lookup(chime_sig_map, sig_var)
        if sig_id is None:
            continue

        triggers_out = [(val, f"m{sv} {op} 0x{val:X}") for sv, op, val in triggers]
        results.append({
            "module":     "Chime",
            "desc":       f"[{'/'.join(chime_ids)}] {func_name}",
            "disp_id":    0,
            "disp_state": 0,
            "signal":     sig_var,
            "sig_id":     sig_id,
            "triggers":   triggers_out,
            "reset":      0 if triggers[0][2] != 0 else 1,
            "note":       "",
            "user_added": False,
        })
    return results


def build_all_signals(sig_map: dict, known_ids: set) -> list:
    results = []
    for name, sig_id in sorted(sig_map.items(), key=lambda x: x[1]):
        results.append({
            "module":     "Signal",
            "desc":       name,
            "disp_id":    0,
            "disp_state": 0,
            "signal":     name,
            "sig_id":     sig_id,
            "triggers":   [],
            "reset":      0,
            "note":       "来自 SignalDefs.h，无触发逻辑" if sig_id not in known_ids else "",
            "user_added": False,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 自定义条目持久化
# ─────────────────────────────────────────────────────────────────────────────

def load_custom_entries() -> dict:
    """加载 custom_entries.json，返回 {module: [entry, ...]}"""
    if not os.path.exists(CUSTOM_ENTRIES_FILE):
        return {}
    try:
        with open(CUSTOM_ENTRIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # ensure each entry has user_added flag
        for entries in data.values():
            for e in entries:
                e["user_added"] = True
        return data
    except Exception:
        return {}


def save_custom_entries(custom: dict):
    """保存 custom_entries.json"""
    try:
        # only save user_added entries
        to_save = {}
        for module, entries in custom.items():
            to_save[module] = [e for e in entries if e.get("user_added")]
        with open(CUSTOM_ENTRIES_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        messagebox.showerror("保存失败", str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# 仪表盘模块静态数据
# ─────────────────────────────────────────────────────────────────────────────

INSTRUMENT_MODULES = [
    {
        "tab_name": "🚗 速度表",
        "signals": [
            {"desc": "车速显示值",       "signal": "VehicleSpdDisplay",
             "quick_vals": [(0,"停车"),(20,"20 km/h"),(40,"40 km/h"),(60,"60 km/h"),
                            (80,"80 km/h"),(100,"100 km/h"),(120,"120 km/h"),(160,"160 km/h"),(200,"200 km/h")],
             "note": "仪表盘显示车速，原始值 = km/h（1:1）"},
            {"desc": "实际车速",         "signal": "VehicleSpeed",
             "quick_vals": [(0,"停车"),(20,"20 km/h"),(60,"60 km/h"),(100,"100 km/h"),(120,"120 km/h")],
             "note": "实际行驶车速"},
            {"desc": "车速显示有效",     "signal": "VehicleSpdDisplayValid",
             "quick_vals": [(1,"有效"),(0,"无效")],
             "note": "0=无效，1=有效"},
            {"desc": "车速有效",         "signal": "VehicleSpeedValid",
             "quick_vals": [(1,"有效"),(0,"无效")],
             "note": ""},
            {"desc": "车辆静止标志",     "signal": "VehicleStandstill",
             "quick_vals": [(1,"静止"),(0,"行驶中")],
             "note": ""},
        ],
    },
    {
        "tab_name": "⛽ 能量续航",
        "signals": [
            {"desc": "SOC 电量显示",     "signal": "DispHvBattLvlOfChrg",
             "quick_vals": [(0,"0%"),(10,"10%"),(20,"20%"),(50,"50%"),(80,"80%"),(100,"100%")],
             "note": "高压电池 SOC 显示值"},
            {"desc": "综合续航里程",     "signal": "DstEstimdToEmptyForDrvgTot",
             "quick_vals": [(0,"0 km"),(50,"50 km"),(100,"100 km"),(200,"200 km"),(255,"255 km")],
             "note": "总续航里程估算"},
            {"desc": "纯电续航里程",     "signal": "DstEstimdToEmptyForDrvgElec",
             "quick_vals": [(0,"0 km"),(50,"50 km"),(100,"100 km"),(200,"200 km")],
             "note": ""},
            {"desc": "燃油续航里程",     "signal": "DstEstimdToEmptyForDrvgEng",
             "quick_vals": [(0,"0 km"),(50,"50 km"),(100,"100 km"),(200,"200 km")],
             "note": ""},
            {"desc": "燃油精确值",       "signal": "FuelOilPrec",
             "quick_vals": [(0,"空"),(25,"1/4 箱"),(50,"1/2 箱"),(75,"3/4 箱"),(100,"满")],
             "note": "燃油量百分比 0–100"},
            {"desc": "瞬时能耗",         "signal": "DynEgyConsInst",
             "quick_vals": [(0,"0"),(20,"20"),(50,"50"),(100,"100"),(200,"200")],
             "note": ""},
            {"desc": "能量管理模式",     "signal": "EgyModAct",
             "quick_vals": [(0,"Eco"),(1,"Normal"),(2,"Sport"),(3,"Custom"),(4,"Electric")],
             "note": ""},
        ],
    },
    {
        "tab_name": "⚙ 档位",
        "signals": [
            {"desc": "档位显示",         "signal": "GearLvrIndcn",
             "quick_vals": [(0,"无/默认"),(1,"P 停车"),(2,"R 倒车"),(3,"N 空挡"),
                            (4,"D 前进"),(5,"S 运动")],
             "note": "仪表盘档位指示"},
            {"desc": "驱动模式状态",     "signal": "PrpsnModSts",
             "quick_vals": [(0,"正常"),(1,"运动"),(2,"雪地"),(3,"越野")],
             "note": ""},
        ],
    },
    {
        "tab_name": "🚪 车门车身",
        "signals": [
            {"desc": "主驾车门",         "signal": "DoorDrvrSts",
             "quick_vals": [(0,"关闭"),(1,"打开"),(2,"半开")], "note": ""},
            {"desc": "副驾车门",         "signal": "DoorPassSts",
             "quick_vals": [(0,"关闭"),(1,"打开")], "note": ""},
            {"desc": "左后车门",         "signal": "DoorLeReSts",
             "quick_vals": [(0,"关闭"),(1,"打开")], "note": ""},
            {"desc": "右后车门",         "signal": "DoorRiReSts",
             "quick_vals": [(0,"关闭"),(1,"打开")], "note": ""},
            {"desc": "引擎盖",           "signal": "HoodSts",
             "quick_vals": [(0,"关闭"),(1,"打开")], "note": ""},
            {"desc": "后备箱",           "signal": "TrSts",
             "quick_vals": [(0,"关闭"),(1,"打开")], "note": ""},
        ],
    },
    {
        "tab_name": "🔴 胎压 TPMS",
        "signals": [
            {"desc": "左前轮胎压",       "signal": "TPMS_FLTyreP",
             "quick_vals": [(0,"0 kPa"),(200,"200 kPa"),(230,"230 kPa"),(250,"250 kPa")],
             "note": "单位 kPa"},
            {"desc": "右前轮胎压",       "signal": "TPMS_FRTyreP",
             "quick_vals": [(0,"0 kPa"),(200,"200 kPa"),(230,"230 kPa"),(250,"250 kPa")],
             "note": ""},
            {"desc": "左后轮胎压",       "signal": "TPMS_RLTyreP",
             "quick_vals": [(0,"0 kPa"),(200,"200 kPa"),(230,"230 kPa"),(250,"250 kPa")],
             "note": ""},
            {"desc": "右后轮胎压",       "signal": "TPMS_RRTyreP",
             "quick_vals": [(0,"0 kPa"),(200,"200 kPa"),(230,"230 kPa"),(250,"250 kPa")],
             "note": ""},
            {"desc": "左前胎温",         "signal": "TPMS_FLTyreT",
             "quick_vals": [(25,"25°C"),(60,"60°C"),(80,"80°C"),(100,"100°C")],
             "note": "单位 °C"},
            {"desc": "右前胎温",         "signal": "TPMS_FRTyreT",
             "quick_vals": [(25,"25°C"),(60,"60°C"),(80,"80°C")], "note": ""},
            {"desc": "左后胎温",         "signal": "TPMS_RLTyreT",
             "quick_vals": [(25,"25°C"),(60,"60°C"),(80,"80°C")], "note": ""},
            {"desc": "右后胎温",         "signal": "TPMS_RRTyreT",
             "quick_vals": [(25,"25°C"),(60,"60°C"),(80,"80°C")], "note": ""},
            {"desc": "左前胎压告警",     "signal": "TPMS_FLWarn",
             "quick_vals": [(0,"正常"),(1,"低压告警"),(2,"严重告警")], "note": ""},
            {"desc": "右前胎压告警",     "signal": "TPMS_FRWarn",
             "quick_vals": [(0,"正常"),(1,"低压告警")], "note": ""},
            {"desc": "左后胎压告警",     "signal": "TPMS_RLWarn",
             "quick_vals": [(0,"正常"),(1,"低压告警")], "note": ""},
            {"desc": "右后胎压告警",     "signal": "TPMS_RRWarn",
             "quick_vals": [(0,"正常"),(1,"低压告警")], "note": ""},
        ],
    },
    {
        "tab_name": "🔋 充电",
        "signals": [
            {"desc": "直流充电状态",         "signal": "DCChrgSt",
             "quick_vals": [(0,"未充电"),(1,"准备中"),(2,"充电中"),(3,"充电完成"),(4,"故障")],
             "note": ""},
            {"desc": "充电枪连接状态",       "signal": "DCChrgnHndlStsE2EDCChrgnHndlStsE2E",
             "quick_vals": [(0,"未连接"),(1,"已连接"),(2,"充电中")],
             "note": "DC 充电连接状态"},
            {"desc": "CDU1 充放电工作状态",  "signal": "CDU1_Chrg_DischrgWorkSts",
             "quick_vals": [(0,"待机"),(1,"充电"),(2,"放电"),(3,"故障")],
             "note": ""},
            {"desc": "高压电池充电电流",     "signal": "HvBattIDc",
             "quick_vals": [(0,"0 A"),(50,"50 A"),(100,"100 A"),(200,"200 A")],
             "note": "单位 A"},
            {"desc": "高压电池充电电压",     "signal": "HvBattUDc",
             "quick_vals": [(0,"0 V"),(200,"200 V"),(255,"255 V")],
             "note": "单位 V"},
            {"desc": "预计充满剩余时间",     "signal": "HvBattChrgnTiEstimd",
             "quick_vals": [(0,"0 min"),(30,"30 min"),(60,"60 min"),(120,"120 min"),(255,"255 min")],
             "note": "单位 min"},
        ],
    },
    {
        "tab_name": "🌡 温度时间",
        "signals": [
            {"desc": "车外温度",         "signal": "TmsOutsideTemp",
             "quick_vals": [(0,"0°C"),(20,"20°C"),(25,"25°C"),(40,"40°C"),(50,"50°C")],
             "note": "单位 °C（带偏移，视协议定义）"},
            {"desc": "车外温度有效",     "signal": "TmsOutsideTempValid",
             "quick_vals": [(1,"有效"),(0,"无效")], "note": ""},
            {"desc": "UTC 小时",         "signal": "TboxTimeHour_UTC",
             "quick_vals": [(0,"0时"),(6,"6时"),(12,"12时"),(18,"18时"),(23,"23时")],
             "note": "0–23"},
            {"desc": "UTC 分钟",         "signal": "TboxTimeMinute_UTC",
             "quick_vals": [(0,"0分"),(15,"15分"),(30,"30分"),(45,"45分"),(59,"59分")],
             "note": "0–59"},
            {"desc": "UTC 秒",           "signal": "TboxTimeSecond_UTC",
             "quick_vals": [(0,"0秒"),(30,"30秒"),(59,"59秒")], "note": ""},
            {"desc": "行驶里程 (RX)",    "signal": "Odometer",
             "quick_vals": [(0,"0 km"),(50,"50 km"),(100,"100 km"),(200,"200 km"),(255,"255 km")],
             "note": "RX_SIG_Odometer (0x0104A05A)"},
        ],
    },
]


def build_instrument_data(sig_map: dict) -> list:
    """将 INSTRUMENT_MODULES 与 sig_map 结合，生成仪表盘模块条目列表。"""
    modules = []
    for mod_def in INSTRUMENT_MODULES:
        entries = []
        for sig in mod_def["signals"]:
            name   = sig["signal"]
            sig_id = sig_map.get(name)
            if sig_id is None:
                # 尝试模糊匹配
                sig_id = _fuzzy_sig_lookup(sig_map, name)
            entries.append({
                "module":      mod_def["tab_name"],
                "desc":        sig["desc"],
                "signal":      name,
                "sig_id":      sig_id,   # may be None if not found
                "quick_vals":  sig["quick_vals"],
                "note":        sig.get("note", ""),
            })
        modules.append({"tab_name": mod_def["tab_name"], "entries": entries})
    return modules


def scan_all(repo_root: str) -> dict:
    """扫描所有模块，返回 {module: data, ...} + sig_map"""
    sig_map = parse_signal_defs(
        abs_path(repo_root, "signal_defs_cluster"),
        abs_path(repo_root, "signal_defs_cluster2"),
        abs_path(repo_root, "signal_defs_chime"),
        abs_path(repo_root, "signal_defs_chime2"),
    )

    warnings = build_warning_data(repo_root, sig_map)
    chimes   = build_chime_data(repo_root, sig_map)
    known_ids = {e["sig_id"] for e in warnings + chimes}
    all_sigs  = build_all_signals(sig_map, known_ids)
    instruments = build_instrument_data(sig_map)

    # merge custom entries
    custom = load_custom_entries()
    for module_name, custom_entries in custom.items():
        if module_name == "Warning":
            warnings.extend(custom_entries)
        elif module_name == "Chime":
            chimes.extend(custom_entries)

    return {
        "Warning":     warnings,
        "Chime":       chimes,
        "All":         all_sigs,
        "Instruments": instruments,
        "sig_map":     sig_map,
    }


# ─────────────────────────────────────────────────────────────────────────────
# msg_send 命令生成
# ─────────────────────────────────────────────────────────────────────────────

def make_cmd(sig_id: int, value: int) -> str:
    lo = sig_id & 0xFF
    return f"msg_send 2 4 1 160 {lo} 0 0 0 0 0 {value} 0 0 0"


# ─────────────────────────────────────────────────────────────────────────────
# GUI 调色板
# ─────────────────────────────────────────────────────────────────────────────

PALETTE = {
    "bg":        "#1E1E2E",
    "panel":     "#24243A",
    "card":      "#313145",
    "sep":       "#45475A",
    "highlight": "#89B4FA",
    "accent":    "#A6E3A1",
    "warn_color":"#FAB387",
    "chime_clr": "#F5C2E7",
    "text":      "#CDD6F4",
    "subtext":   "#7F849C",
    "entry_bg":  "#45475A",
    "entry_fg":  "#FFFFFF",
    "btn_bg":    "#585B70",
    "btn_add":   "#3A5A3A",
    "btn_del":   "#5A3A3A",
    "trig_bg":   "#1E2E1E",
    "reset_bg":  "#2E1E1E",
    "copy_ok":   "#A6E3A1",
}
FF = "Monospace"


# ─────────────────────────────────────────────────────────────────────────────
# Widget helpers
# ─────────────────────────────────────────────────────────────────────────────

class CopyableLabel(tk.Frame):
    """带复制按钮的命令行组件"""
    def __init__(self, parent, cmd: str, sublabel: str = "",
                 bg=PALETTE["trig_bg"], **kw):
        super().__init__(parent, bg=bg, pady=3, **kw)
        lf = tk.Frame(self, bg=bg)
        lf.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        if sublabel:
            tk.Label(lf, text=sublabel, bg=bg, fg=PALETTE["subtext"],
                     font=(FF, 9)).pack(anchor="w")
        tk.Label(lf, text=cmd, bg=bg, fg=PALETTE["text"],
                 font=(FF, 12)).pack(anchor="w")
        self._cmd = cmd
        self._orig_bg = bg
        tk.Button(self, text="复制", bg=PALETTE["btn_bg"],
                  fg=PALETTE["text"], relief=tk.FLAT, cursor="hand2",
                  font=(FF, 10), padx=10,
                  command=self._copy).pack(side=tk.RIGHT, padx=8)

    def _copy(self):
        self.winfo_toplevel().clipboard_clear()
        self.winfo_toplevel().clipboard_append(self._cmd)
        orig = self._orig_bg
        self._flash(PALETTE["copy_ok"])
        self.after(500, lambda: self._flash(orig))

    def _flash(self, color: str):
        try:
            self.configure(bg=color)
            for w in self.winfo_children():
                for ww in ([w] + list(w.winfo_children())):
                    try: ww.configure(bg=color)
                    except: pass
        except: pass


class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        bg = kw.get("bg", PALETTE["bg"])
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self._win, width=e.width))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind(seq, self._on_scroll)
            self.inner.bind(seq, self._on_scroll)

    def _on_scroll(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")


# ─────────────────────────────────────────────────────────────────────────────
# 新增告警条目对话框
# ─────────────────────────────────────────────────────────────────────────────

class AddEntryDialog(tk.Toplevel):
    """弹出对话框：手动填写一条 Warning/Chime 条目"""

    def __init__(self, parent, module: str, sig_map: dict, on_confirm):
        super().__init__(parent)
        self.title(f"➕ 新增{module}条目")
        self.configure(bg=PALETTE["bg"])
        self.resizable(False, False)
        self._module    = module
        self._sig_map   = sig_map
        self._on_confirm = on_confirm
        self._result    = None
        self._build()
        self.grab_set()
        self.transient(parent)

    def _make_row(self, container, label, width=24):
        row = tk.Frame(container, bg=PALETTE["bg"])
        row.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(row, text=label, bg=PALETTE["bg"], fg=PALETTE["subtext"],
                 font=(FF, 11), width=width, anchor="e").pack(side=tk.LEFT)
        var = tk.StringVar()
        ent = tk.Entry(row, textvariable=var,
                       bg=PALETTE["entry_bg"], fg=PALETTE["entry_fg"],
                       insertbackground="#fff", relief=tk.FLAT,
                       font=(FF, 12), bd=4, width=30,
                       highlightthickness=1,
                       highlightcolor=PALETTE["highlight"],
                       highlightbackground=PALETTE["sep"])
        ent.pack(side=tk.LEFT, padx=(8, 0))
        return var, ent

    def _build(self):
        tk.Label(self, text=f"新增自定义{self._module}条目",
                 bg=PALETTE["bg"], fg=PALETTE["highlight"],
                 font=(FF, 13, "bold")).pack(pady=(16, 4))
        tk.Frame(self, bg=PALETTE["sep"], height=1).pack(fill=tk.X, padx=20, pady=4)

        self._desc_var,    _ = self._make_row(self, "描述 (中文):")
        self._signal_var,  _ = self._make_row(self, "信号名:")
        self._id_var,      _ = self._make_row(self, "信号 ID (hex/dec):")
        self._disp_var,    _ = self._make_row(self, "dispID (可选):")
        self._trig_var,    _ = self._make_row(self, "触发值 (逗号分隔):")
        self._reset_var,   _ = self._make_row(self, "复位值:")
        self._note_var,    _ = self._make_row(self, "备注:")

        self._reset_var.set("0")

        # auto-fill signal ID when signal name is typed
        self._signal_var.trace_add("write", self._auto_fill_id)

        tk.Label(self, text="* 触发值支持 0x 前缀，多个用逗号分隔，如: 1,2,3 或 0x1,0x2",
                 bg=PALETTE["bg"], fg=PALETTE["subtext"],
                 font=(FF, 9)).pack(anchor="w", padx=20)

        tk.Frame(self, bg=PALETTE["sep"], height=1).pack(fill=tk.X, padx=20, pady=8)

        btn_row = tk.Frame(self, bg=PALETTE["bg"])
        btn_row.pack(pady=(0, 16))
        tk.Button(btn_row, text="取消", bg=PALETTE["btn_bg"], fg=PALETTE["text"],
                  relief=tk.FLAT, cursor="hand2", font=(FF, 12), padx=20,
                  command=self.destroy).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_row, text="✅ 确定", bg=PALETTE["btn_add"], fg="#A6E3A1",
                  relief=tk.FLAT, cursor="hand2", font=(FF, 12), padx=20,
                  command=self._confirm).pack(side=tk.LEFT, padx=8)

    def _auto_fill_id(self, *_):
        name = self._signal_var.get().strip()
        if not name:
            return
        sig_id = self._sig_map.get(name)
        if sig_id is None:
            sig_id = _fuzzy_sig_lookup(self._sig_map, name)
        if sig_id is not None and not self._id_var.get().strip():
            self._id_var.set(f"0x{sig_id:08X}")

    def _confirm(self):
        desc   = self._desc_var.get().strip()
        signal = self._signal_var.get().strip()
        id_str = self._id_var.get().strip()
        trig_s = self._trig_var.get().strip()
        rst_s  = self._reset_var.get().strip() or "0"
        disp_s = self._disp_var.get().strip() or "0"
        note   = self._note_var.get().strip()

        if not desc:
            messagebox.showwarning("输入错误", "描述不能为空", parent=self)
            return
        if not id_str:
            messagebox.showwarning("输入错误", "信号 ID 不能为空", parent=self)
            return

        try:
            sig_id = int(id_str, 0)
        except ValueError:
            messagebox.showwarning("格式错误", f"信号 ID 无效: {id_str}", parent=self)
            return

        triggers = []
        for t in trig_s.split(","):
            t = t.strip()
            if not t:
                continue
            try:
                v = int(t, 0)
                triggers.append((v, f"value=0x{v:X}"))
            except ValueError:
                messagebox.showwarning("格式错误", f"触发值无效: {t}", parent=self)
                return

        try:
            reset_val = int(rst_s, 0)
        except ValueError:
            messagebox.showwarning("格式错误", f"复位值无效: {rst_s}", parent=self)
            return

        try:
            disp_id = int(disp_s, 0)
        except ValueError:
            disp_id = 0

        entry = {
            "module":     self._module,
            "desc":       desc,
            "disp_id":    disp_id,
            "disp_state": 0,
            "signal":     signal or f"0x{sig_id:08X}",
            "sig_id":     sig_id,
            "triggers":   triggers,
            "reset":      reset_val,
            "note":       note,
            "user_added": True,
        }
        self._on_confirm(entry)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Warning / Chime 模块标签页
# ─────────────────────────────────────────────────────────────────────────────

class ModuleTab(tk.Frame):
    """Warning / Chime / All Signals 标签页"""

    def __init__(self, parent, data: list, module: str = "",
                 editable: bool = False, sig_map: dict = None,
                 save_callback=None, **kw):
        super().__init__(parent, bg=PALETTE["bg"], **kw)
        self._all_data      = list(data)
        self._filtered      = list(data)
        self._module        = module
        self._editable      = editable
        self._sig_map       = sig_map or {}
        self._save_callback = save_callback  # called(updated_list) on add/delete
        self._build()

    def _build(self):
        # ── toolbar (search + optional add button)
        top = tk.Frame(self, bg=PALETTE["bg"], pady=8)
        top.pack(fill=tk.X, padx=12)
        tk.Label(top, text="🔍", bg=PALETTE["bg"], fg=PALETTE["highlight"],
                 font=(FF, 13)).pack(side=tk.LEFT)
        self._sv = tk.StringVar()
        self._sv.trace_add("write", lambda *_: self._do_search())
        tk.Entry(top, textvariable=self._sv,
                 bg=PALETTE["entry_bg"], fg=PALETTE["entry_fg"],
                 insertbackground="#fff", relief=tk.FLAT,
                 font=(FF, 12), bd=5,
                 highlightthickness=1,
                 highlightcolor=PALETTE["highlight"],
                 highlightbackground=PALETTE["sep"]).pack(
                     side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 10))
        self._cnt = tk.StringVar()
        tk.Label(top, textvariable=self._cnt, bg=PALETTE["bg"],
                 fg=PALETTE["subtext"], font=(FF, 10)).pack(side=tk.LEFT, padx=4)

        if self._editable:
            tk.Button(top, text="➕ 新增",
                      bg=PALETTE["btn_add"], fg="#A6E3A1",
                      relief=tk.FLAT, cursor="hand2",
                      font=(FF, 10), padx=10,
                      command=self._open_add_dialog).pack(side=tk.LEFT, padx=(8, 0))

        # ── paned split
        pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=PALETTE["bg"], sashwidth=4)
        pane.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        # left tree
        lf = tk.Frame(pane, bg=PALETTE["panel"])
        pane.add(lf, minsize=300, width=380)
        cols = ("desc", "signal", "disp_id")
        self._tree = ttk.Treeview(lf, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("desc",    text="描述 / 信号名")
        self._tree.heading("signal",  text="信号")
        self._tree.heading("disp_id", text="dispID")
        self._tree.column("desc",    width=190, anchor="w")
        self._tree.column("signal",  width=150, anchor="w")
        self._tree.column("disp_id", width=55,  anchor="center")
        vsb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # right detail
        self._detail_host = tk.Frame(pane, bg=PALETTE["bg"])
        pane.add(self._detail_host, minsize=380)
        self._show_placeholder()

        self._refresh_list(self._all_data)

    # ── list ─────────────────────────────────────────────────────────────────

    def _refresh_list(self, data):
        self._tree.delete(*self._tree.get_children())
        self._filtered = data
        for e in data:
            tag = "user" if e.get("user_added") else ""
            iid = self._tree.insert("", tk.END,
                                    values=(e["desc"], e["signal"],
                                            e["disp_id"] or ""),
                                    tags=(tag,))
        self._tree.tag_configure("user", foreground=PALETTE["accent"])
        self._cnt.set(f"{len(data)} 条")
        self._show_placeholder()

    def _do_search(self):
        kw = self._sv.get().strip().lower()
        if not kw:
            self._refresh_list(self._all_data)
            return
        hits = [e for e in self._all_data
                if (kw in e["desc"].lower()
                    or kw in e["signal"].lower()
                    or kw == str(e["disp_id"])
                    or kw == f"0x{e['sig_id']:08x}"
                    or kw == f"0x{e['sig_id']:08X}"
                    or kw == str(e["sig_id"] & 0xFF))]
        self._refresh_list(hits)
        kids = self._tree.get_children()
        if kids:
            self._tree.selection_set(kids[0])
            self._tree.focus(kids[0])

    def _on_select(self, _=None):
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        if idx < len(self._filtered):
            self._render_detail(self._filtered[idx])

    # ── add / delete ─────────────────────────────────────────────────────────

    def _open_add_dialog(self):
        AddEntryDialog(self.winfo_toplevel(),
                       module=self._module,
                       sig_map=self._sig_map,
                       on_confirm=self._on_entry_added)

    def _on_entry_added(self, entry: dict):
        self._all_data.append(entry)
        self._refresh_list(self._all_data)
        if self._save_callback:
            self._save_callback(self._module, self._all_data)

    def _delete_entry(self, entry: dict):
        if not messagebox.askyesno("确认删除", f"确定要删除【{entry['desc']}】吗？",
                                    parent=self.winfo_toplevel()):
            return
        self._all_data = [e for e in self._all_data if e is not entry]
        self._filtered = [e for e in self._filtered if e is not entry]
        self._refresh_list(self._all_data)
        if self._save_callback:
            self._save_callback(self._module, self._all_data)

    # ── detail ────────────────────────────────────────────────────────────────

    def _show_placeholder(self):
        for w in self._detail_host.winfo_children():
            w.destroy()
        tk.Label(self._detail_host, text="← 选择条目查看详情",
                 bg=PALETTE["bg"], fg=PALETTE["subtext"],
                 font=(FF, 12)).pack(expand=True)

    def _render_detail(self, e: dict):
        for w in self._detail_host.winfo_children():
            w.destroy()

        sf = ScrollableFrame(self._detail_host, bg=PALETTE["bg"])
        sf.pack(fill=tk.BOTH, expand=True)
        inn = sf.inner

        pad = {"padx": 16, "pady": 3}

        # title row
        hdr_row = tk.Frame(inn, bg=PALETTE["bg"])
        hdr_row.pack(fill=tk.X, padx=16, pady=(12, 4))
        tk.Label(hdr_row, text=e["desc"], bg=PALETTE["bg"],
                 fg=PALETTE["highlight"],
                 font=(FF, 14, "bold"),
                 wraplength=460, justify="left").pack(side=tk.LEFT)
        if e.get("user_added") and self._editable:
            tk.Button(hdr_row, text="🗑 删除", bg=PALETTE["btn_del"],
                      fg="#FAB387", relief=tk.FLAT, cursor="hand2",
                      font=(FF, 10), padx=8,
                      command=lambda: self._delete_entry(e)).pack(side=tk.RIGHT)
        if e.get("user_added"):
            tk.Label(hdr_row, text=" ★ 自定义", bg=PALETTE["bg"],
                     fg=PALETTE["accent"], font=(FF, 10)).pack(side=tk.RIGHT)

        def sep():
            tk.Frame(inn, bg=PALETTE["sep"], height=1).pack(fill=tk.X, padx=16, pady=4)

        def kv(k, v, vc=PALETTE["text"]):
            row = tk.Frame(inn, bg=PALETTE["bg"])
            row.pack(fill=tk.X, **pad)
            tk.Label(row, text=f"{k}:", width=13, anchor="e",
                     bg=PALETTE["bg"], fg=PALETTE["subtext"],
                     font=(FF, 11)).pack(side=tk.LEFT)
            tk.Label(row, text=v, anchor="w",
                     bg=PALETTE["bg"], fg=vc,
                     font=(FF, 12, "bold")).pack(side=tk.LEFT, padx=6)

        sep()
        kv("模块",   e["module"])
        kv("信号名", e["signal"], PALETTE["accent"])
        if e["sig_id"] is not None:
            kv("信号ID", f"0x{e['sig_id']:08X}  (lo byte dec = {e['sig_id'] & 0xFF})",
               PALETTE["warn_color"])
        if e["disp_id"]:
            kv("dispID",    str(e["disp_id"]))
            kv("dispState", str(e["disp_state"]))
        if e.get("note"):
            tk.Label(inn, text=f"ℹ  {e['note']}",
                     bg=PALETTE["bg"], fg=PALETTE["subtext"],
                     font=(FF, 10), wraplength=520, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 4))

        if e["sig_id"] is None:
            tk.Label(inn, text="⚠ 未在 SignalDefs.h 中找到该信号 ID",
                     bg=PALETTE["bg"], fg=PALETTE["warn_color"],
                     font=(FF, 11)).pack(anchor="w", padx=16)
            return

        if e["triggers"]:
            sep()
            tk.Label(inn, text="触发命令", bg=PALETTE["bg"],
                     fg=PALETTE["highlight"],
                     font=(FF, 12, "bold")).pack(anchor="w", padx=16, pady=(0, 3))
            for val, note in e["triggers"]:
                cmd = make_cmd(e["sig_id"], val)
                CopyableLabel(inn, cmd, sublabel=f"value=0x{val:X}  ({note})",
                              bg=PALETTE["trig_bg"]).pack(fill=tk.X, padx=16, pady=2)

        sep()
        tk.Label(inn, text="复位命令", bg=PALETTE["bg"],
                 fg=PALETTE["warn_color"],
                 font=(FF, 12, "bold")).pack(anchor="w", padx=16, pady=(0, 3))
        rst = e.get("reset", 0)
        CopyableLabel(inn, make_cmd(e["sig_id"], rst),
                      sublabel=f"value=0x{rst:X}",
                      bg=PALETTE["reset_bg"]).pack(fill=tk.X, padx=16, pady=2)


# ─────────────────────────────────────────────────────────────────────────────
# 仪表盘模块标签页
# ─────────────────────────────────────────────────────────────────────────────

class InstrumentTab(tk.Frame):
    """仪表盘类模块标签页：左信号列表 + 右快速值按钮 + 自定义值输入"""

    def __init__(self, parent, entries: list, **kw):
        super().__init__(parent, bg=PALETTE["bg"], **kw)
        self._entries   = entries
        self._filtered  = entries
        self._cur_entry = None
        self._build()

    def _build(self):
        # ── search bar
        top = tk.Frame(self, bg=PALETTE["bg"], pady=8)
        top.pack(fill=tk.X, padx=12)
        tk.Label(top, text="🔍", bg=PALETTE["bg"], fg=PALETTE["highlight"],
                 font=(FF, 13)).pack(side=tk.LEFT)
        self._sv = tk.StringVar()
        self._sv.trace_add("write", lambda *_: self._do_search())
        tk.Entry(top, textvariable=self._sv,
                 bg=PALETTE["entry_bg"], fg=PALETTE["entry_fg"],
                 insertbackground="#fff", relief=tk.FLAT,
                 font=(FF, 12), bd=5,
                 highlightthickness=1,
                 highlightcolor=PALETTE["highlight"],
                 highlightbackground=PALETTE["sep"]).pack(
                     side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 10))
        self._cnt = tk.StringVar()
        tk.Label(top, textvariable=self._cnt, bg=PALETTE["bg"],
                 fg=PALETTE["subtext"], font=(FF, 10)).pack(side=tk.LEFT)

        # ── paned
        pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=PALETTE["bg"], sashwidth=4)
        pane.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        # left: signal list
        lf = tk.Frame(pane, bg=PALETTE["panel"])
        pane.add(lf, minsize=260, width=300)
        cols = ("desc", "signal")
        self._tree = ttk.Treeview(lf, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("desc",   text="信号描述")
        self._tree.heading("signal", text="信号名")
        self._tree.column("desc",   width=150, anchor="w")
        self._tree.column("signal", width=140, anchor="w")
        vsb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # right: control panel
        self._right = tk.Frame(pane, bg=PALETTE["bg"])
        pane.add(self._right, minsize=420)
        self._show_placeholder()

        self._refresh_list(self._entries)

    def _refresh_list(self, data):
        self._tree.delete(*self._tree.get_children())
        self._filtered = data
        for e in data:
            tag = "" if e["sig_id"] else "missing"
            self._tree.insert("", tk.END, values=(e["desc"], e["signal"]), tags=(tag,))
        self._tree.tag_configure("missing", foreground=PALETTE["subtext"])
        self._cnt.set(f"{len(data)} 个信号")

    def _do_search(self):
        kw = self._sv.get().strip().lower()
        if not kw:
            self._refresh_list(self._entries)
            return
        hits = [e for e in self._entries
                if kw in e["desc"].lower() or kw in e["signal"].lower()]
        self._refresh_list(hits)
        kids = self._tree.get_children()
        if kids:
            self._tree.selection_set(kids[0])

    def _on_select(self, _=None):
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        if idx < len(self._filtered):
            self._cur_entry = self._filtered[idx]
            self._render_control(self._cur_entry)

    def _show_placeholder(self):
        for w in self._right.winfo_children():
            w.destroy()
        tk.Label(self._right, text="← 选择信号进行测试",
                 bg=PALETTE["bg"], fg=PALETTE["subtext"],
                 font=(FF, 12)).pack(expand=True)

    def _render_control(self, e: dict):
        for w in self._right.winfo_children():
            w.destroy()

        sf = ScrollableFrame(self._right, bg=PALETTE["bg"])
        sf.pack(fill=tk.BOTH, expand=True)
        inn = sf.inner

        pad = {"padx": 16, "pady": 4}

        # title
        tk.Label(inn, text=e["desc"], bg=PALETTE["bg"],
                 fg=PALETTE["highlight"],
                 font=(FF, 14, "bold"),
                 wraplength=500, justify="left").pack(anchor="w", padx=16, pady=(12, 2))

        def sep():
            tk.Frame(inn, bg=PALETTE["sep"], height=1).pack(fill=tk.X, padx=16, pady=4)

        def kv(k, v, vc=PALETTE["text"]):
            row = tk.Frame(inn, bg=PALETTE["bg"])
            row.pack(fill=tk.X, **pad)
            tk.Label(row, text=f"{k}:", width=13, anchor="e",
                     bg=PALETTE["bg"], fg=PALETTE["subtext"],
                     font=(FF, 11)).pack(side=tk.LEFT)
            tk.Label(row, text=v, anchor="w",
                     bg=PALETTE["bg"], fg=vc,
                     font=(FF, 12, "bold")).pack(side=tk.LEFT, padx=6)

        sep()
        kv("信号名", e["signal"], PALETTE["accent"])
        if e["sig_id"]:
            kv("信号ID", f"0x{e['sig_id']:08X}  (lo byte dec = {e['sig_id'] & 0xFF})",
               PALETTE["warn_color"])
        else:
            kv("信号ID", "未找到 — 请用手动标签页", PALETTE["subtext"])
        if e.get("note"):
            tk.Label(inn, text=f"ℹ  {e['note']}",
                     bg=PALETTE["bg"], fg=PALETTE["subtext"],
                     font=(FF, 10), wraplength=500, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 2))

        if e["sig_id"] is None:
            return

        sig_id = e["sig_id"]

        # ── quick value buttons
        sep()
        tk.Label(inn, text="快速测试值", bg=PALETTE["bg"],
                 fg=PALETTE["highlight"],
                 font=(FF, 12, "bold")).pack(anchor="w", padx=16, pady=(0, 6))

        # command display area (shared, updates on button click)
        self._cmd_frame = tk.Frame(inn, bg=PALETTE["bg"])
        self._cmd_frame.pack(fill=tk.X, padx=16, pady=(0, 4))
        self._cmd_label_var = tk.StringVar(value="")
        self._cmd_lbl = tk.Label(self._cmd_frame, textvariable=self._cmd_label_var,
                                  bg=PALETTE["trig_bg"], fg=PALETTE["text"],
                                  font=(FF, 12), anchor="w", padx=10, pady=6)
        self._cmd_lbl.pack(fill=tk.X)
        self._copy_btn = tk.Button(self._cmd_frame, text="📋 复制命令",
                                    bg=PALETTE["btn_bg"], fg=PALETTE["text"],
                                    relief=tk.FLAT, cursor="hand2",
                                    font=(FF, 10), padx=14,
                                    command=self._copy_current_cmd)
        self._copy_btn.pack(anchor="e", pady=2)
        self._current_cmd = ""

        # button grid for quick values
        btn_grid = tk.Frame(inn, bg=PALETTE["bg"])
        btn_grid.pack(fill=tk.X, padx=16, pady=4)
        quick_vals = e.get("quick_vals", [])
        for col_idx, (val, label) in enumerate(quick_vals):
            cmd = make_cmd(sig_id, val)
            tk.Button(btn_grid,
                      text=f"{label}\n(0x{val:X})",
                      bg=PALETTE["card"], fg=PALETTE["text"],
                      activebackground=PALETTE["highlight"],
                      activeforeground=PALETTE["bg"],
                      relief=tk.FLAT, cursor="hand2",
                      font=(FF, 10), padx=8, pady=6,
                      command=lambda c=cmd, v=val, l=label: self._select_quick(c, v, l)
                      ).grid(row=0, column=col_idx, padx=4, pady=4, sticky="nsew")
            btn_grid.columnconfigure(col_idx, weight=1)

        # ── custom value input
        sep()
        tk.Label(inn, text="自定义值", bg=PALETTE["bg"],
                 fg=PALETTE["highlight"],
                 font=(FF, 12, "bold")).pack(anchor="w", padx=16, pady=(0, 4))

        custom_row = tk.Frame(inn, bg=PALETTE["bg"])
        custom_row.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(custom_row, text="输入值 (hex/dec):", bg=PALETTE["bg"],
                 fg=PALETTE["subtext"], font=(FF, 11), width=18, anchor="e").pack(side=tk.LEFT)
        self._custom_val = tk.StringVar()
        tk.Entry(custom_row, textvariable=self._custom_val,
                 bg=PALETTE["entry_bg"], fg=PALETTE["entry_fg"],
                 insertbackground="#fff", relief=tk.FLAT,
                 font=(FF, 12), bd=4, width=12,
                 highlightthickness=1,
                 highlightcolor=PALETTE["highlight"],
                 highlightbackground=PALETTE["sep"]).pack(side=tk.LEFT, padx=8)
        tk.Button(custom_row, text="生成命令",
                  bg=PALETTE["btn_bg"], fg=PALETTE["text"],
                  relief=tk.FLAT, cursor="hand2", font=(FF, 11), padx=10,
                  command=lambda: self._apply_custom(sig_id)).pack(side=tk.LEFT)

        # ── reset button
        sep()
        reset_row = tk.Frame(inn, bg=PALETTE["bg"])
        reset_row.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(reset_row, text="快速复位:", bg=PALETTE["bg"],
                 fg=PALETTE["subtext"], font=(FF, 11)).pack(side=tk.LEFT, padx=(0, 12))
        for rst_val, rst_lbl in [(0, "复位为 0"), (0xFF, "复位为 0xFF")]:
            rst_cmd = make_cmd(sig_id, rst_val)
            tk.Button(reset_row, text=rst_lbl,
                      bg=PALETTE["reset_bg"], fg=PALETTE["warn_color"],
                      activebackground="#4E1E1E",
                      relief=tk.FLAT, cursor="hand2", font=(FF, 10), padx=10,
                      command=lambda c=rst_cmd, v=rst_val, l=rst_lbl: self._select_quick(c, v, l)
                      ).pack(side=tk.LEFT, padx=4)

    def _select_quick(self, cmd: str, val: int, label: str):
        self._current_cmd = cmd
        self._cmd_label_var.set(f"[{label}]  {cmd}")
        self._cmd_lbl.configure(bg=PALETTE["trig_bg"])
        self.after(100, lambda: self._cmd_lbl.configure(bg=PALETTE["trig_bg"]))

    def _copy_current_cmd(self):
        if self._current_cmd:
            self.winfo_toplevel().clipboard_clear()
            self.winfo_toplevel().clipboard_append(self._current_cmd)
            self._copy_btn.configure(bg=PALETTE["copy_ok"], fg=PALETTE["bg"])
            self.after(600, lambda: self._copy_btn.configure(
                bg=PALETTE["btn_bg"], fg=PALETTE["text"]))

    def _apply_custom(self, sig_id: int):
        raw = self._custom_val.get().strip()
        if not raw:
            return
        try:
            val = int(raw, 0)
        except ValueError:
            messagebox.showwarning("格式错误", f"值无效: {raw}")
            return
        cmd = make_cmd(sig_id, val)
        self._select_quick(cmd, val, f"自定义 0x{val:X}")


# ─────────────────────────────────────────────────────────────────────────────
# 手动转换标签页
# ─────────────────────────────────────────────────────────────────────────────

class ManualTab(tk.Frame):
    """手动输入信号 ID，自动生成 msg_send 命令"""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=PALETTE["bg"], **kw)
        self._build()

    def _build(self):
        pad = {"padx": 24, "pady": 8}

        tk.Label(self, text="手动信号 ID → msg_send 命令",
                 bg=PALETTE["bg"], fg=PALETTE["highlight"],
                 font=(FF, 14, "bold")).pack(anchor="w", **pad)

        tk.Frame(self, bg=PALETTE["sep"], height=1).pack(fill=tk.X, padx=24)

        def make_entry_row(label, default=""):
            r = tk.Frame(self, bg=PALETTE["bg"])
            r.pack(fill=tk.X, **pad)
            tk.Label(r, text=label, bg=PALETTE["bg"],
                     fg=PALETTE["subtext"], font=(FF, 12), width=22, anchor="e").pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            var.trace_add("write", lambda *_: self._update())
            tk.Entry(r, textvariable=var,
                     bg=PALETTE["entry_bg"], fg=PALETTE["entry_fg"],
                     insertbackground="#fff", relief=tk.FLAT,
                     font=(FF, 13), bd=5, width=22,
                     highlightthickness=1,
                     highlightcolor=PALETTE["highlight"],
                     highlightbackground=PALETTE["sep"]).pack(side=tk.LEFT, padx=8)
            return var

        self._sig_id_var = make_entry_row("信号 ID (hex 或 dec):")
        self._val_var    = make_entry_row("触发值 (hex 或 dec):", "1")
        self._rst_var    = make_entry_row("复位值 (hex 或 dec):", "0")

        tk.Frame(self, bg=PALETTE["sep"], height=1).pack(fill=tk.X, padx=24, pady=(4, 0))

        self._result_frame = tk.Frame(self, bg=PALETTE["bg"])
        self._result_frame.pack(fill=tk.X, padx=24, pady=8)

        self._info_var = tk.StringVar()
        tk.Label(self, textvariable=self._info_var,
                 bg=PALETTE["bg"], fg=PALETTE["subtext"],
                 font=(FF, 11), wraplength=600, justify="left").pack(anchor="w", padx=24)

    def _parse_int(self, s: str):
        s = s.strip()
        if not s:
            return None
        try:
            return int(s, 0)
        except ValueError:
            return None

    def _update(self):
        for w in self._result_frame.winfo_children():
            w.destroy()
        self._info_var.set("")

        sig_id = self._parse_int(self._sig_id_var.get())
        val    = self._parse_int(self._val_var.get())
        rst    = self._parse_int(self._rst_var.get())

        if sig_id is None:
            self._info_var.set("请输入有效的信号 ID（如 0x0401A063 或 67178595）")
            return
        if val is None:
            self._info_var.set("触发值格式无效")
            return
        if rst is None:
            rst = 0

        lo = sig_id & 0xFF
        self._info_var.set(
            f"信号 ID: 0x{sig_id:08X}   低字节: {lo} (dec)   触发值: 0x{val:X}   复位值: 0x{rst:X}"
        )

        tk.Label(self._result_frame, text="触发命令", bg=PALETTE["bg"],
                 fg=PALETTE["highlight"],
                 font=(FF, 12, "bold")).pack(anchor="w", pady=(8, 2))
        CopyableLabel(self._result_frame, make_cmd(sig_id, val),
                      sublabel=f"value=0x{val:X}",
                      bg=PALETTE["trig_bg"]).pack(fill=tk.X, pady=2)

        tk.Label(self._result_frame, text="复位命令", bg=PALETTE["bg"],
                 fg=PALETTE["warn_color"],
                 font=(FF, 12, "bold")).pack(anchor="w", pady=(10, 2))
        CopyableLabel(self._result_frame, make_cmd(sig_id, rst),
                      sublabel=f"value=0x{rst:X}",
                      bg=PALETTE["reset_bg"]).pack(fill=tk.X, pady=2)


# ─────────────────────────────────────────────────────────────────────────────
# 主应用
# ─────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self, repo_root: str):
        super().__init__()
        self.title("msg_send 测试命令查询工具 v3")
        self.configure(bg=PALETTE["bg"])
        self.geometry("1280x860")
        self.minsize(960, 640)
        self._repo_root = repo_root
        self._sig_map   = {}
        self._build_ui()
        self._do_scan()

    def _build_ui(self):
        # header
        hdr = tk.Frame(self, bg=PALETTE["panel"], pady=6)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="  📡  msg_send 测试命令查询工具",
                 bg=PALETTE["panel"], fg=PALETTE["highlight"],
                 font=(FF, 14, "bold")).pack(side=tk.LEFT)

        self._root_var = tk.StringVar(value=self._repo_root)
        tk.Entry(hdr, textvariable=self._root_var,
                 bg=PALETTE["entry_bg"], fg=PALETTE["entry_fg"],
                 insertbackground="#fff", relief=tk.FLAT,
                 font=(FF, 10), bd=4, width=50).pack(side=tk.LEFT, padx=(20, 4))
        tk.Button(hdr, text="📂", bg=PALETTE["btn_bg"], fg=PALETTE["text"],
                  relief=tk.FLAT, cursor="hand2",
                  command=self._browse_root).pack(side=tk.LEFT)
        tk.Button(hdr, text="🔄 重新扫描", bg=PALETTE["btn_bg"], fg=PALETTE["text"],
                  relief=tk.FLAT, cursor="hand2",
                  font=(FF, 10), padx=8,
                  command=self._do_scan).pack(side=tk.LEFT, padx=6)

        self._status_var = tk.StringVar(value="正在扫描…")
        tk.Label(hdr, textvariable=self._status_var,
                 bg=PALETTE["panel"], fg=PALETTE["subtext"],
                 font=(FF, 10)).pack(side=tk.RIGHT, padx=12)

        # style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=PALETTE["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",
                         background=PALETTE["card"],
                         foreground=PALETTE["text"],
                         font=(FF, 10),
                         padding=[10, 5])
        style.map("TNotebook.Tab",
                  background=[("selected", PALETTE["highlight"])],
                  foreground=[("selected", PALETTE["bg"])])
        style.configure("Treeview",
                         background=PALETTE["panel"],
                         foreground=PALETTE["text"],
                         fieldbackground=PALETTE["panel"],
                         rowheight=26,
                         font=(FF, 11))
        style.configure("Treeview.Heading",
                         background=PALETTE["card"],
                         foreground=PALETTE["highlight"],
                         font=(FF, 11, "bold"),
                         relief="flat")
        style.map("Treeview",
                  background=[("selected", PALETTE["highlight"])],
                  foreground=[("selected", PALETTE["bg"])])

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

    def _browse_root(self):
        d = filedialog.askdirectory(initialdir=self._repo_root)
        if d:
            self._repo_root = d
            self._root_var.set(d)
            self._do_scan()

    def _save_custom(self, module: str, all_data: list):
        """Called by ModuleTab when user adds/deletes custom entries."""
        # rebuild the custom dict from all current user_added entries
        custom = load_custom_entries()
        custom[module] = [e for e in all_data if e.get("user_added")]
        save_custom_entries(custom)

    def _do_scan(self):
        self._repo_root = self._root_var.get().strip()
        self._status_var.set("扫描中…")
        self.update_idletasks()

        try:
            data = scan_all(self._repo_root)
        except Exception as exc:
            messagebox.showerror("扫描错误", str(exc))
            self._status_var.set("扫描失败")
            return

        self._sig_map = data.get("sig_map", {})

        # clear old tabs
        for tab in self._nb.tabs():
            self._nb.forget(tab)

        warn_data   = data.get("Warning", [])
        chime_data  = data.get("Chime",   [])
        all_data    = data.get("All",     [])
        instruments = data.get("Instruments", [])

        def add_tab(widget, title):
            widget.pack()
            self._nb.add(self._nb.winfo_children()[-1], text=title)

        # Warning tab — editable
        warn_tab = ModuleTab(self._nb, warn_data, module="Warning",
                             editable=True, sig_map=self._sig_map,
                             save_callback=self._save_custom)
        add_tab(warn_tab, f"⚠ Warning  ({len(warn_data)})")

        # Chime tab — editable
        chime_tab = ModuleTab(self._nb, chime_data, module="Chime",
                              editable=True, sig_map=self._sig_map,
                              save_callback=self._save_custom)
        add_tab(chime_tab, f"🔔 Chime  ({len(chime_data)})")

        # All Signals
        all_tab = ModuleTab(self._nb, all_data, module="Signal")
        add_tab(all_tab, f"📋 All Signals  ({len(all_data)})")

        # Instrument module tabs
        for mod in instruments:
            inst_tab = InstrumentTab(self._nb, mod["entries"])
            add_tab(inst_tab, mod["tab_name"])

        # Manual tab
        add_tab(ManualTab(self._nb), "✏ 手动转换")

        self._status_var.set(
            f"扫描完成  Warning:{len(warn_data)}  Chime:{len(chime_data)}  "
            f"信号:{len(all_data)}  仪表模块:{len(instruments)}")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="msg_send GUI v3")
    parser.add_argument("--root", default=REPO_ROOT,
                        help="仓库根目录（默认自动推断）")
    args = parser.parse_args()
    App(repo_root=args.root).mainloop()


if __name__ == "__main__":
    main()
