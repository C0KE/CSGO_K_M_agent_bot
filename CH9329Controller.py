import serial
import time
import json
from typing import List, Dict, Tuple

# -------------------------- 配置参数（需根据实际情况修改） --------------------------
SERIAL_PORT = "COM3"  # 串口号（Windows：COMx，Linux：/dev/ttyUSBx）
BAUDRATE = 115200      # 波特率（CH9329默认115200）
TIMEOUT = 0.1          # 串口超时时间（秒）
# --------------------------------------------------------------------------------

# 键盘扫描码映射表（参考USB HID标准，仅列出CSGO常用键）
KEYBOARD_SCANNER = {
    "W": 0x1A,
    "S": 0x16,
    "A": 0x04,
    "D": 0x07,
    "SPACE": 0x2C,    # 空格（跳跃）
    "LEFTCTRL": 0xE0  # 左Ctrl（下蹲）
}

# 鼠标按键掩码（第1字节的bit0-bit4对应左键/右键/中键等）
MOUSE_BUTTON_MASK = {
    "left": 0x01,     # 左键（开枪）
    "right": 0x02,    # 右键（开镜/特殊攻击）
    "middle": 0x04    # 中键（默认无用）
}


class CH9329Controller:
    def __init__(self):
        # 初始化串口连接（修正停止位常量名称）
        self.ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            timeout=TIMEOUT,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,  # 关键修正：将STOPBITS_1改为STOPBITS_ONE
            bytesize=serial.EIGHTBITS
        )
        if not self.ser.is_open:
            self.ser.open()
        print(f"CH9329已连接至串口：{SERIAL_PORT}")

    def _send_command(self, data: bytes) -> bool:
        """发送字节指令到CH9329，并等待ACK确认"""
        try:
            self.ser.write(data)
            # 等待CH9329返回ACK（0x06为确认，0x15为错误）
            ack = self.ser.read(1)
            if ack == b'\x06':
                return True
            else:
                print(f"指令发送失败，ACK：{ack.hex()}")
                return False
        except Exception as e:
            print(f"串口通信错误：{str(e)}")
            return False

    def send_keyboard_command(self, key: str, action: str) -> bool:
        """
        发送键盘操作指令
        :param key: 按键名称（如"W"、"SPACE"，需在KEYBOARD_SCANNER中定义）
        :param action: 动作（"press"按下 / "release"松开）
        :return: 发送成功与否
        """
        if key not in KEYBOARD_SCANNER:
            print(f"不支持的按键：{key}")
            return False

        # 键盘HID报告格式（8字节）：[修饰键, 保留, 扫描码1, 扫描码2, 扫描码3, 扫描码4, 扫描码5, 扫描码6]
        # 简化处理：仅使用扫描码1，其他为0
        report = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        if action == "press":
            report[2] = KEYBOARD_SCANNER[key]  # 按下时设置扫描码
        # 松开时扫描码为0（默认值）

        return self._send_command(bytes(report))

    def send_mouse_move(self, dx: int, dy: int) -> bool:
        """
        发送鼠标移动指令
        :param dx: X轴偏移量（-127 ~ +127，正数向右）
        :param dy: Y轴偏移量（-127 ~ +127，正数向下）
        :return: 发送成功与否
        """
        # 鼠标HID报告格式（5字节）：[按键掩码, X偏移, Y偏移, 滚轮, 保留]
        # 偏移量需限制在8位有符号整数范围
        dx_clamped = max(-127, min(127, dx))
        dy_clamped = max(-127, min(127, dy))
        report = [0x00, dx_clamped & 0xFF, dy_clamped & 0xFF, 0x00, 0x00]
        return self._send_command(bytes(report))

    def send_mouse_click(self, button: str, action: str) -> bool:
        """
        发送鼠标点击指令
        :param button: 按键（"left"左键 / "right"右键 / "middle"中键）
        :param action: 动作（"press"按下 / "release"松开 / "click"单击）
        :return: 发送成功与否
        """
        if button not in MOUSE_BUTTON_MASK:
            print(f"不支持的鼠标按键：{button}")
            return False

        mask = MOUSE_BUTTON_MASK[button]
        # 鼠标HID报告第1字节为按键掩码（bit0=左键，bit1=右键等）
        if action == "press":
            report = [mask, 0x00, 0x00, 0x00, 0x00]
            return self._send_command(bytes(report))
        elif action == "release":
            report = [0x00, 0x00, 0x00, 0x00, 0x00]  # 松开所有按键
            return self._send_command(bytes(report))
        elif action == "click":
            # 单击=按下+延迟+松开（延迟50ms模拟物理点击）
            if not self.send_mouse_click(button, "press"):
                return False
            time.sleep(0.05)
            return self.send_mouse_click(button, "release")
        else:
            print(f"不支持的鼠标动作：{action}")
            return False

    def execute_instruction(self, instruction: Dict) -> None:
        """
        执行LLM决策模块输出的标准化指令（JSON格式）
        :param instruction: 符合协议的指令字典（包含keyboard和mouse字段）
        """
        # 执行键盘指令
        for key_cmd in instruction.get("keyboard", []):
            delay = key_cmd.get("delay", 0)
            if delay > 0:
                time.sleep(delay / 1000.0)  # 延迟执行（毫秒转秒）
            self.send_keyboard_command(
                key=key_cmd["key"],
                action=key_cmd["action"]
            )

        # 执行鼠标指令
        for mouse_cmd in instruction.get("mouse", []):
            delay = mouse_cmd.get("delay", 0)
            if delay > 0:
                time.sleep(delay / 1000.0)  # 延迟执行
            action = mouse_cmd["action"]
            if action == "move":
                # 解析参数："(dx:50, dy:0)" → dx=50, dy=0
                param = mouse_cmd["parameter"]
                dx = int(param.split(", ")[0].split(":")[1])
                dy = int(param.split(", ")[1].split(":")[1].strip(")"))
                self.send_mouse_move(dx, dy)
            elif action in ["click", "press", "release"]:
                button = mouse_cmd["parameter"]
                self.send_mouse_click(button, action)

    def close(self):
        """关闭串口连接"""
        if self.ser.is_open:
            self.ser.close()
        print("CH9329连接已关闭")


