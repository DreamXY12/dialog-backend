#!/bin/bash

# 需要清空的日志文件列表，当前目录下
LOG_FILES=(
    "./dev.log"
    "./pool_monitor.log"
)

for log in "${LOG_FILES[@]}"; do
    if [ -f "$log" ]; then
        # 清空文件，保留文件本身
        > "$log"
        echo "✅ 已清空: $log"
    else
        echo "⚠️ 文件不存在，跳过: $log"
    fi
done

echo "✅ 日志清空操作完成"