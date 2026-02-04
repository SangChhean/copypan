import json
from search.get_search_index import get_info, parse_args
from es_config import es
from search.clear_data import clear_data


def get_page(page, pageSize):
    return (int(page) - 1) * int(pageSize)


def search(input: str, args: str):
    print("[search] ========== START ==========")
    print("[search] 收到参数: input=%r, args=%r" % (input, args))
    print("[search] args 原始值: %r" % (args,))

    try:
        parsed = parse_args(args)
        print("[search] args 解析后: cat1=%r, cat2=%r, cat3=%r, page=%s, pageSize=%s" % parsed)

        index, matchs, field, page, pageSize = get_info(args, input)
        print("[search] 查询索引列表: %s" % (index,))

        if not index:
            out = {"total": 0, "msg": []}
            print("[search] 索引为空，返回: %s" % (out,))
            print("[search] ========== END ==========")
            return out

        setting = {
            "size": pageSize,
            "from": get_page(page, pageSize),
            "query": {
                "bool": {
                    "should": matchs,
                    "minimum_should_match": 1,
                }
            },
            "highlight": {
                "number_of_fragments": 0,
                "fields": {"zh": {}, "text": {}, "en": {}, "title": {}},
            },
        }

        print("[search] 完整 ES 查询 JSON:")
        print(json.dumps(setting, ensure_ascii=False, indent=2))

        # 忽略不可用（红）索引，只从可用索引返回结果
        res = es.search(index=index, body=setting, ignore_unavailable=True)
        print("[search] ES 原始返回: hits.total=%s, hits 条数=%d" % (
            res.get("hits", {}).get("total"),
            len(res.get("hits", {}).get("hits", [])),
        ))

        data = clear_data(res, field)
        # 保证 msg 为列表
        if data.get("msg") is None:
            data["msg"] = []
        print("[search] 最终返回给前端: total=%s, msg 条数=%d" % (
            data.get("total"),
            len(data.get("msg", [])),
        ))
        print("[search] ========== END ==========")
        return data

    except Exception as e:
        print("[search] 查询异常: %r" % (e,))
        out = {"total": 0, "msg": []}
        print("[search] 返回空结果: %s" % (out,))
        print("[search] ========== END ==========")
        return out