# -------------------------- 测试示例 --------------------------
if __name__ == "__main__":
    # 初始化控制器
    ch9329 = CH9329Controller()

    try:
        # 示例1：发送单个键盘指令（按W键1秒后松开）
        print("测试：按W键1秒...")
        ch9329.send_keyboard_command("W", "press")
        time.sleep(1)
        ch9329.send_keyboard_command("W", "release")
        time.sleep(0.5)

        # 示例2：发送鼠标指令（向右移动50像素，然后左键单击）
        print("测试：鼠标右移50像素+左键单击...")
        ch9329.send_mouse_move(dx=50, dy=0)
        time.sleep(0.5)
        ch9329.send_mouse_click("left", "click")
        time.sleep(0.5)

        # 示例3：执行LLM输出的标准化指令（模拟JSON）
        print("测试：执行LLM标准化指令...")
        llm_instruction = {
            "instruction_id": "TEST_001",
            "timestamp": "2024-05-20 15:00:00:000",
            "keyboard": [
                {"action": "press", "key": "A", "delay": 0},
                {"action": "release", "key": "A", "delay": 500}  # 按A键500ms后松开
            ],
            "mouse": [
                {"action": "move", "parameter": "(dx:-30, dy:0)", "delay": 600},  # A键松开后100ms移动
                {"action": "click", "parameter": "left", "delay": 800}  # 移动后200ms点击
            ]
        }
        ch9329.execute_instruction(llm_instruction)

    finally:
        # 确保资源释放
        ch9329.close()