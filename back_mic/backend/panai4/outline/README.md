# 纲目 docx → JSON

把两批纲目 docx 转成每篇一行的 JSON。规则见 `docs/panai4_es/docx_to_json_plan.md`。样式映射、异体归一、截断标志、硬编码例外都在 `config.py`。

输入目录只读。产出默认写到桌面的 `纲目JSON`，不写进仓库。

## 运行

在 `back_mic/backend` 下：

```bash
python -m panai4.outline.convert_outline
```

仓库里再留一份报告时：

```bash
python -m panai4.outline.convert_outline --report-copy docs/panai4_es/conversion_report.md
```

`--report-copy` 若用相对路径，相对的是当前工作目录。

## 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `--a-root` | `C:\Users\28121\Desktop\倪李文集纲目` | A 批根目录，处理其中全部 docx |
| `--b-root` | `C:\Users\28121\Desktop\节期纲目` | B 批根目录，只处理文件名以 `【纲目的原文】` 开头的 docx |
| `--out` | `C:\Users\28121\Desktop\纲目JSON` | 产出目录 |
| `--report-copy` | 空 | 把 `conversion_report.md` 再写一份到这个路径 |

## 产出

- `outline_12490.json`：A 批纲目，一篇一行
- `outline_feasts.json`：B 批【纲目的原文】，一篇一行
- `excluded_files.json`：`excluded` 为条件 1（没有任何纲目点）排除的文件；`candidates` 为条件 2 候选，这些文件仍在主 JSON 里
- `anomalies.json`：异常，一条一行
- `conversion_report.md`：条数、层级、token、截断、异常、抽样

docx 用 `zipfile` 只读打开，只读 `word/document.xml` 和 `word/styles.xml`。
