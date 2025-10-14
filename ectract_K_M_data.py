#!/usr/bin/env python3
import argparse
import csv
from scapy.all import rdpcap
import struct

# --- 关键配置（根据你的数据包调整）---
# 从你的数据"00 01 00 02 00 80 02 08..."分析，你的设备端点可能是0x02（可根据调试结果微调）
TARGET_ENDPOINTS = {0x02, 0x82}  # 先尝试这两个端点

# 键盘扫描码映射（保持不变）
KEYBOARD_CODES = {
    0x04: 'a', 0x05: 'b', 0x06: 'c', 0x07: 'd', 0x08: 'e', 0x09: 'f',
    0x0A: 'g', 0x0B: 'h', 0x0C: 'i', 0x0D: 'j', 0x0E: 'k', 0x0F: 'l',
    0x10: 'm', 0x11: 'n', 0x12: 'o', 0x13: 'p', 0x14: 'q', 0x15: 'r',
    0x16: 's', 0x17: 't', 0x18: 'u', 0x19: 'v', 0x1A: 'w', 0x1B: 'x',
    0x1C: 'y', 0x1D: 'z', 0x1E: '1', 0x1F: '2', 0x20: '3', 0x21: '4',
    0x22: '5', 0x23: '6', 0x24: '7', 0x25: '8', 0x26: '9', 0x27: '0',
    0x28: 'ENTER', 0x29: 'ESC', 0x2A: 'BACKSPACE', 0x2B: 'TAB',
    0x2C: 'SPACE', 0x2D: '-', 0x2E: '=', 0x2F: '[', 0x30: ']',
    0x31: '\\', 0x33: ';', 0x34: '\'', 0x35: '`', 0x36: ',',
    0x37: '.', 0x38: '/', 0x39: 'CAPS_LOCK',
    0x3A: 'F1', 0x3B: 'F2', 0x3C: 'F3', 0x3D: 'F4', 0x3E: 'F5',
    0x3F: 'F6', 0x40: 'F7', 0x41: 'F8', 0x42: 'F9', 0x43: 'F10',
    0x44: 'F11', 0x45: 'F12',
    0x46: 'PRINT_SCREEN', 0x47: 'SCROLL_LOCK', 0x48: 'PAUSE',
    0x49: 'INSERT', 0x4A: 'HOME', 0x4B: 'PAGE_UP', 0x4C: 'DELETE',
    0x4D: 'END', 0x4E: 'PAGE_DOWN',
    0x4F: 'RIGHT_ARROW', 0x50: 'LEFT_ARROW', 0x51: 'DOWN_ARROW', 0x52: 'UP_ARROW',
}


def parse_urb_packet(raw_data):
    """解析USB URB数据包，提取端点和HID数据"""
    if len(raw_data) < 16:
        return None, None  # 数据太短，不是有效URB包

    # 从你的数据"0010   00 01 00 02 00 80 02 08..."分析：
    # 偏移14-15字节（0x0E-0x0F）可能是端点信息（0x02 08中的0x02）
    endpoint = raw_data[15] & 0x0F  # 取低4位作为端点号
    # HID数据从偏移20字节（0x14）开始（你的数据0020之后是有效内容）
    hid_data = raw_data[20:]
    return endpoint, hid_data


def identify_hid_report_type(data):
    if len(data) == 8:
        return "KEYBOARD"
    elif len(data) in [5, 6]:
        return "MOUSE"
    return "UNKNOWN"


def parse_usb_pcap(pcap_file, output_csv=None):
    print(f"--- 开始解析文件: {pcap_file} ---")
    print("调试信息：会显示所有被处理的包（含未匹配的）")
    print("时间戳, 端点, 设备类型, 事件类型, 详细信息")
    print("-" * 80)

    packets = rdpcap(pcap_file)
    events = []
    processed_count = 0  # 统计处理的包数量

    for pkt in packets:
        processed_count += 1
        # 每100个包打印一次进度，避免卡死无反馈
        if processed_count % 100 == 0:
            print(f"已处理{processed_count}个包...")

        # 提取原始数据（优先从raw层，没有则取整个包的负载）
        raw_data = b''
        if 'raw' in pkt and hasattr(pkt.raw, 'load'):
            raw_data = pkt.raw.load
        else:
            # 尝试从整个包的负载中提取
            raw_data = bytes(pkt)

        # 解析URB包，获取端点和HID数据
        endpoint, hid_data = parse_urb_packet(raw_data)
        if endpoint is None:
            # 调试：显示未解析的包（可选关闭）
            # print(f"{pkt.time:.6f}, 未知, 跳过, 数据长度={len(raw_data)}")
            continue

        # # 只处理目标端点的包
        # if endpoint not in TARGET_ENDPOINTS:
        #     # 调试：显示端点不匹配的包
        #     # print(f"{pkt.time:.6f}, 端点0x{endpoint:02x}, 跳过, 非目标端点")
        #     continue

        # 处理HID数据
        if hid_data and len(hid_data) >= 4:
            report_type = identify_hid_report_type(hid_data)
            timestamp = pkt.time

            if report_type == "KEYBOARD":
                if len(hid_data) >= 8:
                    modifier = hid_data[0]
                    key_codes = hid_data[2:8]
                    keys_pressed = [
                        KEYBOARD_CODES.get(code, f"UNKNOWN(0x{code:02x})")
                        for code in key_codes if code != 0
                    ]
                    if keys_pressed:
                        event_info = f"按键: {', '.join(keys_pressed)} (Modifier: 0x{modifier:02x})"
                        print(f"{timestamp:.6f}, 端点0x{endpoint:02x}, KEYBOARD, KEY_PRESS, {event_info}")
                        events.append([timestamp, f"端点0x{endpoint:02x}", "KEYBOARD", "KEY_PRESS", event_info])

            elif report_type == "MOUSE":
                if len(hid_data) >= 5:
                    buttons = hid_data[0]
                    dx = struct.unpack('<b', hid_data[1:2])[0]
                    dy = struct.unpack('<b', hid_data[2:3])[0]
                    wheel = struct.unpack('<b', hid_data[3:4])[0]

                    event_details = []
                    if buttons & 0x01:
                        event_details.append("左键按下")
                    if buttons & 0x02:
                        event_details.append("右键按下")
                    if buttons & 0x04:
                        event_details.append("中键按下")
                    if dx != 0 or dy != 0:
                        event_details.append(f"移动: (Δx={dx}, Δy={dy})")
                    if wheel != 0:
                        direction = "上" if wheel > 0 else "下"
                        event_details.append(f"滚轮{direction}: {abs(wheel)}")

                    if event_details:
                        event_info = "; ".join(event_details)
                        print(f"{timestamp:.6f}, 端点0x{endpoint:02x}, MOUSE, EVENT, {event_info}")
                        events.append([timestamp, f"端点0x{endpoint:02x}", "MOUSE", "EVENT", event_info])

    print("-" * 80)
    print(f"--- 解析完成，共处理{processed_count}个包 ---")

    if output_csv:
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Endpoint", "Device_Type", "Event_Type", "Details"])
            writer.writerows(events)
        print(f"\n结果已导出到CSV文件: {output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="解析PCAP中的USB URB键盘鼠标事件（适配你的数据包）。")
    parser.add_argument("pcap_file", help="PCAP文件路径")
    parser.add_argument("-o", "--output", help="导出CSV路径")

    args = parser.parse_args()
    parse_usb_pcap(args.pcap_file, args.output)