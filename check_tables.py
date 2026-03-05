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

# 查看数据库中的所有表
print("Database tables:")
cursor.execute("SHOW TABLES;")
tables = cursor.fetchall()
for table in tables:
    print(f"- {table[0]}")

# 查看case表的结构
print("\nCase table structure:")
print("+------------------+------------------+------+-----+---------+----------------+")
print("| Field            | Type             | Null | Key | Default | Extra          |")
print("+------------------+------------------+------+-----+---------+----------------+")
cursor.execute("DESCRIBE `case`;")
columns = cursor.fetchall()
for column in columns:
    field, type_, null, key, default, extra = column
    default_str = default if default is not None else "NULL"
    print(f"| {field:<16} | {type_:<16} | {null:<4} | {key:<3} | {default_str:<7} | {extra:<16} |")
print("+------------------+------------------+------+-----+---------+----------------+")

# 查看patient_case表的结构
print("\nPatient_case table structure:")
print("+------------------+------------------+------+-----+---------+----------------+")
print("| Field            | Type             | Null | Key | Default | Extra          |")
print("+------------------+------------------+------+-----+---------+----------------+")
cursor.execute("DESCRIBE patient_case;")
columns = cursor.fetchall()
for column in columns:
    field, type_, null, key, default, extra = column
    default_str = default if default is not None else "NULL"
    print(f"| {field:<16} | {type_:<16} | {null:<4} | {key:<3} | {default_str:<7} | {extra:<16} |")
print("+------------------+------------------+------+-----+---------+----------------+")

# 关闭连接
cursor.close()
conn.close()
