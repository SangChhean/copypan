# 3.5 → 4.0 继承：字段勘探报告

数据目录：`C:\Users\28121\Desktop\12490原文JSONL`

源索引只读导出（已排除 dense_vector）。本报告不涉及切块与写入 ES。

## `kg-rag_life`

- 条数：39,463
- chunk_id 总数 / 去重：39,463 / 39,463（等于总条数）

### 字段清单

| 字段 | 出现条数 | 出现率 | 类型分布 |
|---|---:|---:|---|
| `author` | 39,463 | 100.0% | str:39463 |
| `book_title` | 39,463 | 100.0% | str:39463 |
| `chunk_id` | 39,463 | 100.0% | str:39463 |
| `en` | 39,463 | 100.0% | str:39463 |
| `message_key` | 39,463 | 100.0% | str:39463 |
| `message_number` | 39,463 | 100.0% | int:39463 |
| `message_title` | 39,463 | 100.0% | str:39463 |
| `original_ids` | 39,463 | 100.0% | list[str]:39463 |
| `paragraph_type` | 39,463 | 100.0% | str:39463 |
| `scripture_refs` | 39,463 | 100.0% | list(empty):28347, list[str]:11116 |
| `section_title` | 38,234 | 96.9% | str:38234 |
| `source_en` | 39,463 | 100.0% | str:39463 |
| `source_zh` | 39,463 | 100.0% | str:39463 |
| `text` | 39,463 | 100.0% | str:39463 |
| `tokens` | 39,463 | 100.0% | int:39463 |

### 标题空值率

- `book_title` 空：0（0.00%）
- `message_title` 空：0（0.00%）
- `section_title` 空：1,229（3.11%）

- `text` 以 `book_title` 开头：1 / 39,463（0.00%）

### 样本 3 条（text 截前 120 字）

#### 样本 1

```json
{
  "chunk_id": "life_9-34-18",
  "text": "我们的神是有怜悯的，但祂也是公正的。神爱大卫，然而大卫因着自己的罪，就失去了立场和地位；并且失去十二支派中的十一个支派，只有犹大支派留下来跟随大卫（撒下二十1～2）。在所罗门之后，他的国就分裂了；最终，犹大和以色列都被掳。以色列人失去了他们…",
  "en": "Our God is merciful, but He is also just. God loved David, but because of his sin David lost his standing and position and eleven of the twelve tribes. Only the tribe of Judah remained with David (2Sam.20:1-2). After Solomon's reign the kingdom was divided, and eventually Judah and Israel were taken into captivity. The children of Israel lost their nation and the land of their fathers; they were scattered around the globe; and they were persecuted and killed. Today, although they have a narrow strip of land near the Mediterranean Sea, they have no peace with their neighbors.",
  "book_title": "撒母耳记生命读经",
  "author": "李常受",
  "message_key": "life_9-34",
  "message_number": 34,
  "message_title": "第三十四篇　人的失败和神的惩治",
  "section_title": "神是有怜悯的，也是公正的",
  "paragraph_type": "text",
  "scripture_refs": [
    "（撒下二十1～2）"
  ],
  "source_zh": "（撒母耳记生命读经，第三十四篇，第十七段）",
  "source_en": "(Life-study of Samuel, msg. 34)",
  "tokens": 120,
  "original_ids": [
    "life_9-34-18"
  ]
}
```

#### 样本 2

