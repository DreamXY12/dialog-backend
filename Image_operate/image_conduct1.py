import os
import re
import shutil
from pathlib import Path

# 把S3上面的图片文件名后面的uuid去掉

# ========== 请在此处设置您的路径 ==========
SOURCE_DIR = Path("Image") / "conduct_image"   # 原始图片所在目录
TARGET_DIR = Path("Image") / "final_image"     # 处理后图片输出目录
# ========================================

# 允许处理的图片格式（可根据需要增删）
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp'}


def remove_uuid_from_filename(filename: str) -> str | None:
    """
    若文件名末尾为 "_xxxxxxxx"（8位字母/数字），则去除该部分并返回新文件名；
    否则返回 None（表示不处理）。
    """
    stem, ext = os.path.splitext(filename)
    # 匹配：任意内容 + 下划线 + 恰好8位字母数字
    pattern = re.compile(r'^(.+)_([a-zA-Z0-9]{8})$')
    match = pattern.match(stem)
    if match:
        new_stem = match.group(1)
        return new_stem + ext
    return None


def process():
    if not SOURCE_DIR.exists():
        print(f"错误：源目录不存在 - {SOURCE_DIR}")
        return

    # 创建目标目录（保留子文件夹结构）
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    for root, dirs, files in os.walk(SOURCE_DIR):
        root_path = Path(root)
        rel_path = root_path.relative_to(SOURCE_DIR)   # 相对路径，用于保持层级
        target_root = TARGET_DIR / rel_path
        target_root.mkdir(parents=True, exist_ok=True)

        for file in files:
            src_file = root_path / file
            if not src_file.is_file():
                continue

            # 仅处理常见图片格式，其他跳过
            ext = os.path.splitext(file)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                print(f"跳过非图片文件: {file}")
                continue

            # 尝试去除 UUID
            new_name = remove_uuid_from_filename(file)
            if new_name is None:
                new_name = file
                print(f"未匹配 UUID，保留原名: {file}")
            else:
                print(f"去除 UUID: {file} -> {new_name}")

            dst_file = target_root / new_name
            if dst_file.exists():
                print(f"警告：目标已存在，跳过 {dst_file}")
                continue

            try:
                shutil.copy2(src_file, dst_file)   # 保留元数据
            except Exception as e:
                print(f"复制失败 {src_file} -> {dst_file}: {e}")

    print("处理完成！")


if __name__ == "__main__":
    process()