import mysql.connector

# 连接到MySQL数据库
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="MariaDB2026!",
    database="dialog"
)

# 创建游标
cursor = conn.cursor()

# 查看case表的结构
cursor.execute("DESCRIBE `case`;")

# 获取结果
columns = cursor.fetchall()

# 打印结果
print("Case table structure:")
print("+------------------+------------------+------+-----+---------+----------------+")
print("| Field            | Type             | Null | Key | Default | Extra          |")
print("+------------------+------------------+------+-----+---------+----------------+")
for column in columns:
    field, type_, null, key, default, extra = column
    # 处理default为None的情况
    default_str = default if default is not None else "NULL"
    print(f"| {field:<16} | {type_:<16} | {null:<4} | {key:<3} | {default_str:<7} | {extra:<16} |")
print("+------------------+------------------+------+-----+---------+----------------+")

# 关闭连接
cursor.close()
conn.close()