```json
{
  "chunk_id": "life_9-34-20",
  "text": "我们若回顾召会历史，就会看见在已过十九个世纪里所发生的事，与撒母耳记所揭示的四件事相符：神的主宰、神的经纶、人的失败和神惩治的审判。在启示录二至三章，我们看见召会在神的审判之下。这审判要完成于十七章对大巴比伦的审判。当我们思想神的审判这件事…",
  "en": "If we trace the history of the church, we will see that what has happened during the past nineteen centuries matches the four matters found in the books of Samuel: God's sovereignty, God's economy, man's failure, and God's punishing judgment. In chapters two and three of Revelation, we see the church under God's judgment. This judgment will consummate in chapter seventeen, with the judgment of Babylon the Great. As we consider this matter of God's judgment, we need to be very conscious of what God is and of what our response should be.",
  "book_title": "撒母耳记生命读经",
  "author": "李常受",
  "message_key": "life_9-34",
  "message_number": 34,
  "message_title": "第三十四篇　人的失败和神的惩治",
  "section_title": "神在召会历史中的审判",
  "paragraph_type": "text",
  "scripture_refs": [],
  "source_zh": "（撒母耳记生命读经，第三十四篇，第十九段）",
  "source_en": "(Life-study of Samuel, msg. 34)",
  "tokens": 94,
  "original_ids": [
    "life_9-34-20"
  ]
}
```

#### 样本 3

```json
{
  "chunk_id": "life_9-34-22",
  "text": "圣经记载神对大卫惩治的审判，今天乃是为着警戒我们（林前十11）。我们该在神面前，严肃的读这段记载。这记载警戒我们，放纵肉体是严重的事。大卫只因看一眼，就受了试诱，无法约束自己。我们在主恢复里的人，在接触异性的事上，必须圣别、分别归神。性的邪…",
  "en": "The account of God's punishing judgment on David is written as a warning to us today (1Cor.10:11). We should read this account seriously in the presence of God. This account warns us that the indulgence of the flesh is a serious thing. David was tempted simply by a glance and then he failed to restrict himself.In contacting the opposite sex, we in the Lord's recovery need to be sanctified and separated unto God. The evil concerning sex is very contagious. We must exercise our spirit to overcome our flesh and our old man. This must not be a mere teaching; it must be a practice in our daily life.All the saints, especially the young ones, should search their hearts and make a strong resolution of heart (Judg.5:15-16) never to go the way of the indulgence of the flesh. Our God is living, and Christ is real. With Christ as the life-giving Spirit, everything is real, but apart from Him everything is vanity of vanities. The Spirit is moving within us in a very gentle way. We need to say, \"Lord Jesus, I love You, I need You, and I receive You.\" If we say this, He will be our Savior and our dynamic salvation. As the pneumatic Christ, He will save us, preserve us, and protect us from the contamination of this age, so that we may keep the glory that we have gained.",
  "book_title": "撒母耳记生命读经",
  "author": "李常受",
  "message_key": "life_9-34",
  "message_number": 34,
  "message_title": "第三十四篇　人的失败和神的惩治",
  "section_title": "圣经记载神对大卫惩治的审判，今天乃是为着警戒我们",
  "paragraph_type": "text",
  "scripture_refs": [
    "（林前十11）",
    "（士五15～16）"
  ],
  "source_zh": "（撒母耳记生命读经，第三十四篇，第二十一段）",
  "source_en": "(Life-study of Samuel, msg. 34)",
  "tokens": 259,
  "original_ids": [
    "life_9-34-22",
    "life_9-34-23",
    "life_9-34-24"
  ]
}
```

## `kg-rag_cwwl`

- 条数：178,107
- chunk_id 总数 / 去重：178,107 / 178,107（等于总条数）

### 字段清单

| 字段 | 出现条数 | 出现率 | 类型分布 |
|---|---:|---:|---|
| `author` | 178,107 | 100.0% | str:178107 |
| `book_title` | 178,107 | 100.0% | str:178107 |
| `chunk_id` | 178,107 | 100.0% | str:178107 |
| `en` | 178,107 | 100.0% | str:178107 |
| `message_key` | 178,107 | 100.0% | str:178107 |
| `message_number` | 178,107 | 100.0% | int:178107 |
| `message_title` | 178,107 | 100.0% | str:178107 |
| `original_ids` | 178,107 | 100.0% | list[str]:178107 |
| `paragraph_type` | 178,107 | 100.0% | str:178107 |
| `scripture_refs` | 178,107 | 100.0% | list(empty):140073, list[str]:38034 |
| `section_title` | 167,557 | 94.1% | str:167557 |
| `source_en` | 178,107 | 100.0% | str:178107 |
| `source_zh` | 178,107 | 100.0% | str:178107 |
| `text` | 178,107 | 100.0% | str:178107 |
| `tokens` | 178,107 | 100.0% | int:178107 |
| `year` | 178,107 | 100.0% | int:178107 |

