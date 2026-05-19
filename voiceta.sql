/*
 Navicat Premium Data Transfer

 Source Server         : voiceTA
 Source Server Type    : MySQL
 Source Server Version : 80033
 Source Host           : localhost:3306
 Source Schema         : voiceta

 Target Server Type    : MySQL
 Target Server Version : 80033
 File Encoding         : 65001

 Date: 19/05/2026 18:56:13
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for courses
-- ----------------------------
DROP TABLE IF EXISTS `courses`;
CREATE TABLE `courses`  (
  `id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `teacher_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `requirements` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `teacher_user_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `teacher_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `assignment_name` varchar(160) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '课程报告',
  `assignment_requirements` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of courses
-- ----------------------------
INSERT INTO `courses` VALUES ('9b35cfe3', '推荐系统', NULL, NULL, '8d788385431273d11e8b43bb78f3aa41', '默认老师', '课程报告', '测试', '2026-05-19 14:51:23');

-- ----------------------------
-- Table structure for qa_records
-- ----------------------------
DROP TABLE IF EXISTS `qa_records`;
CREATE TABLE `qa_records`  (
  `id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `report_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `question` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `answer` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `created_by_user_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `created_by_user_id`(`created_by_user_id` ASC) USING BTREE,
  INDEX `ix_qa_records_report_id`(`report_id` ASC) USING BTREE,
  CONSTRAINT `qa_records_ibfk_1` FOREIGN KEY (`report_id`) REFERENCES `reports` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `qa_records_ibfk_2` FOREIGN KEY (`created_by_user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of qa_records
-- ----------------------------

-- ----------------------------
-- Table structure for reports
-- ----------------------------
DROP TABLE IF EXISTS `reports`;
CREATE TABLE `reports`  (
  `id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `course_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `student_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `report` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `student_user_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `student_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `course_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `assignment_name` varchar(160) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '课程报告',
  `assignment_requirements` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `original_filename` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `stored_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pending',
  `result` json NULL,
  `error` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of reports
-- ----------------------------
INSERT INTO `reports` VALUES ('961a1d65f9da49dcae254356697f0bc4', '9b35cfe3', NULL, NULL, 'cd73502828457d15655bbd7a63fb0bc8', '默认学生', '推荐系统', '课程报告', '测试', '报告-1.pdf', 'D:\\胡老师的琐事\\语音助教\\Voice-TA\\data\\uploads\\961a1d65f9da49dcae254356697f0bc4.pdf', '2026-05-19 14:51:42', 'completed', '{\"_meta\": {\"model\": \"qwen-long\", \"source_filename\": \"961a1d65f9da49dcae254356697f0bc4.pdf\", \"uploaded_file_id\": \"file-fe-74095e61349849ee9f2f06a9\"}, \"report_brief\": {\"topic\": \"基于条件概率与Beta后验更新的外卖推荐系统冷启动算法设计与验证\", \"core_claims\": [\"通过价格和辣度两个维度将用户划分为四类象限，可在冷启动阶段实现较均衡的推荐覆盖\", \"结合人工先验权重与在线点击反馈的贝叶斯更新机制，能有效优化推荐排序，但先验偏差会导致收敛延迟\"], \"methods_or_evidence\": [\"问卷设计生成30个外卖品类及其多维标签与初始权重\", \"构建基于条件概率的FinalScore计算模型，并引入Beta分布进行后验点击率估计\", \"利用实际展示与点击数据对比预期点击率，评估模型表现\"]}, \"question_plan\": [{\"id\": \"q1\", \"focus\": \"方法选择理由\", \"priority\": \"high\", \"question\": \"你们为什么选择‘价格是否高于25元’和‘是否吃辣’作为启动时的两个判断题？这样划分四类用户的依据是什么？\", \"evidence_hint\": \"文档第一部分‘启动问题设计’段落\", \"sufficient_answer_criteria\": [\"说明这两个问题是为均匀划分用户象限\", \"指出其对应候选项目数相近，避免推荐池过小\", \"提及标签覆盖面广、易于用户快速作答\"], \"follow_up_when_insufficient\": [\"这两个问题如何保证四类用户对应的候选产品数量基本平衡？你能从表格里举个例子说明吗？\", \"如果换成‘主食类型’或‘用餐看重’作为初始问题，会有什么不同？\"]}, {\"id\": \"q2\", \"focus\": \"论证薄弱处\", \"priority\": \"high\", \"question\": \"你们提到总点击率实际为24.6%，低于预期的31.4%，主要原因是什么？\", \"evidence_hint\": \"文档第二部分关于粤菜简餐表现的分析段落\", \"sufficient_answer_criteria\": [\"指出粤菜简餐因先验权重过高导致未被替换\", \"承认初始权重设置失误影响模型自适应速度\", \"意识到低频更新或展示不足加剧了偏差\"], \"follow_up_when_insufficient\": [\"为什么粤菜简餐的低点击率没有被系统及时识别并替换？这反映模型哪个环节存在问题？\", \"除了先验错误，还有哪些因素可能导致整体表现下滑？\"]}, {\"id\": \"q3\", \"focus\": \"结果解释\", \"priority\": \"high\", \"question\": \"在‘麻辣烫’被替换成‘黄焖鸡米饭’之后，点击表现有所提升，这说明了什么？\", \"evidence_hint\": \"文档第二部分对麻辣烫与黄焖鸡米饭的对比分析\", \"sufficient_answer_criteria\": [\"说明模型能通过真实点击数据修正先验偏差\", \"确认算法具备动态优化能力\", \"区分人工干预与系统自主调整\"], \"follow_up_when_insufficient\": [\"这个替换是系统自动完成的吗？如果是，触发条件是什么？\", \"如果不是系统自动做的，那你们的人工干预标准又是什么？\"]}, {\"id\": \"q4\", \"focus\": \"数据或实验来源\", \"priority\": \"medium\", \"question\": \"你们的初始人工权重是怎么确定的？比如‘螺蛳粉’为什么是0.05，而‘拌面’只有0.01？\", \"evidence_hint\": \"表格1中的‘权重理由’列\", \"sufficient_answer_criteria\": [\"说明权重基于主观经验与流行趋势判断\", \"提及‘锅巴爱好者’‘网红爆款’等设定理由\", \"承认缺乏客观数据支撑，存在一定主观性\"], \"follow_up_when_insufficient\": [\"这些权重有没有经过小组讨论或多轮打分？还是仅凭个人经验？\", \"是否有外部数据支持这些先验设定，比如市场调研或历史销量？\"]}, {\"id\": \"q5\", \"focus\": \"方法或实现路径\", \"priority\": \"medium\", \"question\": \"你们是如何用条件概率把用户答案映射到具体外卖项目的？能不能一步步说清楚FinalScore是怎么算出来的？\", \"evidence_hint\": \"文档第一部分‘推荐算法’段落\", \"sufficient_answer_criteria\": [\"描述各维度偏好比例计算方式\", \"说明pm>0.5时对应标签项目乘以1.5倍权重\", \"强调最终得分是在象限内归一化后的排序依据\"], \"follow_up_when_insufficient\": [\"如果用户偏好‘饭’类主食，是不是所有带‘饭’标签的项目都会加分？加多少？\", \"当某个偏好的比例刚好是0.5，会不会导致无法判断？\"]}, {\"id\": \"q6\", \"focus\": \"与课程目标和作业要求的对应关系\", \"priority\": \"low\", \"question\": \"这份报告如何体现你们对推荐系统核心思想的理解？特别是冷启动问题的处理？\", \"evidence_hint\": \"文档中关于冷启动人工权重淡出机制的描述\", \"sufficient_answer_criteria\": [\"指出使用了基于内容的推荐与先验建模\", \"说明贝叶斯更新用于融合先验与实时反馈\", \"关联冷启动中‘利用先验知识过渡’的核心思路\"], \"follow_up_when_insufficient\": [\"你们用了哪些典型的推荐系统技术？比如协同过滤、内容推荐还是混合方法？\", \"Beta后验更新是不是一种典型的冷启动缓解策略？它属于哪一类方法？\"]}], \"voice_qa_prompt\": \"你现在是课程报告智能助教，正在对学生进行一对一语音问答。请依次提问以下六个问题：首先询问他们为何选择价格和辣度作为启动问题；接着问实际点击率低于预期的原因；然后探讨麻辣烫被替换后的表现变化说明了什么；再了解初始权重是如何设定的；随后让其详细解释FinalScore的计算过程；最后引导他们反思本项目如何体现对推荐系统尤其是冷启动问题的理解。每个问题最多追问两次，若回答包含充分标准中的要点即可进入下一题。当所有高优先级问题完成后，可宣布问答结束。禁止询问与报告无关的个人信息或超出课程范围的技术细节。\", \"teacher_attention\": [\"粤菜简餐因先验权重设置过高，导致低点击率长期未被系统识别，暴露模型对先验偏差敏感的问题\", \"总体点击率未达预期目标，反映当前冷启动机制在异常检测与快速响应方面仍有改进空间\"], \"coverage_threshold\": {\"done_rule\": \"所有高优先级问题均已获得充分回答，且至少完成一次追问循环\", \"max_follow_ups_per_question\": 2, \"required_high_priority_completed\": true}}', NULL);

-- ----------------------------
-- Table structure for users
-- ----------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users`  (
  `id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `password_hash` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `display_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `role` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'student',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of users
-- ----------------------------
INSERT INTO `users` VALUES ('21232f297a57a5a743894a0e4a801fc3', 'admin', NULL, NULL, '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', '系统管理员', 'admin', '2026-05-19 14:37:40');
INSERT INTO `users` VALUES ('8d788385431273d11e8b43bb78f3aa41', 'teacher', NULL, NULL, 'cde383eee8ee7a4400adf7a15f716f179a2eb97646b37e089eb8d6d04e663416', '默认老师', 'teacher', '2026-05-19 14:37:40');
INSERT INTO `users` VALUES ('cd73502828457d15655bbd7a63fb0bc8', 'student', NULL, NULL, '703b0a3d6ad75b649a28adde7d83c6251da457549263bc7ff45ec709b0a8448b', '默认学生', 'student', '2026-05-19 14:37:40');

SET FOREIGN_KEY_CHECKS = 1;
