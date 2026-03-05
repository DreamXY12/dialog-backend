-- 数据库建表语句汇总
-- 生成时间: 2026-02-13

-- 设置字符集和校对规则
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET collation_connection = utf8mb4_unicode_ci;

-- 1. invitation_code 表
CREATE TABLE IF NOT EXISTS `invitation_code` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `code` VARCHAR(32) UNIQUE NOT NULL,
  `status` BOOLEAN DEFAULT TRUE,
  `tag` VARCHAR(255),
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. user 表
CREATE TABLE IF NOT EXISTS `user` (
  `user_id` INT AUTO_INCREMENT PRIMARY KEY,
  `identity` VARCHAR(100),
  `code` INT,
  `username` VARCHAR(255) UNIQUE,
  `hashed_password` VARCHAR(255),
  `date_of_birth` DATE,
  `sex` VARCHAR(10),
  `family_history` VARCHAR(255),
  `smoking_status` VARCHAR(255),
  `drinking_history` VARCHAR(255),
  `height` DOUBLE,
  `weight` DOUBLE,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_code` (`code`),
  INDEX `idx_username` (`username`),
  FOREIGN KEY (`code`) REFERENCES `invitation_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. case 表
CREATE TABLE IF NOT EXISTS `case` (
  `user_id` INT,
  `case_id` INT AUTO_INCREMENT PRIMARY KEY,
  `hba1c` FLOAT,
  `fastingGlucose` FLOAT,
  `hdlCholesterol` FLOAT,
  `totalCholesterol` FLOAT,
  `ldlCholesterol` FLOAT,
  `creatinine` FLOAT,
  `triglyceride` FLOAT,
  `potassium` FLOAT,
  `time_spec` INT NOT NULL,
  `testDate` DATE NOT NULL,
  `analysis_result` VARCHAR(30),
  `score` FLOAT,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_testDate` (`testDate`),
  FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. session 表
CREATE TABLE IF NOT EXISTS `session` (
  `user_id` INT,
  `session_key` VARCHAR(255) PRIMARY KEY,
  `status` BOOLEAN DEFAULT FALSE,
  `prompts` JSON,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_user_id` (`user_id`),
  FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. query 表
CREATE TABLE IF NOT EXISTS `query` (
  `query_id` INT AUTO_INCREMENT PRIMARY KEY,
  `session_key` VARCHAR(255),
  `enquiry` TEXT NOT NULL,
  `response` TEXT,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_session_key` (`session_key`),
  FOREIGN KEY (`session_key`) REFERENCES `session` (`session_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. doctor_response 表
CREATE TABLE IF NOT EXISTS `doctor_response` (
  `user_id` INT,
  `eval_id` INT AUTO_INCREMENT PRIMARY KEY,
  `query` TEXT NOT NULL,
  `response` TEXT,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_user_id` (`user_id`),
  FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. doctor_score 表
CREATE TABLE IF NOT EXISTS `doctor_score` (
  `user_id` INT,
  `score_id` INT AUTO_INCREMENT PRIMARY KEY,
  `query` TEXT NOT NULL,
  `response` TEXT NOT NULL,
  `score` INT,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_user_id` (`user_id`),
  FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. login_code 表
CREATE TABLE IF NOT EXISTS `login_code` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `code` VARCHAR(4) UNIQUE NOT NULL,
  `is_used` BOOLEAN DEFAULT FALSE,
  `user_type` VARCHAR(10),
  `used_at` DATETIME,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. nurse 表
CREATE TABLE IF NOT EXISTS `nurse` (
  `nurse_id` INT AUTO_INCREMENT PRIMARY KEY,
  `login_code` VARCHAR(4) UNIQUE NOT NULL,
  `first_name` VARCHAR(50) NOT NULL,
  `last_name` VARCHAR(50) NOT NULL,
  `hashed_password` VARCHAR(255) NOT NULL,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_login_code` (`login_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. patient 表
CREATE TABLE IF NOT EXISTS `patient` (
  `patient_id` INT AUTO_INCREMENT PRIMARY KEY,
  `login_code` VARCHAR(4) UNIQUE NOT NULL,
  `first_name` VARCHAR(50) NOT NULL,
  `last_name` VARCHAR(50) NOT NULL,
  `hashed_password` VARCHAR(255) NOT NULL,
  `date_of_birth` DATE,
  `sex` ENUM('Female', 'Male', 'Prefer not to tell'),
  `family_history` ENUM('Yes', 'No', 'Unknown'),
  `smoking_status` ENUM('Yes', 'No', 'Prefer not to tell'),
  `drinking_history` ENUM('Never', 'Rarely', 'Occasionally', 'Frequently', 'Daily'),
  `height` DECIMAL(5,2),
  `weight` DECIMAL(5,2),
  `assigned_nurse_id` VARCHAR(4),
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_login_code` (`login_code`),
  INDEX `idx_assigned_nurse_id` (`assigned_nurse_id`),
  FOREIGN KEY (`assigned_nurse_id`) REFERENCES `nurse` (`login_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. ai_dialog_history 表
CREATE TABLE IF NOT EXISTS `ai_dialog_history` (
  `history_id` INT AUTO_INCREMENT PRIMARY KEY,
  `patient_login_code` VARCHAR(4) NOT NULL,
  `session_key` VARCHAR(100) UNIQUE NOT NULL,
  `ai_model` VARCHAR(50),
  `title` VARCHAR(200),
  `prompts` JSON,
  `message_count` INT DEFAULT 0,
  `last_message_time` DATETIME,
  `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_patient_login_code` (`patient_login_code`),
  INDEX `idx_session_key` (`session_key`),
  FOREIGN KEY (`patient_login_code`) REFERENCES `patient` (`login_code`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12. blood_glucose_records 表
CREATE TABLE IF NOT EXISTS `blood_glucose_records` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `patient_login_code` VARCHAR(4) NOT NULL,
  `value` DECIMAL(5,2) NOT NULL COMMENT '血糖值 (mmol/L)',
  `period` VARCHAR(50) NOT NULL COMMENT '测量时段: 空腹、餐前、餐后、睡前',
  `recorded_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间',
  INDEX `idx_patient_login_code` (`patient_login_code`),
  INDEX `idx_recorded_at` (`recorded_at`),
  FOREIGN KEY (`patient_login_code`) REFERENCES `patient` (`login_code`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 创建完成后的注释
-- 所有表已创建完成
-- 注意：在实际使用前，请确保数据库已存在
-- 可以使用以下命令创建数据库：
-- CREATE DATABASE IF NOT EXISTS `dialog` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;