### 标题空值率

- `book_title` 空：0（0.00%）
- `message_title` 空：0（0.00%）
- `section_title` 空：10,550（5.92%）

- `text` 以 `book_title` 开头：0 / 178,107（0.00%）

### 样本 3 条（text 截前 120 字）

#### 样本 1

```json
{
  "chunk_id": "cwwl_1990-3-3#2-9",
  "text": "有人可能说这是太过了。不，这不是太过，根据我人生的经历，教育仅次于神。我感谢神，当我年轻时，祂给我机会、时间来接受祂。我年轻时就得着神。不仅如此，我同时也接受了相当程度的教育。",
  "en": "Some of you may say that this is too much. No, this is not too much. According to my experience of human life, education is next only to God. I thank God that when I was young, He afforded me the opportunity, the time, to receive Him. I had God when I was young. Moreover, at the same time, I received a certain amount of education.",
  "book_title": "李常受文集一九九〇年第三册，与旧金山召会的交通，以及与柏克莱青年人、大专生和召会的交通",
  "author": "李常受",
  "year": 1990,
  "message_key": "cwwl_1990-3-3#2",
  "message_number": 2,
  "message_title": "第二章　神、教育与性格",
  "section_title": "教育",
  "paragraph_type": "text",
  "scripture_refs": [],
  "source_zh": "（李常受文集一九九〇年第三册，与旧金山召会的交通，以及与柏克莱青年人、大专生和召会的交通，第二章，第八段）",
  "source_en": "(CWWL, 1990, vol. 3, \"Fellowship with the Church in San Francisco, California, and With the Young People, the College Students, and the Church in Berkeley, California,\" ch. 2)",
  "tokens": 58,
  "original_ids": [
    "cwwl_1990-3-3#2-9"
  ]
}
```

#### 样本 2

```json
{
  "chunk_id": "cwwl_1958-1-5#3-36",
  "text": "我难过的点在这里，同工们在外面，有的人所作的工作，属灵的分量非常差，完全没有下文可说。有的人实在给人一些属灵的帮助，但在他们手里，从来没有成全出一个有用的人。好像人经过他们的手，铁定是不会成器的。对一个好的木匠来说，无论你拿什么样的木头给他…",
  "en": "Some of the workers lack spiritual weight in their work, and therefore there is no result. Some workers render spiritual help to the saints, but they do not perfect the saints to be useful. The saints whom they serve do not become useful. A good carpenter can use wood of any quality to make something useful. However, even though some of our workers render the saints spiritual help, the saints are still not useful vessels. This can be compared to a carpenter who works on different pieces of wood until the pieces are smooth and have nice colors but are not useful. They are just pieces of wood; nothing useful, like a desk or chair, has been produced.",
  "book_title": "李常受文集一九五八年第一册，成全圣徒与神家的建造",
  "author": "李常受",
  "year": 1958,
  "message_key": "cwwl_1958-1-5#3",
  "message_number": 3,
  "message_title": "第三章",
  "section_title": "有恩赐者成全圣徒以直接建造召会",
  "paragraph_type": "text",
  "scripture_refs": [],
  "source_zh": "（李常受文集一九五八年第一册，成全圣徒与神家的建造，第三章，第三十六段）",
  "source_en": "(CWWL, 1958, vol. 1, \"The Perfecting of the Saints and the Building Up of the House of God,\" ch. 3, par. 36)",
  "tokens": 252,
  "original_ids": [
    "cwwl_1958-1-5#3-36"
  ]
}
```

#### 样本 3

