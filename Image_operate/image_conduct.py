import os
import re
import shutil
import uuid
from pathlib import Path

# 这个文件是把微信图片名称和whatsapp图片名称转成S3服务端的名称

# 配置路径（可根据需要修改）
SOURCE_DIR = Path(r"C:\Users\PolyU\Desktop\Image\original_image")
TARGET_DIR = Path(r"C:\Users\PolyU\Desktop\Image\conduct_image")

# 允许的图片扩展名（不区分大小写）
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp'}

# 正则表达式：匹配微信图片文件名
WECHAT_PATTERN = re.compile(r'微信图片_(\d{14})')

# 正则表达式：匹配WhatsApp图片文件名（可前导负号，数字前缀可忽略）
WHATSAPP_PATTERN = re.compile(r'-?(\d+)-PHOTO-(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})')

def generate_new_filename(old_name: str) -> str | None:
    """
    根据旧文件名生成新文件名（不含路径）
    只处理命名规则，不检查扩展名。
    若匹配微信/WhatsApp格式，返回新文件名（含原扩展名）；否则返回 None。
    """
    stem, ext = os.path.splitext(old_name)
    ext = ext.lower()  # 统一小写，保留扩展名格式

    # 尝试匹配微信格式
    m = WECHAT_PATTERN.match(old_name)
    if m:
        ts = m.group(1)  # 14位数字
        try:
            year = ts[0:4]
            month = ts[4:6]
            day = ts[6:8]
            hour = ts[8:10]
            minute = ts[10:12]
            second = ts[12:14]
        except IndexError:
            return None
        date_part = f"{year}-{month}-{day}_{hour}-{minute}-{second}"
        random_suffix = uuid.uuid4().hex[:8]
        return f"{date_part}_{random_suffix}{ext}"

    # 尝试匹配WhatsApp格式
    m = WHATSAPP_PATTERN.match(old_name)
    if m:
        year, month, day, hour, minute, second = m.group(2, 3, 4, 5, 6, 7)
        date_part = f"{year}-{month}-{day}_{hour}-{minute}-{second}"
        random_suffix = uuid.uuid4().hex[:8]
        return f"{date_part}_{random_suffix}{ext}"

    # 不匹配任何规则
    return None

def process_directory():
    """遍历源目录，处理所有文件并复制到目标目录"""
    if not SOURCE_DIR.exists():
        print(f"错误：源目录不存在 {SOURCE_DIR}")
        return

    # 统计
    total_skipped = 0
    total_copied = 0

    for root, dirs, files in os.walk(SOURCE_DIR):
        root_path = Path(root)
        rel_path = root_path.relative_to(SOURCE_DIR)  # 相对路径，用于保持子文件夹
        target_root = TARGET_DIR / rel_path
        target_root.mkdir(parents=True, exist_ok=True)

        for file in files:
            src_file = root_path / file
            if not src_file.is_file():
                continue

            # 1. 检查扩展名是否允许
            ext = os.path.splitext(file)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                print(f"跳过非图片格式: {src_file}")
                total_skipped += 1
                continue

            # 2. 尝试生成新文件名
            new_name = generate_new_filename(file)
            if new_name is None:
                # 无法识别命名规则，保留原文件名
                new_name = file
                print(f"未识别命名，保留原名: {src_file} -> {target_root / new_name}")
            else:
                print(f"重命名: {src_file} -> {target_root / new_name}")

            dst_file = target_root / new_name
            if dst_file.exists():
                print(f"警告：目标文件已存在，跳过 {dst_file}")
                continue

            try:
                shutil.copy2(src_file, dst_file)
                total_copied += 1
            except Exception as e:
                print(f"复制失败 {src_file} -> {dst_file}: {e}")

    print(f"\n处理完成：复制 {total_copied} 个图片，跳过 {total_skipped} 个非图片文件。")

if __name__ == "__main__":
    process_directory()