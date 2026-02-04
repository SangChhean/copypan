from es_config import es


def delete_and_recreate_index(index_name):
    msg = ""
    try:
        mapping = es.indices.get_mapping(index=index_name)
    except Exception as e:
        msg = f"获取索引映射时出错: {e}"

    try:
        es.indices.delete(index=index_name)
    except Exception as e:
        msg = f"删除索引时出错: {e}"

    try:
        es.indices.create(
            index=index_name, body={"mappings": mapping[index_name]["mappings"]}
        )
        msg = f"索引 {index_name} 已清空"
    except Exception as e:
        msg = f"重新创建索引时出错: {e}"

    return msg


def get_all_indices():
    try:
        indices = es.cat.indices(format="json")
        index_names = []
        for index in indices:
            idx = index["index"]
            index_names.append({"indexname": idx, "del": ""})
        return index_names
    except Exception as e:
        return []


def datalist(index, opt):
    if opt == "getlist":
        return {"datalist": get_all_indices(), "msg": "datalist"}
    elif opt == "del":
        tip = delete_and_recreate_index(index)
        return {"tip": tip, "msg": ""}
    return