```json
{
  "chunk_id": "cwwl_1958-1-5#3-41",
  "text": "今天召会里的材料，不是为着陈列好看，乃是为着建造。建造的人把材料弄得好看，还是其次；能把材料建造起来才是第一。有的同工弟兄姊妹所作的工，最多只是把材料弄得好看一点，从来不懂什么叫作成全别人。然而成全别人，才是真实的建造，才真是作神的同工。",
  "en": "The material in the church is for building; it is not for display. Construction workers build with materials; they do not beautify materials. However, some co-workers only beautify the building materials. They do not know how to perfect others, which is the real building. The saints who know how to perfect others are genuine co-workers of God.",
  "book_title": "李常受文集一九五八年第一册，成全圣徒与神家的建造",
  "author": "李常受",
  "year": 1958,
  "message_key": "cwwl_1958-1-5#3",
  "message_number": 3,
  "message_title": "第三章",
  "section_title": "有恩赐者成全圣徒以直接建造召会",
  "paragraph_type": "text",
  "scripture_refs": [],
  "source_zh": "（李常受文集一九五八年第一册，成全圣徒与神家的建造，第三章，第四十一段）",
  "source_en": "(CWWL, 1958, vol. 1, \"The Perfecting of the Saints and the Building Up of the House of God,\" ch. 3, par. 41)",
  "tokens": 79,
  "original_ids": [
    "cwwl_1958-1-5#3-41"
  ]
}
```

## `kg-rag_cwwn`

- 条数：32,032
- chunk_id 总数 / 去重：32,032 / 32,032（等于总条数）

### 字段清单

| 字段 | 出现条数 | 出现率 | 类型分布 |
|---|---:|---:|---|
| `author` | 32,032 | 100.0% | str:32032 |
| `book_title` | 32,032 | 100.0% | str:32032 |
| `chunk_id` | 32,032 | 100.0% | str:32032 |
| `en` | 32,032 | 100.0% | str:32032 |
| `message_key` | 32,032 | 100.0% | str:32032 |
| `message_number` | 32,032 | 100.0% | int:32032 |
| `message_title` | 32,032 | 100.0% | str:32032 |
| `original_ids` | 32,032 | 100.0% | list[str]:32032 |
| `paragraph_type` | 32,032 | 100.0% | str:32032 |
| `scripture_refs` | 32,032 | 100.0% | list(empty):26780, list[str]:5252 |
| `section_title` | 27,576 | 86.1% | str:27576 |
| `source_en` | 32,032 | 100.0% | str:32032 |
| `source_zh` | 32,032 | 100.0% | str:32032 |
| `text` | 32,032 | 100.0% | str:32032 |
| `tokens` | 32,032 | 100.0% | int:32032 |

### 标题空值率

- `book_title` 空：0（0.00%）
- `message_title` 空：0（0.00%）
- `section_title` 空：4,456（13.91%）

- `text` 以 `book_title` 开头：1 / 32,032（0.00%）

### 样本 3 条（text 截前 120 字）

#### 样本 1

```json
{
  "chunk_id": "cwwn_2-19#5-2",
  "text": "我们每个人都曾在罪的辖制中，我们很容易相信罪恶的事是属撒但的；但我们同样相信世界的事是属撒但的么？我想我们许多人对此仍存二心。然而圣经何等清楚的确言，“全世界都卧在那恶者手下。”（约壹五19。）一般说来，撒但深知，想要借着确实是罪恶的事诱陷…",
  "en": "Having every one of us been in bondage to sin, we readily believe that sinful things are Satanic; but do we believe equally that the things of the world are Satanic? Many of us, I think, are still in two minds about this. Yet how clearly Scripture affirms that “the whole world lieth in the evil one” (1 John 5:19). Satan well knows that, generally speaking, to try to ensnare real Christians through things that are positively sinful is vain and futile. They will usually sense the danger and elude him. So he had contrived instead an enticing network, the mesh of which is so skillfully woven as to entrap the most innocent of men. We flee sinful lusts, and with good reason, but when it comes to such seemingly innocuous things as science and art and education, how readily do we lose our sense of values and fall a prey to his enticements!",
  "book_title": "倪柝声文集第二辑第十八册，不要爱世界、坐行站",
  "author": "倪柝声",
  "message_key": "cwwn_2-19#5",
  "message_number": 5,
  "message_title": "第二章　远离神的趋势",
  "paragraph_type": "text",
  "scripture_refs": [
    "（约壹五19。）"
  ],
  "source_zh": "（倪柝声文集第二辑第十八册，不要爱世界、坐行站，第二章，第一段）",
  "source_en": "(CWWN, vol. 38, \"Sit, Walk, Stand; Love Not the World,\" ch. 2)",
  "tokens": 166,
  "original_ids": [
    "cwwn_2-19#5-2"
  ]
}
```

