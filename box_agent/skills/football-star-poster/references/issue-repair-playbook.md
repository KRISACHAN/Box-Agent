# ISSUE 修复手册

| 问题 | 判定 | 修复方式 | Prompt 方向 |
|---|---|---|---|
| 出现真人脸或像真实球星 | BLOCKED | 改为虚构 IP/吉祥物，移除真人五官特征 | fictional mascot only, no real human likeness |
| 出现官方 Logo/队徽/赛事标识 | BLOCKED | 去标识重生，改原创抽象徽章或纯纹理 | remove all official marks, abstract geometric patch only |
| 球衣复刻官方款 | BLOCKED | 改原创球衣：改色块比例、条纹方向、领口、袖口、号码字体 | original non-official football kit |
| 组合识别过强 | ISSUE/BLOCKED | 减少年龄、号码、具体事件、动作、配色中的至少两项 | reduce identifying clues, keep only abstract spirit |
| 中文乱码或不可读 | ISSUE | 改无字版主视觉，使用 render_text_overlay.py 叠字 | no text in image, leave clean title safe area |
| 文字超出安全区 | ISSUE | 调整 text-overlay-config 中 x/y/font_size | keep text inside safe margin |
| IP 识别度不足 | ISSUE | 强化 IP 描述，增加 2-3 张自有 IP 参考图 | preserve mascot identity, face markings, body proportion |
| 画面畸形或多肢体 | ISSUE | 简化姿态，减少动作复杂度 | simple heroic standing pose, correct anatomy |
| 商用表述像官方授权 | BLOCKED | 移除“官方/授权/联名/同款/代言” | fan-inspired, brand-owned IP creative poster |

## 自动修复顺序

1. 先修合规：真人脸、Logo、球衣复刻、授权暗示。
2. 再修可用性：IP 保真、畸形、构图、文字。
3. 最后修风格：光影、材质、氛围、细节。

连续两次同类问题未解决时，应停止循环，降级交付：合规转译方案、无字版 prompt、叠字配置和人工排版建议。
