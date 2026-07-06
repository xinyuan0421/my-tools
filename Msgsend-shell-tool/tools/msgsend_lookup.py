#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
msg_send 测试命令查询工具

通过信号名、告警描述或 dispID 快速查找信号 ID 和对应的 msg_send 测试命令。

msg_send 命令格式:
  msg_send 2 4 1 160 <sig_lo_dec> 0 0 0 0 0 <value> 0 0 0
  其中 sig_lo_dec = 信号ID低字节的十进制值

用法:
  python3 msgsend_lookup.py [关键字]
  python3 msgsend_lookup.py --list
  python3 msgsend_lookup.py DrvrGear
  python3 msgsend_lookup.py 请降低
  python3 msgsend_lookup.py 185
"""

import sys
import argparse

# ─────────────────────────────────────────────────────────────────────────────
# 数据来源:
#   信号 ID  ← framework/cluster_api/clusterapi_tsdl/src/SignalDefs.h
#   dispID   ← framework/cluster_api_0627push/cluster_api/control/Warning/WarningTable.cpp
#   触发值   ← framework/cluster_api_0627push/cluster_api/control/Warning/WarningService.cpp
# ─────────────────────────────────────────────────────────────────────────────

def _cmd(sig_id: int, value: int) -> str:
    lo = sig_id & 0xFF
    return f"msg_send 2 4 1 160 {lo} 0 0 0 0 0 {value} 0 0 0"

def _reset(sig_id: int) -> str:
    return _cmd(sig_id, 0)


# 每条记录:
#   (描述, dispID, 信号名, 信号ID, [(触发值, 说明)], 复位值, 附注)
#
# 触发值列表: [(value, note), ...]
#   若 note 不为空，表示该值触发对应的告警变体
# 复位值: 通常为 0 (某些信号除外)

WARNING_TABLE = [
    # ── 安全气囊 ──────────────────────────────────────────────────────────────
    {
        "desc":       "安全气囊故障",
        "disp_id":    13,
        "disp_state": 1,
        "signal":     "ACU_1_LampWarning",
        "sig_id":     0x0401A004,
        "triggers":   [(0x2, "")],
        "reset":      0,
    },
    # ── 空气悬架 ──────────────────────────────────────────────────────────────
    {
        "desc":       "空气悬架控制系统故障",
        "disp_id":    27,
        "disp_state": 2,
        "signal":     "ASUSusWrnngMsg",
        "sig_id":     0x0401A00F,
        "triggers":   [(0x7, ""), (0x8, ""), (0x9, ""), (0xA, ""), (0xB, "")],
        "reset":      0,
    },
    # ── 动力电池电量低 ────────────────────────────────────────────────────────
    {
        "desc":       "动力电池电量低",
        "disp_id":    166,
        "disp_state": 12,
        "signal":     "BMS_SOC_Low_Chg",
        "sig_id":     0x0401A05B,
        "triggers":   [(0x1, "")],
        "reset":      0,
        "note":       "也可用 BMS_SOC_Low_Dis(0x0401A05C) == 0x1 触发",
    },
    {
        "desc":       "动力电池电量低（充电侧备用）",
        "disp_id":    166,
        "disp_state": 12,
        "signal":     "BMS_SOC_Low_Dis",
        "sig_id":     0x0401A05C,
        "triggers":   [(0x1, "")],
        "reset":      0,
        "note":       "与 BMS_SOC_Low_Chg 触发同一告警",
    },
    # ── 动力电池电量低，部分功能受限 ─────────────────────────────────────────
    {
        "desc":       "动力电池电量低，部分功能受限",
        "disp_id":    66,
        "disp_state": 2,
        "signal":     "EgyIndicating",
        "sig_id":     0x0401A023,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 动力电池电量低，已禁止继续行驶 ───────────────────────────────────────
    {
        "desc":       "动力电池电量低，已禁止继续行驶",
        "disp_id":    66,
        "disp_state": 3,
        "signal":     "EgyIndicating",
        "sig_id":     0x0401A023,
        "triggers":   [(0x2, "")],
        "reset":      0,
    },
    # ── 请关闭加油口盖 ────────────────────────────────────────────────────────
    {
        "desc":       "请关闭加油口盖",
        "disp_id":    98,
        "disp_state": 1,
        "signal":     "FillerLidDCorAcDcStsIndcr",
        "sig_id":     0x0401A032,
        "triggers":   [(0x2, "")],
        "reset":      0,
        "note":       "还需 VehicleSpdDisplay >= 3 且 VehicleSpdDisplayValid == 1",
    },
    # ── DrvrGearLvrLockIndcn (多条告警共用同一信号) ──────────────────────────
    {
        "desc":       "请踩下刹车踏板",
        "disp_id":    43,
        "disp_state": 1,
        "signal":     "DrvrGearLvrLockIndcn",
        "sig_id":     0x0401A063,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    {
        "desc":       "请降低车速",
        "disp_id":    185,
        "disp_state": 6,
        "signal":     "DrvrGearLvrLockIndcn",
        "sig_id":     0x0401A063,
        "triggers":   [(0x2, "")],
        "reset":      0,
    },
    {
        "desc":       "车辆无法驻车，有溜坡风险",
        "disp_id":    10,
        "disp_state": 2,
        "signal":     "DrvrGearLvrLockIndcn",
        "sig_id":     0x0401A063,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    {
        "desc":       "当前状态禁止换挡",
        "disp_id":    69,
        "disp_state": 6,
        "signal":     "DrvrGearLvrLockIndcn",
        "sig_id":     0x0401A063,
        "triggers":   [(0x4, "")],
        "reset":      0,
    },
    # ── 制动系统故障 ──────────────────────────────────────────────────────────
    {
        "desc":       "制动系统故障",
        "disp_id":    55,
        "disp_state": 1,
        "signal":     "BrakeSystemStatus",
        "sig_id":     0x0401A016,
        "triggers":   [(0x1, ""), (0x2, ""), (0x3, ""), (0x4, "")],
        "reset":      0,
    },
    # ── 制动液位低 ────────────────────────────────────────────────────────────
    {
        "desc":       "制动液位低",
        "disp_id":    6,
        "disp_state": 1,
        "signal":     "BrakeFluidWarning",
        "sig_id":     0x0401A015,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 制动液位传感器故障 ────────────────────────────────────────────────────
    {
        "desc":       "制动液位传感器故障",
        "disp_id":    5,
        "disp_state": 1,
        "signal":     "BrakeFluidWarning",
        "sig_id":     0x0401A015,
        "triggers":   [(0x2, "")],
        "reset":      0,
    },
    # ── 电子制动力分配故障 ────────────────────────────────────────────────────
    {
        "desc":       "电子制动力分配故障",
        "disp_id":    5,
        "disp_state": 2,
        "signal":     "EBDFault",
        "sig_id":     0x0401A022,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 自动驻车功能故障 ──────────────────────────────────────────────────────
    {
        "desc":       "自动驻车功能故障",
        "disp_id":    16,
        "disp_state": 1,
        "signal":     "AVHAvailable",
        "sig_id":     0x0401A010,
        "triggers":   [(0x0, "")],
        "reset":      0x1,
        "note":       "触发值为 0x0，复位值为 0x1",
    },
    # ── 油箱泄压失败 ──────────────────────────────────────────────────────────
    {
        "desc":       "油箱泄压失败，请再次点击加油开关，尝试加油",
        "disp_id":    99,
        "disp_state": 1,
        "signal":     "EngTankPressReleaseFailedPrompt",
        "sig_id":     0x0401A027,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 陡坡缓降功能故障 ──────────────────────────────────────────────────────
    {
        "desc":       "陡坡缓降功能故障",
        "disp_id":    21,
        "disp_state": 1,
        "signal":     "HDCAvailable",
        "sig_id":     0x0401A035,
        "triggers":   [(0x0, "")],
        "reset":      0x1,
        "note":       "触发值为 0x0，复位值为 0x1",
    },
    # ── 驻车坡度过大 ──────────────────────────────────────────────────────────
    {
        "desc":       "驻车坡度过大，请安全停车",
        "disp_id":    10,
        "disp_state": 1,
        "signal":     "EpbTxtDisp",
        "sig_id":     0x0401A02A,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 驻车制动系统故障 ──────────────────────────────────────────────────────
    {
        "desc":       "驻车制动系统故障",
        "disp_id":    9,
        "disp_state": 1,
        "signal":     "EpbFaultLamp",
        "sig_id":     0x0401A028,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 驱动功率受限 ──────────────────────────────────────────────────────────
    {
        "desc":       "驱动功率受限",
        "disp_id":    66,
        "disp_state": 1,
        "signal":     "TelltlPwrLoss",
        "sig_id":     0x0401A041,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 雨量传感器故障 ────────────────────────────────────────────────────────
    {
        "desc":       "雨量传感器故障",
        "disp_id":    138,
        "disp_state": 1,
        "signal":     "RainSnsrFlr",
        "sig_id":     0x0401A094,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 动力电池热扩散 ────────────────────────────────────────────────────────
    {
        "desc":       "动力电池热扩散，文言提示+声音提醒",
        "disp_id":    31,
        "disp_state": 3,
        "signal":     "Therunawy",
        "sig_id":     0x0401A071,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 动力系统故障 ──────────────────────────────────────────────────────────
    {
        "desc":       "动力系统故障，请联系服务中心",
        "disp_id":    169,
        "disp_state": 5,
        "signal":     "HybErrIndcnReqTelltlSysHybFailr",
        "sig_id":     0x0401A038,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 充电枪锁 ──────────────────────────────────────────────────────────────
    {
        "desc":       "充电枪上锁失败",
        "disp_id":    69,
        "disp_state": 4,
        "signal":     "CDU2ChrgPortElecLockSts",
        "sig_id":     0x0401A090,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    {
        "desc":       "充电枪解锁失败",
        "disp_id":    69,
        "disp_state": 5,
        "signal":     "CDU2ChrgPortElecLockSts",
        "sig_id":     0x0401A090,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 防晕车 ────────────────────────────────────────────────────────────────
    {
        "desc":       "防晕车功能已激活",
        "disp_id":    49,
        "disp_state": 1,
        "signal":     "AntiCarSicknessState",
        "sig_id":     0x0401A091,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 展厅模式 ──────────────────────────────────────────────────────────────
    {
        "desc":       "此模式下不可行驶，请退出当前模式",
        "disp_id":    31,
        "disp_state": 4,
        "signal":     "AlertMsgToDrvr",
        "sig_id":     0x0401A092,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 灯光故障（转向灯）────────────────────────────────────────────────────
    {
        "desc":       "转向灯有故障，为了安全驾驶，请及时修理",
        "disp_id":    2,
        "disp_state": 2,
        "signal":     "ExtrLtgStsTurnIndrLe",
        "sig_id":     0x0401A080,
        "triggers":   [(0x3, "")],
        "reset":      0,
        "note":       "也可用 ExtrLtgStsTurnIndrRi(0x0401A081) == 0x3 触发",
    },
    {
        "desc":       "转向灯有故障（右）",
        "disp_id":    2,
        "disp_state": 2,
        "signal":     "ExtrLtgStsTurnIndrRi",
        "sig_id":     0x0401A081,
        "triggers":   [(0x3, "")],
        "reset":      0,
        "note":       "与 ExtrLtgStsTurnIndrLe 触发同一告警",
    },
    # ── 位置灯故障 ────────────────────────────────────────────────────────────
    {
        "desc":       "位置灯有故障，为了安全驾驶，请及时修理",
        "disp_id":    2,
        "disp_state": 3,
        "signal":     "ExtrLtgStsPosLi",
        "sig_id":     0x0401A030,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    # ── 远光灯故障 ────────────────────────────────────────────────────────────
    {
        "desc":       "远光灯有故障，为了安全驾驶，请及时修理",
        "disp_id":    2,
        "disp_state": 4,
        "signal":     "ExtrLtgStsHiBeam",
        "sig_id":     0x0401A02E,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    # ── 制动灯故障 ────────────────────────────────────────────────────────────
    {
        "desc":       "制动灯有故障，为了安全驾驶，请及时修理",
        "disp_id":    2,
        "disp_state": 5,
        "signal":     "ExtrLtgStsStopLi",
        "sig_id":     0x0401A083,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    # ── 未找到有效钥匙 ────────────────────────────────────────────────────────
    {
        "desc":       "未找到有效钥匙",
        "disp_id":    79,
        "disp_state": 1,
        "signal":     "KeyNotPrsntMsgToDrvr",
        "sig_id":     0x0401A093,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 驱动电机过热 ──────────────────────────────────────────────────────────
    {
        "desc":       "驱动电机过热",
        "disp_id":    33,
        "disp_state": 1,
        "signal":     "RmcuGenericInvrtTAlrmSt",
        "sig_id":     0x0401A06F,
        "triggers":   [(0x1, ""), (0x2, "")],
        "reset":      0,
        "note":       "六路信号任一为 0x1/0x2 均触发: RmcuGenericInvrtTAlrmSt/MotTAlrmSt, FmcuGenericInvrtTAlrmSt/MotTAlrmSt, GcuGenericInvrtTAlrmSt/MotTAlrmSt",
    },
    # ── 充电口盖灯故障 ────────────────────────────────────────────────────────
    {
        "desc":       "充电口盖灯有故障，请及时修理",
        "disp_id":    2,
        "disp_state": 9,
        "signal":     "ExtrLtgStsChrgLidLi",
        "sig_id":     0x0401A085,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    # ── 后雾灯故障 ────────────────────────────────────────────────────────────
    {
        "desc":       "后雾灯有故障，为了安全驾驶，请及时修理",
        "disp_id":    2,
        "disp_state": 6,
        "signal":     "ExtrLtgStsReFog",
        "sig_id":     0x0401A031,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    # ── 牌照灯故障 ────────────────────────────────────────────────────────────
    {
        "desc":       "牌照灯有故障，为了安全驾驶，请及时修理",
        "disp_id":    2,
        "disp_state": 7,
        "signal":     "ExtrLtgStsPlateLamp",
        "sig_id":     0x0401A082,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    # ── 倒车灯故障 ────────────────────────────────────────────────────────────
    {
        "desc":       "倒车灯有故障，为了安全驾驶，请及时修理",
        "disp_id":    2,
        "disp_state": 8,
        "signal":     "ExtrLtgStsReverseLi",
        "sig_id":     0x0401A084,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    # ── 驱动电机故障 ──────────────────────────────────────────────────────────
    {
        "desc":       "驱动电机故障",
        "disp_id":    72,
        "disp_state": 1,
        "signal":     "RmcuGenericFltAlrmSt",
        "sig_id":     0x0401A06E,
        "triggers":   [(0x1, ""), (0x2, "")],
        "reset":      0,
        "note":       "三路信号任一为 0x1/0x2 均触发: RmcuGenericFltAlrmSt, FmcuGenericFltAlrmSt, GcuGenericFltAlrmSt",
    },
    # ── 充电枪连接无法行驶 ────────────────────────────────────────────────────
    {
        "desc":       "充电枪连接，无法行驶",
        "disp_id":    69,
        "disp_state": 3,
        "signal":     "WarnMsgToDrvr",
        "sig_id":     0x0401A095,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 近光灯故障 ────────────────────────────────────────────────────────────
    {
        "desc":       "近光灯有故障，为了安全驾驶，请及时修理",
        "disp_id":    2,
        "disp_state": 1,
        "signal":     "ExtrLtgStsLoBeam",
        "sig_id":     0x0401A02F,
        "triggers":   [(0x3, "")],
        "reset":      0,
    },
    # ── 智能钥匙电池电量低 ────────────────────────────────────────────────────
    {
        "desc":       "智能钥匙电池电量低",
        "disp_id":    86,
        "disp_state": 1,
        "signal":     "Fob_LowBattery",
        "sig_id":     0x0401A0A3,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
    # ── 雨刮故障 ──────────────────────────────────────────────────────────────
    {
        "desc":       "雨刮故障",
        "disp_id":    138,
        "disp_state": 2,
        "signal":     "Wiprmotrsts",
        "sig_id":     0x0401A096,
        "triggers":   [(0x1, "")],
        "reset":      0,
    },
]


# ─────────────────────────────────────────────────────────────────────────────

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def format_entry(e: dict) -> str:
    sig_id   = e["sig_id"]
    sig_name = e["signal"]
    desc     = e["desc"]
    disp_id  = e["disp_id"]
    note     = e.get("note", "")
    reset_v  = e.get("reset", 0)

    lines = []
    lines.append(f"{BOLD}{CYAN}{'─'*70}{RESET}")
    lines.append(f"  {BOLD}描述:{RESET}     {desc}")
    lines.append(f"  {BOLD}dispID:{RESET}   {disp_id}   dispState: {e.get('disp_state','')}")
    lines.append(f"  {BOLD}信号名:{RESET}   {GREEN}{sig_name}{RESET}")
    lines.append(f"  {BOLD}信号ID:{RESET}   {YELLOW}0x{sig_id:08X}{RESET}  (lo byte dec: {sig_id & 0xFF})")

    for value, _note in e["triggers"]:
        cmd = _cmd(sig_id, value)
        lines.append(f"  {BOLD}触发命令:{RESET} {cmd}  (value=0x{value:X})")

    reset_cmd = _cmd(sig_id, reset_v)
    lines.append(f"  {BOLD}复位命令:{RESET} {reset_cmd}  (value=0x{reset_v:X})")

    if note:
        lines.append(f"  {BOLD}备注:{RESET}     {note}")

    return "\n".join(lines)


def search(keyword: str) -> list:
    kw = keyword.strip().lower()
    results = []
    for e in WARNING_TABLE:
        if (kw in e["desc"].lower()
                or kw in e["signal"].lower()
                or kw == str(e["disp_id"])
                or kw == f"0x{e['sig_id']:08x}"
                or kw == f"0x{e['sig_id']:08X}"):
            results.append(e)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="msg_send 测试命令查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument("keyword", nargs="?", help="搜索关键字（信号名 / 描述 / dispID）")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有告警条目")
    args = parser.parse_args()

    if args.list or not args.keyword:
        if not args.keyword:
            # 交互模式
            print(f"{BOLD}msg_send 测试命令查询工具{RESET}  (输入 q 退出, --list 显示全部)")
            while True:
                try:
                    kw = input("\n请输入搜索关键字（信号名/描述/dispID）: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if kw.lower() in ("q", "quit", "exit"):
                    break
                if not kw:
                    continue
                hits = search(kw)
                if not hits:
                    print(f"  未找到匹配项: {kw}")
                else:
                    for e in hits:
                        print(format_entry(e))
            return

        # --list
        for e in WARNING_TABLE:
            print(format_entry(e))
        return

    hits = search(args.keyword)
    if not hits:
        print(f"未找到匹配项: {args.keyword}")
        sys.exit(1)
    for e in hits:
        print(format_entry(e))


if __name__ == "__main__":
    main()