#### 样本 2

```json
{
  "chunk_id": "cwwn_2-19#5-3",
  "text": "然而我们的主对世界的判决清楚的含示，构成“世界”的每件事，都与神的旨意不合。祂说，“现在这世界受审判，”这清楚的含示，凡构成kosmos的，都必被定罪；倘若这世界不是有根本的错误，主绝不会说出这话。再者，耶稣接着说，“这世界的王要被赶出去，…",
  "en": "Yet our Lord’s sentence of judgment clearly implies that everything that constitutes “the world” is out of line with God’s purpose. His words, “Now is the judgment of this world,” clearly imply the condemnation of all that goes to make up the cosmos, and would never have been uttered if there were not something radically amiss with it. Further, when Jesus goes on: “Now shall the prince of this world be cast out,” he is stressing not merely the intimate relation between Satan and the world order but the fact that its condemnation is linked with his. Do we acknowledge that Satan is today the prince of education and science and culture and the arts, and that they, with him, are doomed? Do we acknowledge that he is the effective master of all those things that together make up the world system?",
  "book_title": "倪柝声文集第二辑第十八册，不要爱世界、坐行站",
  "author": "倪柝声",
  "message_key": "cwwn_2-19#5",
  "message_number": 5,
  "message_title": "第二章　远离神的趋势",
  "paragraph_type": "text",
  "scripture_refs": [],
  "source_zh": "（倪柝声文集第二辑第十八册，不要爱世界、坐行站，第二章，第二段）",
  "source_en": "(CWWN, vol. 38, \"Sit, Walk, Stand; Love Not the World,\" ch. 2)",
  "tokens": 150,
  "original_ids": [
    "cwwn_2-19#5-3"
  ]
}
```

#### 样本 3

```json
{
  "chunk_id": "cwwn_2-19#5-4",
  "text": "一提起舞厅或夜总会，我们基督徒直觉的反应就是反对。对我们而言，那是十足的世界。然而，从另一个极端来看，一讨论医学或社会服务，基督徒也许一点都没有这样的反应。这些事得到我们的赞许，可能也得到我们热心的支持。在这两个极端之间，有许许多多其他的事…",
  "en": "When mention is made of a dance hall or a night club, our reaction as Christians is one of instinctive disapproval. To us that is “the world” par excellence. When, however, to go to the other extreme, medical science or social service are discussed, there may be no such reaction at all. These things command our tacit approval, and maybe too our enthusiastic support. And between these extremes there lie a host of other things varying widely in their influence for good or bad, between which we should probably none of us agree on where to draw an exact line. Yet let us face the fact that judgment has been pronounced by God, not upon certain selected things that belong to this world, but impartially upon them all.",
  "book_title": "倪柝声文集第二辑第十八册，不要爱世界、坐行站",
  "author": "倪柝声",
  "message_key": "cwwn_2-19#5",
  "message_number": 5,
  "message_title": "第二章　远离神的趋势",
  "paragraph_type": "text",
  "scripture_refs": [],
  "source_zh": "（倪柝声文集第二辑第十八册，不要爱世界、坐行站，第二章，第三段）",
  "source_en": "(CWWN, vol. 38, \"Sit, Walk, Stand; Love Not the World,\" ch. 2)",
  "tokens": 138,
  "original_ids": [
    "cwwn_2-19#5-4"
  ]
}
```

## `kg-rag_others`

- 条数：15,481
- chunk_id 总数 / 去重：15,481 / 15,481（等于总条数）

### 字段清单

| 字段 | 出现条数 | 出现率 | 类型分布 |
|---|---:|---:|---|
| `author` | 15,481 | 100.0% | str:15481 |
| `book_title` | 15,481 | 100.0% | str:15481 |
| `chunk_id` | 15,481 | 100.0% | str:15481 |
| `en` | 15,481 | 100.0% | str:15481 |
| `message_key` | 15,481 | 100.0% | str:15481 |
| `message_number` | 15,481 | 100.0% | int:15481 |
| `message_title` | 15,481 | 100.0% | str:15481 |
| `original_ids` | 15,481 | 100.0% | list[str]:15481 |
| `paragraph_type` | 15,481 | 100.0% | str:15481 |
| `scripture_refs` | 15,481 | 100.0% | list(empty):8915, list[str]:6566 |
| `section_title` | 15,060 | 97.3% | str:15060 |
| `source_en` | 15,481 | 100.0% | str:15481 |
| `source_zh` | 15,481 | 100.0% | str:15481 |
| `text` | 15,481 | 100.0% | str:15481 |
| `tokens` | 15,481 | 100.0% | int:15481 |

### 标题空值率

- `book_title` 空：0（0.00%）
- `message_title` 空：0（0.00%）
- `section_title` 空：421（2.72%）

- `text` 以 `book_title` 开头：2 / 15,481（0.01%）

### 样本 3 条（text 截前 120 字）

#### 样本 1

```json
{
  "chunk_id": "others_1_363-42",
  "text": "保罗用隐喻的说法，接着说到召会是“真理的柱石和根基”。柱石支持建筑物，根基托住柱石。召会就是这样支持真理的柱石，也是这样托住真理的根基。这里的真理，是指照着神新约的经纶，在新约里所启示，关乎基督与召会的真实事物。真理是神新约经纶的实际和内容…",
  "en": "Speaking metaphorically, Paul speaks of the church as “the pillar and base of the truth.” The pillar supports the building, and the base holds the pillar. The church is such a supporting pillar and holding base of the truth. The truth here refers to the real things which are revealed in the New Testament concerning Christ and the church according to God’s New Testament economy. The truth is the reality and the contents of God’s New Testament economy. This economy is composed of two mysteries: Christ as the mystery of God (Col. 2:2) and the church as the mystery of Christ (Eph. 3:4). Christ and the church, the Head and the Body, are the contents of the reality of God’s New Testament economy. The church is the supporting pillar and holding base of all these realities. A local church should be such a building that holds, bears, and testifies the truth, the reality, of Christ and the church. ",
  "book_title": "新约总论",
  "author": "李常受",
  "message_key": "others_1_363",
  "message_number": 363,
  "message_title": "第三百六十三篇　在书信中的经历并享受基督（六九）",
  "section_title": "ｃ　活神的召会所担负的真理",
  "paragraph_type": "text",
  "scripture_refs": [
    "（西二2）",
    "（弗三4）"
  ],
  "source_zh": "（新约总论，第三百六十三篇，第四十一段）",
  "source_en": "(The Conclusion of the New Testament, msg. 363)",
  "tokens": 164,
  "original_ids": [
    "others_1_363-42"
  ]
}
```

#### 样本 2

```json
{
  "chunk_id": "others_1_363-43",
  "text": "召会对于神有一个功能，就是把神的一切，就是宇宙中的那个实际，也就是那真理托住。“实际”比“真理”更达意，因为“真理”容易害意，常让人领会成道理，以为召会是托着这些道理。不，召会不是托住道理，召会乃是托着神所是的一切实际。宇宙间，只有神是实际…",
  "en": "To God, the church has the function to bear all that God is as the reality, the truth, of the universe. The word reality is better than truth in conveying the proper meaning, because truth can be misunderstood as doctrines. This may cause people to think that the church holds doctrines. No, the church is not for holding doctrines but for holding the reality of all that God is. In the universe, only God is reality; all that He is, is reality, which is borne by the church. We are here as the church, the house and household of God, holding the reality of all that God is. ",
  "book_title": "新约总论",
  "author": "李常受",
  "message_key": "others_1_363",
  "message_number": 363,
  "message_title": "第三百六十三篇　在书信中的经历并享受基督（六九）",
  "section_title": "ｃ　活神的召会所担负的真理",
  "paragraph_type": "text",
  "scripture_refs": [],
  "source_zh": "（新约总论，第三百六十三篇，第四十二段）",
  "source_en": "(The Conclusion of the New Testament, msg. 363)",
  "tokens": 121,
  "original_ids": [
    "others_1_363-43"
  ]
}
```

#### 样本 3

```json
{
  "chunk_id": "others_1_363-46",
  "text": "十六节启示出召会所托住的实际是什么：“大哉！敬虔的奥秘！这是众所公认的，就是：祂显现于肉体，被称义于灵里，被天使看见，被传于万邦，被信仰于世人中，被接去于荣耀里。”十五节的真理，实际的彰显，就是十六节敬虔的奥秘。正如前面所题的，敬虔的奥秘就…",
  "en": "The reality borne by the church is revealed in 1 Timothy 3:16: “Confessedly, great is the mystery of godliness: He who was manifested in the flesh, / Justified in the Spirit, / Seen by angels, / Preached among the nations, / Believed on in the world, / Taken up in glory.” The truth in verse 15, the expression of the reality, is the mystery of godliness in verse 16. As previously mentioned, the mystery of godliness is God manifested in the flesh. When Christ was on earth, He was God manifested in the flesh. Outwardly, He was a man in the flesh; inwardly, in actuality and in reality, He was God. God in His reality was manifested in the man Jesus. God was reality, and Jesus as a man in the flesh was the manifestation of God. This is the truth mentioned in verse 15, and this is the mystery of godliness. ",
  "book_title": "新约总论",
  "author": "李常受",
  "message_key": "others_1_363",
  "message_number": 363,
  "message_title": "第三百六十三篇　在书信中的经历并享受基督（六九）",
  "section_title": "ｃ　活神的召会所担负的真理",
  "paragraph_type": "text",
  "scripture_refs": [],
  "source_zh": "（新约总论，第三百六十三篇，第四十五段）",
  "source_en": "(The Conclusion of the New Testament, msg. 363)",
  "tokens": 152,
  "original_ids": [
    "others_1_363-46"
  ]
}
```

## `kg-rag_map_note`

- 条数：16,052
- chunk_id 总数 / 去重：16,052 / 16,052（等于总条数）

### 字段清单

| 字段 | 出现条数 | 出现率 | 类型分布 |
|---|---:|---:|---|
| `author` | 16,052 | 100.0% | str:16052 |
| `book_title` | 16,052 | 100.0% | str:16052 |
| `chunk_id` | 16,052 | 100.0% | str:16052 |
| `en` | 16,052 | 100.0% | str:16052 |
| `message_key` | 16,052 | 100.0% | str:16052 |
| `message_number` | 16,052 | 100.0% | int:16052 |
| `message_title` | 16,052 | 100.0% | str:16052 |
| `original_ids` | 16,052 | 100.0% | list[str]:16052 |
| `paragraph_type` | 16,052 | 100.0% | str:16052 |
| `scripture_refs` | 16,052 | 100.0% | list[str]:12344, list(empty):3708 |
| `source_en` | 16,052 | 100.0% | str:16052 |
| `source_zh` | 16,052 | 100.0% | str:16052 |
| `text` | 16,052 | 100.0% | str:16052 |
| `tokens` | 16,052 | 100.0% | int:16052 |

### 标题空值率

- `book_title` 空：0（0.00%）
- `message_title` 空：0（0.00%）
- `section_title` 空：16,052（100.00%）

- `text` 以 `book_title` 开头：0 / 16,052（0.00%）

### 样本 3 条（text 截前 120 字）

#### 样本 1

```json
{
  "chunk_id": "map_note_75-1-9_c3",
  "text": "叁　使徒新约的职事不但有荣光，更充盈着神的荣光，远超过摩西旧约职事的荣光—10节，【林后三9注3】：\n一　使徒那为着新约的职事，不是属于死的字句，如摩西那为着旧约的职事，乃是属于赐人生命的活灵—【林后三6注3】。\n二　因着新约职事的荣光（这…",
  "en": "",
  "book_title": "圣经真理题库，第一系列　圣经—神的话，旧约与新约的关联",
  "author": "李常受",
  "message_key": "map_note_75-1",
  "message_number": 9,
  "message_title": "第五篇　旧约与新约的对比（一）",
  "paragraph_type": "note",
  "scripture_refs": [
    "（三7，出三四29~30）"
  ],
  "source_zh": "（恢复本圣经，林后三9，注3）",
  "source_en": "",
  "tokens": 312,
  "original_ids": [
    "map_note_75-1-9"
  ]
}
```

#### 样本 2

```json
{
  "chunk_id": "map_note_75-1-9_c4",
  "text": "肆　在福音上所显示神的义（一17），是神在新约经纶里，将祂自己分赐到人里面的基础和根基；这义与神在旧约经纶里的律法毫无关系—腓三9与注，【罗三21注2】：\n一　律法是神在旧约对人暂时的经纶（安排），因为律法是因人的过犯临时添上的（加三19）…",
  "en": "",
  "book_title": "圣经真理题库，第一系列　圣经—神的话，旧约与新约的关联",
  "author": "李常受",
  "message_key": "map_note_75-1",
  "message_number": 9,
  "message_title": "第五篇　旧约与新约的对比（一）",
  "paragraph_type": "note",
  "scripture_refs": [
    "（加三19）",
    "（十5，腓三9）",
    "（约壹三23）",
    "（加三23、25）"
  ],
  "source_zh": "（恢复本圣经，罗三21，注2）",
  "source_en": "",
  "tokens": 250,
  "original_ids": [
    "map_note_75-1-9"
  ]
}
```

#### 样本 3

```json
{
  "chunk_id": "map_note_75-1-9_c5",
  "text": "伍　我们照着这客观的信仰，主观的相信神所要我们相信的基督，就得着信的义；这义是我们在神所安排客观的信仰中，有了我们主观的相信所得的基督，作了神的义，给我们得着—林前一30，【罗四13注2】。",
  "en": "",
  "book_title": "圣经真理题库，第一系列　圣经—神的话，旧约与新约的关联",
  "author": "李常受",
  "message_key": "map_note_75-1",
  "message_number": 9,
  "message_title": "第五篇　旧约与新约的对比（一）",
  "paragraph_type": "note",
  "scripture_refs": [],
  "source_zh": "（恢复本圣经，罗四13，注2）",
  "source_en": "",
  "tokens": 63,
  "original_ids": [
    "map_note_75-1-9"
  ]
}
```

## 与 `kg-rag_life` 字段集对照

`kg-rag_life` 字段集（15）：`author`, `book_title`, `chunk_id`, `en`, `message_key`, `message_number`, `message_title`, `original_ids`, `paragraph_type`, `scripture_refs`, `section_title`, `source_en`, `source_zh`, `text`, `tokens`

### `kg-rag_cwwl`

- 与 life **不一致**
- 仅 life 有：（无）
- 仅本索引有：['year']

### `kg-rag_cwwn`

- 与 life **一致**

### `kg-rag_others`

- 与 life **一致**

### `kg-rag_map_note`

- 与 life **不一致**
- 仅 life 有：['section_title']
- 仅本索引有：（无）

## A4 硬闸门判定

- 四个职事正文索引字段集存在不一致 → **阶段 B 全部停下，等确认**。
- `kg-rag_map_note` 字段集与 life **不同**（预期）→ **map_note 本项停下，只记入本报告，等确认后再做**。

proceed_text_four: no
proceed_map_note: no

